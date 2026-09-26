#!/usr/bin/env python3
"""OpenCode. Source: https://opencode.ai/docs/skills/

Read again 23.09.2026 and unchanged: the six locations, the five fields, "Unknown
frontmatter fields are ignored", a name of 1-64 characters matching its directory, and a
description of 1-1024.
"""
from .base import OPTIONAL, REQUIRED, HarnessAdapter


class OpenCode(HarnessAdapter):
    name = "opencode"
    title = "OpenCode"
    docs = "https://opencode.ai/docs/skills/"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".opencode/skills/<name>/SKILL.md",
        ".claude/skills/<name>/SKILL.md",
        ".agents/skills/<name>/SKILL.md",
        "~/.config/opencode/skills/<name>/SKILL.md",
        "~/.claude/skills/<name>/SKILL.md",
        "~/.agents/skills/<name>/SKILL.md",
    )
    discovery = ("walks up from the working directory to the git worktree root collecting "
                 "matches, then adds the global folders; loaded on demand through a native "
                 "skill tool")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
        "license": OPTIONAL,
        "compatibility": OPTIONAL,
        "metadata": OPTIONAL,
    }
    dirs = ("scripts", "references", "assets")
    limits = {"name": 64, "description": 1024}
    name_matches_dir = True
    # Stated outright in the documentation, which is why another harness's extension is
    # merely inert here rather than a question mark.
    ignores_unknown_fields = True
    notes = (
        "Reads `.claude/skills` and `~/.claude/skills` directly, so a Claude Code skill "
        "needs no move to be found.",
        "Skill names have to be unique across every location searched, not just within one.",
        "`opencode.json` can allow, deny or ask per skill name, and an agent can switch the "
        "skill tool off entirely.",
    )
