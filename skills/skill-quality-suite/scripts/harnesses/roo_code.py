#!/usr/bin/env python3
"""Roo Code. Source: https://roocodeinc.github.io/Roo-Code/features/skills

The page moved from docs.roocode.com (a permanent redirect by 23.09.2026). Read then: the
name has to match its directory "or the skill won't load", 1-64 characters, and the
description 1-1024. It does not mention `license` or `metadata`, which had been listed
here, and names no subdirectory convention - its example shows `templates/` - so the
`scripts/`, `references/`, `assets/` recorded here had nothing behind them either.
"""
from .base import REQUIRED, HarnessAdapter


class RooCode(HarnessAdapter):
    name = "roo-code"
    title = "Roo Code"
    docs = "https://roocodeinc.github.io/Roo-Code/features/skills"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".roo/skills/<name>/SKILL.md",
        ".agents/skills/<name>/SKILL.md",
        "~/.roo/skills/<name>/SKILL.md",
        "~/.agents/skills/<name>/SKILL.md",
    )
    discovery = ("frontmatter read at startup, the full file when a request matches; "
                 "project outranks global, and `.roo/` outranks `.agents/` at each level")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
    }
    dirs = ()
    # "Roo discovers these files on-demand when the instructions reference them"
    loads_linked_files = True
    limits = {"name": 64, "description": 1024}
    name_matches_dir = True
    notes = (
        "A `skills-<mode>/` folder next to each `skills/` targets one Roo mode and outranks "
        "the generic one, which has no equivalent elsewhere.",
        "No subdirectory is named; bundled files are found when the instructions point at "
        "them, so a directory SKILL.md links is fine and one it does not is a question.",
    )
