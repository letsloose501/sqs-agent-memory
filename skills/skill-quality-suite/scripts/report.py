#!/usr/bin/env python3
"""Every way the suite's findings leave the process.

One analysis, several readers. A human at a terminal wants the findings sorted by how
loud they are; CI wants annotations on the diff; a security dashboard wants SARIF; and
whoever is deciding whether the skill is ready wants the board - one line per layer,
with the layers that were never run saying so instead of showing a zero.

The board is the answer to "how good is this skill" that does not collapse into a
single number. A number hides which question failed, and the questions are not
interchangeable: a skill can be flawless and never fire, or fire perfectly and leak a
token. `--score` will still add the number, and prints the arithmetic with it.
"""
import hashlib
import json
import os

from rules import RULES, module_of

RANK = {"error": 0, "warning": 1, "info": 2}
SIGIL = {"error": "⛔", "warning": "⚠️ ", "info": "· "}
SARIF_LEVEL = {"error": "error", "warning": "warning", "info": "note"}
TOOL_URI = "https://github.com/letsloose501/sqs-skills"

# The order the board prints, and the question each layer answers.
LAYERS = [
    ("STRUCTURE", "structure", "does every pointer still resolve"),
    ("SPEC", "spec", "will a strict loader take it"),
    ("QUALITY", "quality", "do the instructions read like instructions"),
    ("SECURITY", "security", "what can it do to the machine that loads it"),
    ("COMPATIBILITY", "compat", "will it work anywhere but here"),
    ("EVALS", "evals", "is there anything that would notice a regression"),
    ("PUBLISH", "publish", "is it safe to let it leave the machine"),
]


def uri_of(finding, base=None):
    """Repository-relative path for a finding, or None when it has no place.

    SARIF consumers resolve a URI against the checkout, so a path relative to the
    current directory is what GitHub Code Scanning can anchor a comment to. Falling
    back to `<skill folder>/<file>` keeps the field meaningful when the skill was
    checked from somewhere else entirely.
    """
    if not finding.where:
        return None
    root = getattr(finding, "root", None)
    if root:
        full = os.path.join(root, finding.where)
        try:
            rel = os.path.relpath(full, base or os.getcwd())
        except ValueError:                      # different drive on Windows
            rel = full
        return rel.replace("\\", "/")
    return f"{finding.skill}/{finding.where}".replace("\\", "/")


def render_text(results, strict=False, show_clean=True):
    lines = []
    for folder, found in results:
        if not found:
            if show_clean:
                lines.append(f"✅ {folder}")
            continue
        worst = min(RANK.get(f.severity, 3) for f in found)
        lines.append(f"{SIGIL[['error', 'warning', 'info'][worst]].strip()} {folder}")
        for f in found:
            place = f" ({f.where}:{f.line})" if f.where and f.line else (
                f" ({f.where})" if f.where else "")
            lines.append(f"     {SIGIL[f.severity]} {f.code} {f.msg}{place}")
    return "\n".join(lines)


def render_github(results):
    out = []
    for folder, found in results:
        for f in found:
            level = {"error": "error", "warning": "warning", "info": "notice"}[f.severity]
            row = RULES.get(f.code)
            title = row.title if row else f.code
            uri = uri_of(f)
            where = f"file={uri}" + (f",line={f.line}" if f.line else "") if uri else ""
            out.append(f"::{level} {where},title={f.code} {title}::{f.msg}")
    return "\n".join(out)


def render_json(results):
    return json.dumps({
        "findings": [
            {"skill": folder, "code": f.code, "module": module_of(f.code),
             "severity": f.severity, "message": f.msg, "file": f.where, "line": f.line,
             "confidence": (RULES[f.code].confidence if f.code in RULES else "unrated"),
             "false_positive_risk": (RULES[f.code].false_positive_risk
                                     if f.code in RULES else "unrated")}
            for folder, found in results for f in found
        ]
    }, ensure_ascii=False, indent=2)


def fingerprint(finding):
    """A hash that survives the finding moving down the file.

    The line number is deliberately left out: a finding that shifts because something
    was inserted above it is the same finding, and a fingerprint that changes with it
    makes every unrelated edit look like a new problem.
    """
    raw = "|".join((finding.code, finding.skill or "", finding.where or "", finding.msg))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class _whole_skill:
    """A stand-in finding that points at the skill itself rather than at a line."""

    def __init__(self, finding):
        self.root = finding.root
        self.skill = finding.skill
        self.where = "SKILL.md"
        self.line = None


