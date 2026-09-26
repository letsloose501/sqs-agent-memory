#!/usr/bin/env python3
"""A mistakes journal, read for what it says about each skill.

The journal is a folder of short entries, one per mistake, each in four fields:

    MISTAKE: what was done wrong
    WHY:     what caused it
    FIX:     how it was fixed then
    PATTERN: how not to repeat it - the part worth keeping

It is written by the agent the moment it notices it was wrong, and read in batches: a
periodic pass groups the entries, raises a repeat one step (once is noise, twice a rule,
three times a script or a gate) and clears the folder. So the folder alone shows only
what has not been reviewed yet. When it is under git, the entries already cleared are
still in its history, and they are read too - a mistake that keeps coming back across
reviews is exactly what a count over the folder alone would miss.

Nothing here judges an entry. A skill is matched only where an entry names it in a form
that cannot be ordinary prose: in backticks, as `/name`, as a path into the skill's own
folder, or next to the word skill. Measured on a real journal of 88 entries: a plain word
match credited the English verb "commit" to a skill named `commit`, "the video had" to a
skill named `video`, and a project folder that shares a skill's name to that skill.
"""
import os
import re
import subprocess

# Both spellings a journal has been seen in. A field runs to the next field or the end.
FIELD_NAMES = {"MISTAKE": "mistake", "ОШИБКА": "mistake", "WHY": "why", "ПОЧЕМУ": "why",
               "FIX": "fix", "РЕШЕНИЕ": "fix", "PATTERN": "pattern", "ПАТТЕРН": "pattern"}
FIELD_RE = re.compile(r"^[ \t>*_-]*\**(" + "|".join(FIELD_NAMES) + r")\**[ \t]*:\**", re.M | re.I)
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
SKILL_DIRS = r"(?:references|scripts|assets|evals|templates|SKILL\.md)"

# The step a repeat earns, from the review that owns the journal: one entry is noise until
# it repeats, two alike are a rule in the skill, three a script or a gate the agent cannot
# skip. It is printed as a ladder and never applied to a count: on the real journal, the
# four entries naming one skill were four different mistakes, and a count that read
# "4 -> gate" would have ordered a gate for nothing. Whether entries are alike is read off
# their patterns, by whoever reads the report.
LADDER = "once is noise; two alike, a rule in the skill; three alike, a script or a gate"


def fields(text):
    """{"mistake", "why", "fix", "pattern"} out of one entry; missing ones are absent."""
    out, marks = {}, list(FIELD_RE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        key = FIELD_NAMES[m.group(1).upper()]
        value = " ".join(text[m.end():end].split())
        if value and key not in out:
            out[key] = value
    return out


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except OSError:
        return False, ""
    return r.returncode == 0, r.stdout


def entries(journal_dir):
    """[{"name", "date", "text", "fields", "reviewed"}] - the folder, then its git history.

    `reviewed` marks an entry no longer in the folder: the review cleared it, and only git
    remembers it. Its text is the version that was added, which is what the review read.
    """
    if not journal_dir or not os.path.isdir(journal_dir):
        return []
    out, seen = [], set()
    for name in sorted(os.listdir(journal_dir)):
        path = os.path.join(journal_dir, name)
        if not name.endswith(".md") or not os.path.isfile(path) or name.lower() == "readme.md":
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        seen.add(name)
        out.append(_entry(name, text, reviewed=False))
    ok, log = _git(journal_dir, "log", "--diff-filter=A", "--format=@%H", "--name-only",
                   "--relative", "--", ".")
    if ok:
        sha = None
        for line in log.splitlines():
            line = line.strip()
            if line.startswith("@"):
                sha = line[1:]
                continue
            name = os.path.basename(line)
            if not line.endswith(".md") or name in seen or name.lower() == "readme.md":
                continue
            got, text = _git(journal_dir, "show", f"{sha}:./{line}")
            if got:
                seen.add(name)
                out.append(_entry(name, text, reviewed=True))
    return out


def _entry(name, text, reviewed):
    m = DATE_RE.match(name)
    return {"name": name, "date": m.group(1) if m else "", "text": text,
            "fields": fields(text), "reviewed": reviewed}


def names_skill(text, name):
    """Whether an entry names this skill in a form ordinary prose does not take."""
    n = re.escape(name)
    forms = [
        "`/?" + n + "`",                                        # `name`, `/name`
        r"skills[/\\]" + n + r"(?![\w-])",                      # skills/name
        r"(?<![\w:/-])/" + n + r"(?![\w-])",                    # /name, not a:name, a/name
        r"(?<![\w-])" + n + r"[/\\]" + SKILL_DIRS,              # name/references/...
        r"(?:скилл\w*|skill)\s+[`«\"']?" + n + r"(?![\w-])",    # skill name
        r"(?<![\w:-])" + n + r"[`»\"']?\s+(?:skill|скилл)",     # name skill
    ]
    return re.search("|".join(forms), text, re.I) is not None


def for_skill(skill, journal_dir, limit=5):
    """What the journal says about one skill: the count, the step it earns, the patterns."""
    names = {skill.folder, (skill.name or skill.folder).split(":")[-1]}
    hits = [e for e in entries(journal_dir) if any(names_skill(e["text"], n) for n in names)]
    hits.sort(key=lambda e: e["date"], reverse=True)
    return {"journal": journal_dir, "count": len(hits),
            "open": sum(1 for e in hits if not e["reviewed"]),
            "entries": [{"name": e["name"], "date": e["date"], "reviewed": e["reviewed"],
                         "pattern": e["fields"].get("pattern") or e["fields"].get("mistake")
                         or " ".join(e["text"].split())[:200]}
                        for e in hits[:limit]]}


def per_skill(skills, journal_dir):
    """{skill folder: (entries, still in the folder)} for every skill the journal names."""
    all_entries = entries(journal_dir)
    out = {}
    for s in skills:
        names = {s.folder, (s.name or s.folder).split(":")[-1]}
        hits = [e for e in all_entries if any(names_skill(e["text"], n) for n in names)]
        if hits:
            out[s.folder] = (len(hits), sum(1 for e in hits if not e["reviewed"]))
    return out, len(all_entries)


def resolve(cfg, flag=None):
    """The journal folder: the flag, else `mistakes` in `sqs.config.json`, else none."""
    path = flag or cfg.get("mistakes")
    return os.path.abspath(os.path.expanduser(path)) if path else None
