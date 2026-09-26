#!/usr/bin/env python3
"""Cline. Source: https://docs.cline.bot/customization/skills

Read again 23.09.2026: "Project skills: `.cline/skills/` (recommended),
`.clinerules/skills/`, `.claude/skills/`" - the last two were missing here, so a Claude
Code skill read as unreachable on Cline when it is not. The name "must exactly match the
directory name", which the adapter had not said.
"""
from .base import REQUIRED, HarnessAdapter


class Cline(HarnessAdapter):
    name = "cline"
    title = "Cline"
    docs = "https://docs.cline.bot/customization/skills"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".cline/skills/<name>/SKILL.md",
        ".clinerules/skills/<name>/SKILL.md",
        ".claude/skills/<name>/SKILL.md",
        "~/.cline/skills/<name>/SKILL.md",
    )
    discovery = ("name and description at the start of a conversation, the full file when "
                 "the request matches or the skill is called with `/`")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
    }
    dirs = ("docs", "templates", "scripts")
    limits = {}
    name_matches_dir = True
    notes = (
        "Documented subdirectories are `docs/`, `templates/` and `scripts/`; `references/` "
        "and `assets/` are not named.",
        "Reads `.claude/skills` in a project, so a Claude Code skill is found there without "
        "moving; the global folder is `~/.cline/skills` only.",
        "The documentation asks for the common cases first in the file, since it is read "
        "top-down, and for instructions under about 5k tokens.",
    )
