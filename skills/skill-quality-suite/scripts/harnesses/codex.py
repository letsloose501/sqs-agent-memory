#!/usr/bin/env python3
"""OpenAI Codex. Source: https://learn.chatgpt.com/docs/build-skills

The page moved from developers.openai.com/codex/skills (a permanent redirect by
23.09.2026). It names two frontmatter fields - "The `SKILL.md` file must include `name`
and `description`" - and none besides; per-skill settings live in `agents/openai.yaml`,
not in the frontmatter. `license` and `metadata` sat here as optional without a line
behind them, and came out when the page was read.
"""
from .base import REQUIRED, HarnessAdapter


class Codex(HarnessAdapter):
    name = "codex"
    title = "Codex"
    docs = "https://learn.chatgpt.com/docs/build-skills"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".agents/skills/<name>/SKILL.md",
        "<repo-root>/.agents/skills/<name>/SKILL.md",
        "~/.agents/skills/<name>/SKILL.md",
        "/etc/codex/skills/<name>/SKILL.md",
    )
    discovery = ("explicit with `$skill-name`, or selected from the description; the "
                 "discovery listing is capped at 2% of the context window or 8000 characters")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
    }
    dirs = ("scripts", "references", "assets", "agents")
    limits = {}
    name_matches_dir = None
    notes = (
        "`agents/openai.yaml` is the Codex-side switch: `policy.allow_implicit_invocation: "
        "false` leaves the skill reachable by name only; the same file carries display "
        "settings and declared tool dependencies.",
        "The 8000-character discovery budget is shared by every installed skill's "
        "description, so a long description here costs the other skills their visibility.",
    )
