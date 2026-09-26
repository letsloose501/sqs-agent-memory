#!/usr/bin/env python3
"""Does the agent reach for this skill on the wordings it should - and only those?

Two different failures wear the same word. A skill that never fires is invisible; a
skill that fires on a neighbour's work is worse, because it produces confident wrong
work and the neighbour looks broken. Reading a description tells you neither. This
runs the agent against a labelled set and counts what actually happened.

The set lives in either shape:

    evals/trigger/should-trigger.yaml       - prompt: "Convert this PDF into a spreadsheet"
    evals/trigger/should-not-trigger.yaml     expected: trigger
    evals/eval_queries.json                 [{"query": "...", "should_trigger": true}]

The numbers are the confusion matrix and nothing more: true and false positives, true
and false negatives, precision, recall, F1 - printed beside the cases they came from.
F1 deliberately does not become a grade. It weighs the two failures equally, and they
are not equal: a skill that stays quiet costs a turn, a skill that barges in costs the
user their work. Which one you can afford is a judgement about your tree, not a
property of the number.

The train/validation split is what separates a description tuned against its failures
from one that generalises. Tune on train; if validation moves with it, the change was
real, and if it does not, the description memorised the train set.
"""
import json
import os
import random

QUERIES_JSON = os.path.join("evals", "eval_queries.json")
TRIGGER_DIR = os.path.join("evals", "trigger")
POSITIVE_FILE = "should-trigger.yaml"
NEGATIVE_FILE = "should-not-trigger.yaml"
THRESHOLD = 0.5
TRAIN_SHARE = 0.6
# The guidance asks for about twenty queries, eight to ten on each side.
SIDE_MIN = 8
# A per-run spend cap. The routing decision lands in the first turn or two, and the rest
# of a run is the skill doing its job - work this pass pays for and throws away. Measured
# on a real tree: one uncapped query cost $0.62 over 19 turns against $0.14 over 4 with
# the cap on, and both answered the only question being asked. It is a ceiling, not a
# spend: raise it for a skill whose routing decision genuinely takes longer to appear.
RUN_BUDGET_USD = 0.12


class DatasetError(ValueError):
    pass


def parse_simple_yaml(text, source="<yaml>"):
    """A list of items from the one YAML shape this format needs, and nothing else.

    Supported: a sequence of mappings with scalar values, or a sequence of plain
    strings. Comments and blank lines are ignored. Anything else - nesting, block
    scalars, flow collections, anchors - raises, naming the line.

    A tolerant parser here would be a liability: silently misreading a label turns a
    should-not-trigger case into a should-trigger one, and the report would then call
    a precision failure a success.
    """
    items = []
    current = None
    for n, raw in enumerate(text.split("\n"), 1):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        if line.startswith("- "):
            body = line[2:].strip()
            current = {}
            items.append(current)
            if ":" in body and not body.startswith(("\"", "'")):
                key, _, value = body.partition(":")
                current[key.strip()] = _scalar(value.strip(), n, source)
            elif body:
                current["prompt"] = _scalar(body, n, source)
            continue
        if line.startswith(("  ", "\t")) and current is not None:
            body = line.strip()
            if ":" not in body:
                raise DatasetError(f"{source}:{n}: expected `key: value`, got {body!r}")
            key, _, value = body.partition(":")
            current[key.strip()] = _scalar(value.strip(), n, source)
            continue
        raise DatasetError(f"{source}:{n}: only a list of `- prompt: ...` items is "
                           f"supported here, got {line.strip()[:40]!r}")
    return items


def _strip_comment(raw):
    """The line without its comment, by YAML's own rule.

    A comment opens at a `#` outside quotes that starts the line or follows whitespace.
    This used to cut at the first `#` anywhere, so `- prompt: "fix issue #12"` read as
    `"fix issue` with a stray quote and no error - a real prompt silently rewritten,
    which is the one failure this parser exists to refuse. `C#` was cut the same way.
    """
    quote = None
    for i, ch in enumerate(raw):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'" and (i == 0 or raw[i - 1] in " \t:-"):
            quote = ch
        elif ch == "#" and (i == 0 or raw[i - 1] in " \t"):
            return raw[:i]
    return raw


def _scalar(value, line, source):
    if value[:1] in "|>":
        raise DatasetError(f"{source}:{line}: block scalars are not supported - put the "
                           f"prompt on one line")
    if value[:1] in "[{":
        raise DatasetError(f"{source}:{line}: flow collections are not supported")
    if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


class Query:
    __slots__ = ("text", "want", "source")

    def __init__(self, text, want, source):
        self.text = text
        self.want = want
        self.source = source


