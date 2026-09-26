#!/usr/bin/env python3
"""Trigger queries out of the user's own history, instead of out of the author's head.

A trigger set written by the author tends to restate the description (`EV010` counts
how often), because the author writes down the phrasings they already listed. The
phrasings that matter are the ones people actually typed, and Claude Code keeps them:
every session is a JSONL transcript under `~/.claude/projects/<project>/`. This reads
those files - locally, read-only, nothing leaves the machine - and returns drafts.

What counts as a routing decision is read off the transcript's shape, not guessed:

- a **positive** is a user prompt whose first tool call was a `Skill` load of this
  skill. The first call is the moment the router decided; a skill loaded after other
  work in the same turn is the agent's decision about its task, not routing;
- a typed `/command`, a system or meta message, a compaction summary and a subagent's
  sidechain are not prompts, and they end the prompt before them - otherwise a load
  after an explicit `/konspekt` would be credited to whatever was said earlier;
- a **near miss** is a prompt whose first call loaded a different skill, ranked by how
  much of it this skill's description also covers. The top of that list is the wording
  a neighbour won and this skill could plausibly have claimed - the negatives a trigger
  set is supposed to be made of. Ranked, not thresholded: a cut-off would be a guess.

Everything returned is the user's own words. The drafts are printed for review and
written only on request, and only where no trigger set exists yet.
"""
import glob
import json
import os
import re

# A routing set is a set of wordings. A prompt this long is a pasted document with an
# instruction attached, which tests something else; the figure is a readability cap
# chosen by eye, not a measurement.
MAX_PROMPT_CHARS = 400


# A person pastes credentials into a chat, and a report built from their prompts prints
# them back: the first run of `discover` put a server's root password on the screen. Every
# prompt this module hands out goes through `redact`. The shapes are `security.SECRETS`
# plus the prose form a person actually types - a word for a secret, a colon, the value.
SECRET_PROSE_RE = re.compile(
    r"((?:password|passwd|pass|token|api[ _-]?key|secret|пароль|парол\w*|токен|ключ|секрет)"
    r"\b[^\n:=]{0,24}[:=]\s*)(\S+)", re.I)
REDACTED = "[redacted]"
# The harness records a stop by the person as a user message, or inside a tool result.
INTERRUPT_RE = re.compile(r"\[Request interrupted by user|doesn't want to proceed")


def redact(text):
    from security import SECRETS                                  # noqa: PLC0415
    for _, pattern in SECRETS:
        text = pattern.sub(REDACTED, text)
    return SECRET_PROSE_RE.sub(lambda m: m.group(1) + REDACTED, text)


def _result_text(block):
    c = block.get("content")
    if isinstance(c, str):
        return c
    return " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))


def default_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "projects")


