#!/usr/bin/env python3
"""Windsurf (Cascade), now Devin Desktop. Source: https://docs.devin.ai/desktop/cascade/skills

The Windsurf page redirected there by 23.09.2026, and the layout moved with the name:
`.devin/skills` is preferred and `.windsurf/skills` is legacy, the managed tier is under
Devin paths, and `.claude/skills` is read only "If you have enabled Claude Code config
reading". No frontmatter field beyond `name` and `description` is mentioned, so the
`license` and `metadata` listed here came out. Supporting files are covered whole: "These
files become available to Cascade when the skill is invoked".
"""
from .base import REQUIRED, HarnessAdapter


class Windsurf(HarnessAdapter):
    name = "windsurf"
    title = "Windsurf"
    docs = "https://docs.devin.ai/desktop/cascade/skills"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".devin/skills/<name>/SKILL.md",
        ".windsurf/skills/<name>/SKILL.md",
        ".agents/skills/<name>/SKILL.md",
        ".claude/skills/<name>/SKILL.md",
        "~/.config/devin/skills/<name>/SKILL.md",
        "~/.codeium/windsurf/skills/<name>/SKILL.md",
        "~/.agents/skills/<name>/SKILL.md",
        "~/.claude/skills/<name>/SKILL.md",
    )
    discovery = ("name and description only, until Cascade decides to invoke the skill or "
                 "it is named with `@skill-name`")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
    }
    dirs = ()
    reads_whole_folder = True
    limits = {}
    notes = (
        "`.claude/skills` and `~/.claude/skills` are read only with Claude Code config "
        "reading switched on; `.agents/skills` always.",
        "`.devin/skills` is the current folder, `.windsurf/skills` the legacy one.",
        "A machine-wide tier for managed installs: `/Library/Application Support/Devin/skills` "
        "on macOS, `/etc/devin/skills` on Linux, `C:\\\\ProgramData\\\\Devin\\\\skills` on "
        "Windows.",
    )