def load(skill_root):
    """(queries, problem). The yaml pair wins when both shapes are present."""
    tdir = os.path.join(skill_root, TRIGGER_DIR)
    out = []
    if os.path.isdir(tdir):
        for filename, want in ((POSITIVE_FILE, True), (NEGATIVE_FILE, False)):
            path = os.path.join(tdir, filename)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                try:
                    items = parse_simple_yaml(f.read(), os.path.join(TRIGGER_DIR, filename))
                except DatasetError as e:
                    return [], str(e)
            for item in items:
                text = item.get("prompt") or item.get("query")
                if not text:
                    return [], f"{filename}: an item carries no `prompt`"
                expected = (item.get("expected") or "").strip().lower()
                if expected and expected not in ("trigger", "no-trigger", "none"):
                    return [], (f"{filename}: `expected: {expected}` is neither `trigger` "
                                f"nor `no-trigger`")
                # the file the case sits in is the label; `expected` may restate it and
                # must not contradict it, or one of the two is a lie
                if expected and (expected == "trigger") != want:
                    return [], (f"{filename}: a case labelled `{expected}` sits in the "
                                f"{'positive' if want else 'negative'} file")
                out.append(Query(text, want, filename))
        if out:
            return out, ""

    path = os.path.join(skill_root, QUERIES_JSON)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            return [], f"{QUERIES_JSON} does not parse: {e}"
        if not isinstance(data, list):
            return [], f"{QUERIES_JSON} is not a list of {{query, should_trigger}}"
        for item in data:
            if not isinstance(item, dict) or "query" not in item:
                return [], f"{QUERIES_JSON}: an entry carries no `query`"
            out.append(Query(item["query"], bool(item.get("should_trigger")), QUERIES_JSON))
        return out, ""
    return [], (f"no trigger set - `sqs.py evals <skill> --init` scaffolds "
                f"{QUERIES_JSON}, or write {TRIGGER_DIR}/{POSITIVE_FILE} and "
                f"{NEGATIVE_FILE}")


def split(queries, seed=0, share=TRAIN_SHARE):
    """Stratified train/validation split, fixed so two iterations compare like with like.

    Stratified because a random cut can land every negative on one side, and a set with
    no negatives measures breadth only: it cannot tell you the description got greedy.
    """
    rng = random.Random(seed)
    train, valid = [], []
    for want in (True, False):
        side = [q for q in queries if q.want is want]
        rng.shuffle(side)
        cut = round(len(side) * share)
        train += side[:cut]
        valid += side[cut:]
    rng.shuffle(train)
    rng.shuffle(valid)
    return train, valid


NOTHING = "(no skill)"


def measure(queries, skill_name, provider, runs, model, on_event=None, spend=None):
    """[(query, rate, usable runs, {skill loaded first: runs})] - how often each query
    loaded the skill, and what it loaded when it did not.

    The last element is what makes a miss actionable: "fired 0 of 2" says the description
    lost, not to whom - and whether to fix this description or the neighbour's depends
    entirely on who won. The first skill a run loaded is the routing decision; a skill
    loaded later in the same run is the agent's choice about its task.

    `spend`, when given, is a dict the runs' reported cost and time are added to. A run
    that reports no cost leaves `cost_usd` unknown for the whole pass rather than
    counting as free - the same rule as everywhere else: not measured is not zero.
    """
    rows = []
    for q in queries:
        hits = usable = 0
        went = {}
        for attempt in range(runs):
            if on_event:
                on_event(q, attempt + 1, runs)
            run = provider.run(q.text, skill=None, bare=False, model=model, timeout=180,
                               max_budget_usd=RUN_BUDGET_USD)
            if spend is not None:
                spend["runs"] = spend.get("runs", 0) + 1
                if run.cost_usd is None or spend.get("cost_usd", 0) is None:
                    spend["cost_usd"] = None
                else:
                    spend["cost_usd"] = spend.get("cost_usd", 0) + run.cost_usd
                if run.duration_s is not None:
                    spend["duration_s"] = spend.get("duration_s", 0) + run.duration_s
            if not run.ok:
                continue
            usable += 1
            hits += int(skill_name in run.skills)
            first = run.skills[0] if run.skills else NOTHING
            went[first] = went.get(first, 0) + 1
        rows.append((q, hits / usable if usable else None, usable, went))
    return rows


def confusion(rows, threshold=THRESHOLD):
    """The four counts, and the three ratios derived from them.

    A query is counted as "fired" when it loaded the skill in more than `threshold` of
    its runs: the model is not deterministic, and one run of one query is an anecdote.
    """
    tp = fp = fn = tn = unusable = 0
    for q, rate, *_ in rows:
        if rate is None:
            unusable += 1
            continue
        fired = rate > threshold
        if q.want and fired:
            tp += 1
        elif q.want and not fired:
            fn += 1
        elif not q.want and fired:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else (0.0 if precision is not None and recall is not None
                                        else None))
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "true_negative": tn, "unusable": unusable,
            "precision": precision, "recall": recall, "f1": f1}