def _user_text(content):
    """The typed text of a user record, or None for a record that carries no prompt."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(parts) if parts else None       # tool_result only: not a prompt
    return None


def _not_a_prompt(rec, text):
    """A user record that ends the current prompt without being one."""
    stripped = text.lstrip()
    return (rec.get("isMeta") or rec.get("isCompactSummary")
            or stripped.startswith("<") or stripped.startswith("/"))


def routing_decisions(path):
    """[(prompt, skill)] for each prompt in one transcript whose first tool was `Skill`.

    Also yields (prompt, None) for a prompt whose first tool was anything else, so a
    caller can tell "decided against every skill" from "never decided at all".
    """
    out = []
    prompt, decided = None, True
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("isSidechain"):
                continue
            kind = rec.get("type")
            content = (rec.get("message") or {}).get("content")
            if kind == "user":
                text = _user_text(content)
                if text is None:
                    continue                  # a tool result: the turn goes on
                if _not_a_prompt(rec, text):
                    prompt, decided = None, True
                    continue
                prompt, decided = redact(text.strip()), False
            elif kind == "assistant" and isinstance(content, list) and not decided:
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        skill = None
                        if block.get("name") == "Skill":
                            skill = (block.get("input") or {}).get("skill") or None
                        if prompt:
                            out.append((prompt, skill))
                        decided = True
                        break
    return out


def is_this(loaded, name):
    """The same two spellings `providers.loaded` accepts: bare, or behind a plugin."""
    return bool(loaded) and (loaded == name or loaded.endswith(":" + name))


def names_it(prompt, loaded):
    """Whether the prompt asked for the skill by name - `/trener`, or `konspekt` as a word.

    Such a load is a lookup, not a routing decision, and a trigger set built from it
    would measure whether the model can read a name. Watched in the first run over a real
    history: "давай /trener на сегодня" and "дай konspekt дописать" both ranked as
    near misses for neighbours they never competed with.
    """
    short = loaded.split(":")[-1]
    return re.search(r"(?<![\w-])/?" + re.escape(short) + r"(?![\w-])", prompt,
                     re.I) is not None


# A near miss has to carry a topic to compete on. `prompt_match` scores overlap against
# the shorter side, so a one-word reply ("добавляй") scores 0 or 1 and a 1 sorted to the
# top of the first real run. Three stems is the smallest prompt that says what it wants.
NEAR_MISS_MIN_STEMS = 3

# A link, a path or an attached file is not a topic. Left in, `users`, the account name and
# `downl` out of `@"C:\Users\...\Downloads\..."` were most of what put one prompt at the
# top of three different skills' near-miss lists in the second real run.
NOT_TOPIC_RE = re.compile(r"@\"[^\"]*\"|@\S+|https?://\S+|[A-Za-z]:\\\S*|(?:~|\.{0,2})/\S+")


def topic(prompt):
    return NOT_TOPIC_RE.sub(" ", prompt)


def harvest(skill, history_dir=None, limit=10):
    """{"positive": [...], "near_miss": [...], "skipped_long": n, "transcripts": n}."""
    from quality import prompt_match, stems          # local: quality is a heavy import

    name = skill.name or skill.folder
    files = glob.glob(os.path.join(history_dir or default_dir(), "*", "*.jsonl"))
    positives, others, seen, long_, named = [], [], set(), 0, 0
    for path in sorted(files):
        for prompt, loaded in routing_decisions(path):
            key = " ".join(prompt.split()).casefold()
            if key in seen:
                continue
            seen.add(key)
            if len(prompt) > MAX_PROMPT_CHARS:
                long_ += 1
                continue
            if loaded and names_it(prompt, loaded):
                named += 1
                continue
            if is_this(loaded, name):
                positives.append(prompt)
            elif loaded:
                others.append((prompt, loaded))
    own = stems(skill.description or "")
    ranked = []
    for prompt, loaded in others:
        st = stems(topic(prompt))
        if len(st) < NEAR_MISS_MIN_STEMS:
            continue
        score, _ = prompt_match(skill.description or "", st)
        if score > 0:
            ranked.append((score, len(st & own), prompt, loaded))
    # Share first, count second: ranked by count, the longest prompt won on length alone.
    ranked.sort(key=lambda r: (-r[0], -r[1]))
    return {"positive": positives[:limit],
            "near_miss": [{"query": p, "went_to": w, "overlap": round(s, 2)}
                          for s, _, p, w in ranked[:limit]],
            "skipped_long": long_, "skipped_named": named, "transcripts": len(files)}


def search(seeds, history_dir=None):
    """[(prompt, skill it loaded first or None)] for prompts carrying any of `seeds`.

    For a skill that does not exist yet there is no load to harvest, so the user names
    the need instead: a few words it would be asked with. A seed matches the start of a
    word, so `инвойс` finds `инвойсы` - Russian inflects at the end, and a whole-word
    match would miss most of it. The seeds are the user's choice; nothing here decides
    what is relevant on its own.
    """
    pats = [re.compile(r"(?<![\w-])" + re.escape(s.strip()), re.I) for s in seeds if s.strip()]
    if not pats:
        return []
    out, seen = [], set()
    files = glob.glob(os.path.join(history_dir or default_dir(), "*", "*.jsonl"))
    for path in sorted(files):
        for prompt, loaded in routing_decisions(path):
            key = " ".join(prompt.split()).casefold()
            if key in seen or len(prompt) > MAX_PROMPT_CHARS:
                continue
            seen.add(key)
            if any(p.search(prompt) for p in pats):
                out.append((prompt, loaded))
    return out


# What the agent looks up rather than does: a script's own usage, a path, a file by name.
# Asked once it is work; asked again in the next session it is something the skill could
# have said.
LOOKUP_RE = re.compile(r"(?:^|\s)(?:--help|-h)(?:\s|$)|\bfind\s+\S+.*-i?name\b"
                       r"|^\s*(?:which|where)\s", re.I)
SHELL_TOOLS = ("Bash", "PowerShell")
# Where a task keeps its own inputs. A file there is what one job was about, even when a
# later session opens it again: the first real run ranked a scratchpad transcript among a
# skill's heaviest reads, read from three sessions - one of them this tool's own.
TEMP_RE = re.compile(r"(?:^|[/\\])(?:te?mp|scratchpad)(?:[/\\]|$)", re.I)


def _call_key(name, inp):
    if name in SHELL_TOOLS:
        return " ".join(str(inp.get("command") or "").split())
    for k in ("file_path", "path", "pattern", "url", "query"):
        if inp.get(k):
            return str(inp[k])
    return ""


def _result_chars(block):
    c = block.get("content")
    if isinstance(c, str):
        return len(c)
    return sum(len(x.get("text", "")) for x in c or [] if isinstance(x, dict))


def _failure_key(tool, key):
    """What a failed call was, stable across sessions: a shell command's first two words,
    or a tool and the file name it touched."""
    if tool in SHELL_TOOLS:
        return " ".join(re.sub(r"[\"'`]", "", key).split()[:2])[:80]
    return f"{tool} {os.path.basename(key)}".strip()[:80]


def _loads(path, name):
    """[{"calls": [(tool, key)], "reads": [(key, chars)], "usage": {...}}] for one transcript.

    A load's work is everything the agent did from the `Skill` call to the next thing the
    person typed, or to the next skill loading. That is attribution by time, not by cause:
    a long turn that loads a skill and then goes on to something else is counted here too.
    One correction is made on evidence - a call that names another skill's folder is that
    skill's work - because the first run over real history filed a notes skill's turn full
    of a trainer skill's commands under the notes skill.
    """
    out, seg, msgs, pending = [], None, set(), {}
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    other_skill = re.compile(r"[/\\]\.claude[/\\]skills[/\\](?!" + re.escape(name)
                             + r"[/\\])[\w.-]+[/\\]")
    with f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("isSidechain"):
                continue
            msg = rec.get("message") or {}
            content = msg.get("content")
            if rec.get("type") == "user":
                text = _user_text(content)
                if text is not None and INTERRUPT_RE.search(text):
                    if seg is not None:               # a stop, not a new request
                        seg["interrupted"] = True
                    continue
                if text is not None:
                    if not rec.get("isMeta") and not text.lstrip().startswith("<"):
                        seg = None                    # the person spoke: the load's work ends
                    continue
                if seg is not None and isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            call = pending.pop(b.get("tool_use_id"), None)
                            result = _result_text(b)
                            if INTERRUPT_RE.search(result):
                                seg["interrupted"] = True
                            elif b.get("is_error") and call:
                                seg["failures"].append((_failure_key(*call), result))
                            if call and call[0] == "Read" and not TEMP_RE.search(call[1]):
                                seg["reads"].append((call[1], _result_chars(b)))
            elif rec.get("type") == "assistant" and isinstance(content, list):
                elsewhere = 0                         # calls that were another skill's work
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    tool, inp = b.get("name"), b.get("input") or {}
                    if tool == "Skill":
                        seg = None
                        if is_this(inp.get("skill") or "", name):
                            seg = {"calls": [], "reads": [], "usage": {"fresh": 0, "out": 0},
                                   "failures": [], "interrupted": False}
                            out.append(seg)
                        continue
                    if seg is None:
                        continue
                    key = _call_key(tool, inp)
                    if other_skill.search(key):
                        elsewhere += 1
                        continue
                    seg["calls"].append((tool, key))
                    pending[b.get("id")] = (tool, key)
                mid = msg.get("id")
                # A record carrying only another skill's call is that skill's cost as well.
                if seg is not None and mid and mid not in msgs and not elsewhere:
                    msgs.add(mid)                     # one message, several content records
                    u = msg.get("usage") or {}
                    seg["usage"]["fresh"] += ((u.get("input_tokens") or 0)
                                              + (u.get("cache_creation_input_tokens") or 0))
                    seg["usage"]["out"] += u.get("output_tokens") or 0
    return out


def work_after_load(skill, history_dir=None, limit=3):
    """Where the agent's work went after this skill loaded, across the user's sessions.

    Only what points at a change in the skill is reported, and each list is ranked rather
    than cut at a threshold nobody measured:

    - `lookups` - the same `--help`, `find -name` or `which` in two or more sessions: the
      skill left out something the agent keeps having to find;
    - `heavy_reads` - the files, read in two or more sessions, that cost the most
      characters across all loads; a grep, a section or a script would do;
    - `rereads` - a file read again in one load with no edit to it in between;
    - `cost` - loads, sessions, and the median fresh input and output tokens per load;
    - `failures` - a call that failed inside the skill's work in two or more sessions, with
      the last error: the skill keeps leading the agent into the same wall. Measured on a
      real history: a planning skill's shell command broke on its own quoting in eight
      sessions, a lyrics skill read a file past the size limit in three;
    - `interrupted` - loads the person stopped, beside the share of turns they stopped
      with no skill loaded. Counts, not a verdict: the samples are small.
    """
    import statistics                                               # noqa: PLC0415
    name = skill.name or skill.folder
    loads = []                                   # [(transcript, load)]
    for path in sorted(glob.glob(os.path.join(history_dir or default_dir(), "*", "*.jsonl"))):
        loads += [(path, seg) for seg in _loads(path, name)]
    if not loads:
        return {"loads": 0}
    lookup_sessions = {}
    for path, seg in loads:
        for tool, key in seg["calls"]:
            if tool in SHELL_TOOLS and LOOKUP_RE.search(key):
                lookup_sessions.setdefault(key, set()).add(path)
    lookups = sorted(((len(v), k) for k, v in lookup_sessions.items() if len(v) >= 2),
                     key=lambda r: (-r[0], r[1]))
    read_chars, read_count, read_sessions = {}, {}, {}
    for path, seg in loads:
        for key, chars in seg["reads"]:
            read_chars[key] = read_chars.get(key, 0) + chars
            read_count[key] = read_count.get(key, 0) + 1
            read_sessions.setdefault(key, set()).add(path)
    # A file read in one session only is that task's input - a transcript being analysed,
    # a draft being edited - and reading it whole is the task. What the skill can change
    # is what it makes the agent read every time: its own references, the notes it
    # consults. Watched: without this, the top of a video-analysis skill's list was the
    # transcripts it had been asked to analyse.
    heavy = sorted(((k, c) for k, c in read_chars.items() if len(read_sessions[k]) >= 2),
                   key=lambda kv: -kv[1])
    rereads = {}
    for _, seg in loads:
        open_reads = set()
        for tool, key in seg["calls"]:
            if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                open_reads.discard(key)
            elif tool == "Read" and not TEMP_RE.search(key):
                if key in open_reads:
                    rereads[key] = rereads.get(key, 0) + 1
                open_reads.add(key)
    fail_sessions, fail_last = {}, {}
    for path, seg in loads:
        for key, result in seg["failures"]:
            fail_sessions.setdefault(key, set()).add(path)
            fail_last[key] = redact(" ".join(result.split()))[:160]
    failures = sorted(((len(v), k) for k, v in fail_sessions.items() if len(v) >= 2),
                      key=lambda r: (-r[0], r[1]))
    base_turns = base_stopped = 0
    for _, seg in _all_segments(history_dir):
        if not seg["loaded"] and not seg["loaded_before"]:
            base_turns += 1
            base_stopped += seg["interrupted"]
    return {
        "failures": [{"call": k, "sessions": n, "last_error": fail_last[k]}
                     for n, k in failures[:limit]],
        "interrupted": {"loads": sum(1 for _, s in loads if s["interrupted"]),
                        "base_turns": base_turns, "base_stopped": base_stopped},
        "loads": len(loads), "sessions": len({p for p, _ in loads}),
        "median_fresh_tokens": int(statistics.median(s["usage"]["fresh"] for _, s in loads)),
        "median_output_tokens": int(statistics.median(s["usage"]["out"] for _, s in loads)),
        "lookups": [{"command": k, "sessions": n} for n, k in lookups[:limit]],
        "heavy_reads": [{"file": k, "chars": c, "reads": read_count[k]}
                        for k, c in heavy[:limit]],
        "rereads": [{"file": k, "times": n}
                    for k, n in sorted(rereads.items(), key=lambda kv: -kv[1])[:limit]],
    }


# What a task leaves behind that can be told apart from conversation: a script it ran and a
# file it changed. Stems of the prompt were tried first and measured as noise (1,058 real
# prompts, see `new --seed`); the agent's own actions are the part of a transcript that
# says what the work was without anyone judging intent.
# Only a script in the position where it runs: after an interpreter, or first in a command.
# Matching any `name.py` in the line counted the file names inside heredocs and commit
# messages, and `skills.sh`, a site's name, as a shell script run in four sessions.
INTERPRETER = (r"(?:\S*[/\\])?(?:python(?:3(?:\.\d+)?)?|pythonw|py|node|bash|sh|zsh|pwsh"
               r"|powershell|ruby|tsx|deno|bun)(?:\.exe)?")
_EXT = r"\.(?:py|ps1|sh|js|mjs|cjs|ts|rb)"
SCRIPT_RE = re.compile(r"(?:\A\s*|[;&|(]\s*|" + INTERPRETER + r"\s+(?:-\S+\s+)*)"
                       r"(?:\"([^\"\n]+" + _EXT + r")\"|'([^'\n]+" + _EXT + r")'"
                       r"|([^\s\"';|&()<>]+" + _EXT + r"))(?=[\s\"';|&)]|$)", re.I)


def _script(match):
    return match.group(1) or match.group(2) or match.group(3)
SKILL_PATH_RE = re.compile(r"[/\\]\.claude[/\\]skills[/\\]([\w.-]+)[/\\]")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# Files the harness itself asks the agent to keep - its memory index, its instructions,
# anything under `.claude/`. Editing them is the harness at work, not a task of the
# user's: the first run over real history put an auto-memory index at the top of the list.
HARNESS_FILE_RE = re.compile(r"(?:^|[/\\])(?:MEMORY|CLAUDE|AGENTS)\.md$|[/\\]\.claude[/\\]",
                             re.I)
# Source code edited again and again is software being written, which is the work of a
# project rather than a task a skill would carry; the documents a person keeps returning
# to - a plan, a registry, a note - are. Measured: before this, the files of the project
# under development filled the list, in front of a plan edited in nine sessions.
CODE_FILE_RE = re.compile(r"\.(?:py|pyi|js|mjs|cjs|jsx|ts|tsx|go|rs|java|kt|cs|cpp|c|h|rb|php"
                          r"|sh|ps1|json|ya?ml|toml|ini|cfg|lock|css|scss|html?|sql)$", re.I)
COMMAND_TAG_RE = re.compile(r"<command-name>/?([\w:.-]+)</command-name>")
COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def _signature(path):
    """A script or file as the last two parts of its path, so one tool run from two
    working directories - `video/transcript.py` and `C:/x/video/transcript.py` - is one."""
    parts = [p for p in re.split(r"[/\\]+", path.strip("\"'`")) if p and p not in (".", "~")]
    return "/".join(parts[-2:]).casefold() if parts else ""


def _segments(path):
    """[{"prompt", "loaded_before", "loaded", "scripts", "edits", "owned"}] for one transcript.

    A segment runs from a typed prompt - or a typed `/command`, which loads by name - to
    the next one. `loaded_before` is every skill loaded earlier in the session: a skill
    stays in context after it loads, so a later turn running its script without loading
    it again is the skill at work, not a miss. `owned` maps a skill folder to the scripts
    of it the segment ran; those are never counted as work without a skill.
    """
    out, seg, session_loaded = [], None, set()
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("isSidechain"):
                continue
            msg = rec.get("message") or {}
            content = msg.get("content")
            if rec.get("type") == "user":
                text = _user_text(content)
                if text is None and seg is not None and isinstance(content, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        and INTERRUPT_RE.search(_result_text(b)) for b in content):
                    seg["interrupted"] = True
                    continue
                if text is None or rec.get("isMeta") or rec.get("isCompactSummary"):
                    continue
                if INTERRUPT_RE.search(text):
                    if seg is not None:                # a stop belongs to the turn it ended
                        seg["interrupted"] = True
                    continue
                loaded = set()
                if text.lstrip().startswith("<"):
                    m = COMMAND_TAG_RE.search(text)
                    if not m:
                        continue                  # a reminder or a command's echo, not a turn
                    loaded.add(m.group(1).split(":")[-1])
                    args = COMMAND_ARGS_RE.search(text)
                    text = args.group(1) if args else ""
                if seg is not None:
                    session_loaded |= seg["loaded"]
                seg = {"prompt": redact(text.strip()), "loaded_before": set(session_loaded),
                       "loaded": loaded, "scripts": set(), "edits": set(), "owned": {},
                       "touched": set(), "worked_on": set(), "interrupted": False}
                out.append(seg)
            elif rec.get("type") == "assistant" and isinstance(content, list) and seg:
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    tool, inp = b.get("name"), b.get("input") or {}
                    if tool == "Skill":
                        seg["loaded"].add((inp.get("skill") or "").split(":")[-1])
                    elif tool in SHELL_TOOLS:
                        for m in SCRIPT_RE.finditer(str(inp.get("command") or "")):
                            script = _script(m)
                            owner = SKILL_PATH_RE.search(script)
                            if owner:
                                seg["owned"].setdefault(owner.group(1), set()).add(
                                    _signature(script))
                            elif not HARNESS_FILE_RE.search(script):
                                seg["scripts"].add(_signature(script))
                    elif tool in EDIT_TOOLS:
                        fp = str(inp.get("file_path") or inp.get("notebook_path") or "")
                        if not fp:
                            continue
                        seg["touched"].add(_signature(fp).rsplit("/", 1)[-1])
                        owner = SKILL_PATH_RE.search(fp)
                        if owner:
                            seg["worked_on"].add(owner.group(1))
                        if not (TEMP_RE.search(fp) or SKILL_PATH_RE.search(fp)
                                or HARNESS_FILE_RE.search(fp) or CODE_FILE_RE.search(fp)):
                            seg["edits"].add(_signature(fp))
    return out


_SEGMENTS = {}


def _worked_on(history_dir):
    """{transcript: skills whose files it edited}. A session that edits a skill is building
    it, and running its scripts there is testing them: the first run over real history
    listed a trainer skill's own development session as nine routing misses."""
    out = {}
    for path, seg in _all_segments(history_dir):
        out.setdefault(path, set()).update(seg["worked_on"])
    return out


