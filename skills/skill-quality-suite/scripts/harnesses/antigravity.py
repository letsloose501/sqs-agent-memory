#!/usr/bin/env python3
"""Google Antigravity. Source: https://antigravity.google/docs/skills?tab=ide

The page moved from /docs/ide/skills/ and the global location moved with it: read on
23.09.2026 it names `~/.gemini/config/skills` for the IDE and Antigravity 2.0,
`~/.gemini/antigravity-cli/skills` for the CLI, and keeps `~/.gemini/antigravity/skills`
as legacy - the only global path this adapter had. `name` is still optional ("Defaults to
the folder name if not provided"); `license` and `metadata` are not mentioned and came
out, having been listed as optional with nothing behind them.
"""
from .base import OPTIONAL, REQUIRED, HarnessAdapter


class Antigravity(HarnessAdapter):
    name = "antigravity"
    title = "Antigravity"
    docs = "https://antigravity.google/docs/skills?tab=ide"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".agents/skills/<name>/SKILL.md",
        ".agent/skills/<name>/SKILL.md",
        "~/.gemini/config/skills/<name>/SKILL.md",
        "~/.gemini/antigravity-cli/skills/<name>/SKILL.md",
        "~/.gemini/antigravity/skills/<name>/SKILL.md",
        "~/.gemini/antigravity-cli/plugins/<plugin>/skills/<name>/SKILL.md",
    )
    discovery = ("names and descriptions at the start of a conversation, the full SKILL.md "
                 "when the task looks relevant; every skill also becomes a `/<name>` command")

    fields = {
        # One of two harnesses in the registry where `name` is optional: left out, it is
        # taken from the folder. A skill relying on that is invalid in most others.
        "name": OPTIONAL,
        "description": REQUIRED,
    }
    dirs = ("scripts", "examples", "resources")
    limits = {}
    notes = (
        "`.agent/skills` and `~/.gemini/antigravity/skills` are kept working for older "
        "layouts; `.agents/skills` and `~/.gemini/config/skills` are the current ones.",
        "Documented subdirectories are `scripts/`, `examples/` and `resources/` - not the "
        "`references/` and `assets/` other harnesses name.",
    )