def evaluate(skill, provider, runs=3, model=None, use_split=True, seed=0, on_event=None):
    """(report dict, problem)."""
    queries, problem = load(skill.root)
    if problem:
        return None, problem
    name = skill.name or skill.folder
    pos = sum(1 for q in queries if q.want)
    sets = []
    if use_split and len(queries) >= 6:
        train, valid = split(queries, seed)
        sets = [("train", train), ("validation", valid)]
    else:
        sets = [("all", queries)]

    out = {"skill": name, "provider": provider.name, "model": model, "runs_per_query": runs,
           "queries": len(queries), "positive": pos, "negative": len(queries) - pos,
           "threshold": THRESHOLD, "sets": {}}
    spend = {}
    for label, subset in sets:
        rows = measure(subset, name, provider, runs, model, on_event, spend)
        out["sets"][label] = {
            "metrics": confusion(rows),
            "cases": [{"prompt": q.text, "expected": "trigger" if q.want else "no-trigger",
                       "rate": rate, "runs": usable, "went_to": went}
                      for q, rate, usable, went in rows],
        }
    out["agent_runs"] = spend.get("runs", 0)
    out["cost_usd"] = spend.get("cost_usd") if spend.get("runs") else None
    out["duration_s"] = spend.get("duration_s")
    if "train" in out["sets"]:
        from . import regression                                  # noqa: PLC0415
        gap = regression.split_gap(out)
        out["split_gap"] = ({"lower": gap[0], "noise": gap[1]} if gap else None)
    return out, ""


def thin(report):
    """Whether the set is too small for its numbers to mean much."""
    return report["positive"] < SIDE_MIN or report["negative"] < SIDE_MIN


def render(report):
    lines = [f"Trigger evaluation: {report['skill']}",
             f"  provider {report['provider']} · {report['runs_per_query']} run(s) per query"
             f" · {report['queries']} queries "
             f"({report['positive']} should trigger, {report['negative']} should not)", ""]
    if thin(report):
        lines += [f"  Fewer than {SIDE_MIN} on a side. The numbers below are arithmetic, "
                  f"not evidence:",
                  "  one case moves precision by a tenth. The negatives matter most, and "
                  "the useful ones",
                  "  are near-misses - wordings that share vocabulary and need another "
                  "skill.", ""]
    for label, block in report["sets"].items():
        m = block["metrics"]
        def pct(v):
            return "n/a" if v is None else f"{v:.0%}"
        lines.append(f"  {label}")
        lines.append(f"    fired when it should      {m['true_positive']:>3}   "
                     f"(recall    {pct(m['recall'])})")
        lines.append(f"    stayed quiet when it should {m['true_negative']:>1}")
        lines.append(f"    missed                    {m['false_negative']:>3}   "
                     f"(precision {pct(m['precision'])})")
        lines.append(f"    barged in                 {m['false_positive']:>3}   "
                     f"(F1        {pct(m['f1'])})")
        if m["unusable"]:
            lines.append(f"    unusable runs             {m['unusable']:>3}")
        wrong = [c for c in block["cases"]
                 if c["rate"] is not None
                 and (c["rate"] > report["threshold"]) != (c["expected"] == "trigger")]
        for c in wrong:
            why = "did not fire" if c["expected"] == "trigger" else "fired when it should not"
            lines.append(f"      [{c['rate']:.2f}] {why}: {c['prompt'][:66]}")
            # who won instead: a miss to a neighbour is a boundary to draw, a miss to
            # nothing is a description that does not reach the request at all
            went = c.get("went_to") or {}
            if c["expected"] == "trigger" and went:
                took = ", ".join(f"{k} {v}/{c['runs']}" for k, v in
                                 sorted(went.items(), key=lambda kv: -kv[1])
                                 if k != report["skill"])
                if took:
                    lines.append(f"             went to: {took}")
        lines.append("")
    cost = report.get("cost_usd")
    runs_total = report.get("agent_runs")
    if runs_total:
        spent = f"${cost:.2f}" if cost is not None else "n/a (a run did not report its cost)"
        lines += [f"  {runs_total} agent run(s), cost {spent}", ""]
    gap = report.get("split_gap")
    if gap and gap["lower"] > 0:
        lines += [f"  Train F1 is above validation by more than the runs vary (at least "
                  f"{gap['lower']:.0%}).",
                  "  One study of production descriptions reads that as scopes that "
                  "genuinely overlap -",
                  "  a neighbour covers the same requests - which rewording does not "
                  "fix: draw the boundary", "  between the two skills instead.", ""]
    lines += ["  F1 is printed, not scored: it treats a miss and a false fire as equally "
              "bad, and in a",
              "  tree of skills they are not. Tune the description against the train "
              "failures; the",
              "  validation numbers are what say the change generalised."]
    return "\n".join(lines)
