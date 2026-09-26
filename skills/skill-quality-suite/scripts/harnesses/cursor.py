#!/usr/bin/env python3
"""Cursor. Source: https://cursor.com/docs/context/skills

An earlier version of this adapter was built from Cursor's plugins page and claimed
skills reach Cursor only inside a plugin. Cursor's own skills page says otherwise: it
scans `.cursor/skills` and `.agents/skills` at both scopes, and reads `.claude/skills`
and `.codex/skills` as legacy locations. The wrong table reported a `.claude/skills`
path as unreadable here, which is an invented incompatibility - the one output this
module must never produce.

Read again 23.09.2026: `name` "Must match the parent folder name" (the adapter had not
said so), `license` is not among the documented fields (it had been listed), and the
subdirectories named are `scripts/`, `references/` and `assets/`. Plugins are still how a
skill arrives from a repository: "Skills aren't imported on their own. To bring skills in
from a GitHub repository, package them in a plugin".
"""
from .base import EXTENSION, OPTIONAL, REQUIRED, HarnessAdapter


class Cursor(HarnessAdapter):
    name = "cursor"
    title = "Cursor"
    docs = "https://cursor.com/docs/context/skills"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".cursor/skills/<name>/SKILL.md",
        ".agents/skills/<name>/SKILL.md",
        ".claude/skills/<name>/SKILL.md",
        ".codex/skills/<name>/SKILL.md",
        "~/.cursor/skills/<name>/SKILL.md",
        "~/.agents/skills/<name>/SKILL.md",
        "<plugin>/skills/<name>/SKILL.md",
    )
    discovery = ("the skills roots are walked recursively; a skill activates when the "
                 "context looks relevant, when typed with `/`, or through a Custom Mode")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
        "metadata": OPTIONAL,
        "disable-model-invocation": EXTENSION,
        "paths": EXTENSION,
        "icon": EXTENSION,
        "color": EXTENSION,
    }
    dirs = ("scripts", "references", "assets")
    limits = {}
    name_matches_dir = True
    notes = (
        "Reads `.claude/skills` and `.codex/skills` as legacy locations, so a skill written "
        "for either is found without moving.",
        "`paths` limits a skill to files matching a glob; `icon` and `color` are badge "
        "settings for Custom Modes. All four are Cursor's own.",
        "A skill from a GitHub repository is not imported on its own; it arrives packaged "
        "in a plugin published through a marketplace.",
        "`rules/*.mdc` with `globs` and `alwaysApply` is Cursor's other mechanism; it is "
        "not a skill and this suite does not check it.",
    )