def _all_segments(history_dir):
    """[(transcript, segment)] over the whole history, parsed once per process: `improve`
    over a tree asks for every skill, and a real history is hundreds of transcripts."""
    key = os.path.abspath(history_dir or default_dir())
    if key not in _SEGMENTS:
        _SEGMENTS[key] = [(path, seg)
                          for path in sorted(glob.glob(os.path.join(key, "*", "*.jsonl")))
                          for seg in _segments(path)]
    return _SEGMENTS[key]


def ran_unloaded(skill, history_dir=None, limit=5):
    """Prompts whose turn ran this skill's scripts in a session that never loaded it.

    Only a script in the skill's own folder counts - a path the transcript names, not a
    guess about the topic - only before the skill loaded anywhere in that session, and
    never in a session that edited the skill.
    The agent reaching for a skill's tools by hand is the plainest sign its description
    did not fire on that request: these are should-trigger wordings in the user's words.
    """
    names = {skill.folder, (skill.name or skill.folder).split(":")[-1]}
    building = _worked_on(history_dir)
    hits, sessions, turns = [], set(), 0
    for path, seg in _all_segments(history_dir):
        mine = set().union(*(seg["owned"].get(n, set()) for n in names))
        if not mine or names & (seg["loaded"] | seg["loaded_before"] | building[path]):
            continue
        sessions.add(path)
        turns += 1
        if seg["prompt"] and len(seg["prompt"]) <= MAX_PROMPT_CHARS:
            hits.append({"prompt": seg["prompt"], "scripts": sorted(mine)})
    return {"turns": turns, "sessions": len(sessions), "examples": hits[:limit]}


