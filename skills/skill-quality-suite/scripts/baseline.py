#!/usr/bin/env python3
"""The findings a repository has agreed to live with, for now.

A suite switched on over an existing tree reports three hundred findings, the build
goes red, and the gate is turned off the same afternoon. A baseline is how it survives
that first day: everything already there is recorded once, and from then on the gate
fails only on what is **new**.

What it is not: a way to make findings go away. The recorded ones stay in the file,
counted and dated, and `sqs.py baseline show` lists them. Silencing a rule is the
config's job and needs a reason written next to it; this is a queue, not a bin.

Findings are matched by fingerprint, which deliberately leaves the line number out -
a finding that moved down the file because something was inserted above it is the
same finding, and a baseline that says otherwise turns every unrelated edit into a
red build.
"""
import datetime
import json
import os

from report import fingerprint

FILENAME = ".sqs-baseline.json"


def path_for(root, override=None):
    return override or os.path.join(root, FILENAME)


def load(root, override=None):
    path = path_for(root, override)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(root, results, override=None, note=""):
    """Write every current finding into the baseline. Returns (path, count)."""
    entries = {}
    for folder, found in results:
        for f in found:
            entries[fingerprint(f)] = {
                "code": f.code, "skill": folder, "file": f.where,
                "severity": f.severity, "message": f.msg,
            }
    payload = {
        "tool": "skill-quality-suite",
        "created": datetime.date.today().isoformat(),
        "note": note or "Findings present when the gate was switched on. New findings "
                        "fail the build; these are a queue to work through.",
        "findings": entries,
    }
    path = path_for(root, override)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return path, len(entries)


def split(results, baseline):
    """(new results, how many baselined findings were suppressed, fixed entries).

    `fixed` is the other half of the point: a finding in the baseline that no longer
    appears has been dealt with, and saying so is what stops the file growing stale in
    silence.
    """
    known = set((baseline or {}).get("findings", {}))
    seen, fresh, suppressed = set(), [], 0
    for folder, found in results:
        keep = []
        for f in found:
            fp = fingerprint(f)
            seen.add(fp)
            if fp in known:
                suppressed += 1
            else:
                keep.append(f)
        fresh.append((folder, keep))
    fixed = [v for k, v in (baseline or {}).get("findings", {}).items() if k not in seen]
    return fresh, suppressed, fixed


def summary(suppressed, fixed, baseline):
    created = (baseline or {}).get("created", "?")
    line = f"baseline: {suppressed} known finding(s) from {created}"
    if fixed:
        line += (f" · {len(fixed)} gone since "
                 f"({', '.join(sorted({e['code'] for e in fixed}))}) - "
                 f"`sqs.py baseline create` to record that")
    return line