def render_sarif(results, base=None, fallback=None):
    """SARIF 2.1.0, for GitHub Code Scanning and anything else that reads it.

    Every rule the run could emit is declared, not only the ones that fired, so the
    consumer can show a rule's reasoning even on a clean run. The two gradings ride
    along as properties: a dashboard that wants to hide the heuristics can filter on
    `confidence`, which is the thing a severity alone never tells it.
    """
    used = sorted({f.code for _, found in results for f in found})
    rules_block = []
    for code in sorted(RULES):
        row = RULES[code]
        rules_block.append({
            "id": code,
            "name": "".join(w.capitalize() for w in row.title.split()[:6] if w.isalnum()) or code,
            "shortDescription": {"text": row.title},
            "fullDescription": {"text": row.why},
            "help": {"text": f"{row.why}\n\nFix: {row.how}",
                     "markdown": f"{row.why}\n\n**Fix:** {row.how}"},
            "defaultConfiguration": {"level": SARIF_LEVEL.get(row.severity, "note")},
            "properties": {"category": row.category, "confidence": row.confidence,
                           "falsePositiveRisk": row.false_positive_risk,
                           "autofix": row.fixable,
                           "tags": [row.category, f"confidence:{row.confidence}"]},
        })
    out = []
    for folder, found in results:
        for f in found:
            result = {
                "ruleId": f.code,
                "level": SARIF_LEVEL.get(f.severity, "note"),
                "message": {"text": f.msg},
                "partialFingerprints": {"sqsFindingV1": fingerprint(f)},
                "properties": {"skill": folder, "module": module_of(f.code)},
            }
            # Every result gets a location, because code scanning refuses a SARIF file
            # where one does not ("expected at least one location"). A finding about the
            # skill as a whole - a duplicate `name`, a routing invariant - has no line to
            # point at, so it points at the skill's own SKILL.md, which is the file whose
            # content caused it.
            uri = uri_of(f, base)
            if not uri and getattr(f, "root", None):
                uri = uri_of(_whole_skill(f), base)
            uri = uri or fallback or "SKILL.md"
            loc = {"physicalLocation": {"artifactLocation": {"uri": uri}}}
            if f.line and f.where:
                loc["physicalLocation"]["region"] = {"startLine": f.line}
            result["locations"] = [loc]
            out.append(result)
    return json.dumps({
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "skill-quality-suite", "informationUri": TOOL_URI,
                                "rules": rules_block}},
            "results": out,
            "invocations": [{"executionSuccessful": True,
                             "properties": {"rulesEmitted": used}}],
        }],
    }, ensure_ascii=False, indent=2)


# ---- the board -------------------------------------------------------------

def counts_by_module(results):
    out = {}
    for _, found in results:
        for f in found:
            bucket = out.setdefault(module_of(f.code), {"error": 0, "warning": 0, "info": 0})
            bucket[f.severity] = bucket.get(f.severity, 0) + 1
    return out


def status_of(bucket):
    if bucket is None:
        return "NOT RUN"
    if bucket["error"]:
        return "FAIL"
    if bucket["warning"]:
        return "WARN"
    if bucket["info"]:
        return "NOTE"
    return "PASS"


def render_board(results, ran_modules, extras=None):
    """One line per layer, and `NOT RUN` where nothing was measured.

    `NOT RUN` is the whole point of this view. A layer that was skipped and a layer
    that passed look identical in a findings list, and that is how a report comes to
    say "clean" about a question nobody asked.
    """
    counts = counts_by_module(results)
    lines = []
    for label, module, question in LAYERS:
        bucket = counts.get(module, {"error": 0, "warning": 0, "info": 0}) \
            if module in ran_modules else None
        state = status_of(bucket)
        detail = ""
        if bucket:
            detail = " · ".join(f"{n} {k}" for k, n in bucket.items() if n)
        lines.append(f"{label:<16}{state:<10}{detail or question}")
    for label, state, detail in (extras or []):
        lines.append(f"{label:<16}{state:<10}{detail}")
    return "\n".join(lines)


# Weights for the optional aggregate. They are here, in the open, because a score
# whose arithmetic is hidden is a number people argue with instead of reading.
SCORE_WEIGHT = {"error": 8, "warning": 3, "info": 1}
SCORE_CAP = 100


def render_score(results):
    """The aggregate, with the arithmetic that produced it.

    Additional, never the headline: the board says which question failed, and this
    says only how much. Printing the subtraction is what keeps it from being read as
    a measurement of the skill rather than of the findings.
    """
    counts = counts_by_module(results)
    lines, total = [], 0
    for label, module, _ in LAYERS:
        bucket = counts.get(module)
        if not bucket:
            continue
        cost = sum(SCORE_WEIGHT[k] * n for k, n in bucket.items() if n)
        total += cost
        detail = " + ".join(f"{n}x{SCORE_WEIGHT[k]}" for k, n in bucket.items() if n)
        lines.append(f"  -{cost:<4} {label.lower():<14} {detail}")
    score = max(0, SCORE_CAP - total)
    head = [f"score {score}/100 = 100 - {total}", ""]
    tail = ["", "  Weights: error 8, warning 3, info 1. The number ranks two versions of "
                "one skill;",
            "  it does not compare two skills, and it does not say which question failed."]
    return "\n".join(head + (lines or ["  nothing was found"]) + tail)