def unloaded_by_skill(history_dir=None):
    """{skill folder: (turns, sessions)} - `ran_unloaded` for every skill in one pass."""
    building = _worked_on(history_dir)
    turns, sessions = {}, {}
    for path, seg in _all_segments(history_dir):
        for owner in seg["owned"]:
            if owner in seg["loaded"] | seg["loaded_before"] | building[path]:
                continue
            turns[owner] = turns.get(owner, 0) + 1
            sessions.setdefault(owner, set()).add(path)
    return {k: (turns[k], len(sessions[k])) for k in turns}


def unskilled_work(history_dir=None, limit=8, min_sessions=2):
    """Work repeated across sessions with no skill in context: candidates for a new one.

    A script run or a file changed in turns of `min_sessions` or more sessions, none of
    which had loaded any skill up to that turn. Ranked by sessions, then turns, and not
    cut at a threshold: how many repeats make a task worth a skill is the reader's call.
    A script inside an installed skill is not here - that is `ran_unloaded`, a routing
    miss rather than a missing skill. The prompts that led to each are attached so that
    whoever reads the list judges intent; nothing here does.
    """
    # A script that was itself edited somewhere in the history is the thing being built,
    # not a tool being used: the first run ranked the files of the project under
    # development - its CLI, its test runner - as the user's most repeated work.
    # Matched by file name, because one script is run as `python sqs.py` from its folder
    # and edited as `scripts/sqs.py`, and only the name is common to both.
    developed = {name for _, seg in _all_segments(history_dir) for name in seg["touched"]}
    by_sig = {}
    for path, seg in _all_segments(history_dir):
        if seg["loaded"] or seg["loaded_before"]:
            continue
        for kind, sigs in (("script", seg["scripts"]), ("edit", seg["edits"])):
            for sig in sigs:
                if kind == "script" and sig.rsplit("/", 1)[-1] in developed:
                    continue
                row = by_sig.setdefault((kind, sig), {"sessions": set(), "turns": 0,
                                                      "prompts": [], "projects": set()})
                row["sessions"].add(path)
                row["projects"].add(os.path.basename(os.path.dirname(path)))
                row["turns"] += 1
                p = " ".join(seg["prompt"].split())
                if p and len(p) <= MAX_PROMPT_CHARS and p not in row["prompts"]:
                    row["prompts"].append(p)
    ranked = sorted(((k, v) for k, v in by_sig.items() if len(v["sessions"]) >= min_sessions),
                    key=lambda kv: (-len(kv[1]["sessions"]), -kv[1]["turns"], kv[0]))
    # Where the work happens decides where its skill lives: in one project it belongs in
    # that project's skills folder, across several it is general. Transcripts are stored per
    # project, so the folder a session sits in is the project, with no guessing.
    return [{"kind": k[0], "what": k[1], "sessions": len(v["sessions"]), "turns": v["turns"],
             "projects": sorted(v["projects"]), "prompts": v["prompts"][:3]}
            for k, v in ranked[:limit]]


def as_query_set(harvested):
    """The drafts in `evals/eval_queries.json` form, the shape `triggers.load` reads."""
    return ([{"query": p, "should_trigger": True} for p in harvested["positive"]]
            + [{"query": n["query"], "should_trigger": False}
               for n in harvested["near_miss"]])
