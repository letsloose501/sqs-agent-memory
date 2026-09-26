#!/usr/bin/env python3
"""The repairs that have exactly one correct answer.

A fixer earns its place only when the corrected text is forced by the broken text. A
description over the spec limit has no single right shortening, and a linter that
picks one for you deletes a trigger you needed - so that one stays a human's job and
is absent here. What is here is mechanical: the name the folder already dictates, the
characters that should never have been in the file.

Nothing is written without `--apply`. A dry run prints the same diff it would make.
"""
import re

from core import Finding
from security import strip_hidden

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FM_NAME = re.compile(r"^name:[ \t]*(.*)$", re.M)


def slugify(name):
    """The spec-legal form of a name: lowercase, latin, single inner hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return s.strip("-")


def plan(skill):
    """[(code, what changes, new SKILL.md text or None, new file map)] for this skill.

    Returns one entry per repair, each carrying the full replacement text, so the
    caller can print a dry run and apply the very same thing.
    """
    out = []
    if not skill.ok:
        return out

    # SP002 / SP004 / SP006 - the folder already says what the name has to be
    want = slugify(skill.folder)
    if skill.fm_raw is not None and want and skill.name != want:
        if not skill.name:
            code, what = "SP002", f"add `name: {want}`"
            new_fm = f"name: {want}\n{skill.fm_raw}"
            text = skill.text.replace(skill.fm_raw, new_fm, 1)
        else:
            code = "SP004" if NAME_RE.match(skill.name) else "SP006"
            what = f"`name: {skill.name}` -> `name: {want}`"
            new_fm = FM_NAME.sub(f"name: {want}", skill.fm_raw, count=1)
            text = skill.text.replace(skill.fm_raw, new_fm, 1)
        out.append((code, what, {"SKILL.md": text}))

    # SE004 - characters that make the rendered file differ from the read file
    stripped = {}
    for rel, text in skill.texts():
        clean, n = strip_hidden(text)
        if n:
            stripped[rel] = (n, clean)
    if stripped:
        total = sum(n for n, _ in stripped.values())
        out.append(("SE004", f"strip {total} hidden character(s) from "
                             f"{', '.join(sorted(stripped))}",
                    {rel: t for rel, (_, t) in stripped.items()}))
    return out


def apply(skill, entries):
    """Write the planned replacements. Returns the paths actually written."""
    written = []
    for _, _, files in entries:
        for rel, text in files.items():
            path = f"{skill.root}/{rel}"
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            written.append(rel)
    return written


def check(skill, cfg=None):
    """The planned repairs as findings, so a dry run reads like every other report."""
    return [Finding(code, what + " (run `sqs.py fix --apply` to write it)", severity="info")
            for code, what, _ in plan(skill)]
