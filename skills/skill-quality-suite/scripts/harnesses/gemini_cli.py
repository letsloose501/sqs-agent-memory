#!/usr/bin/env python3
"""Gemini CLI. Sources:
https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md
https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/creating-skills.md
https://github.com/google-gemini/gemini-cli/blob/main/docs/extensions/index.md

Read again 23.09.2026. The creating-skills page names `name` - "This should match the
directory name" - and `description`, and no other frontmatter field; `license` and
`metadata` had been listed here without a line behind them. The precedence inside a tier
is quoted from skills.md: "the `.agents/skills/` alias takes precedence over the
`.gemini/skills/` directory".
"""
from .base import REQUIRED, HarnessAdapter


class GeminiCLI(HarnessAdapter):
    name = "gemini-cli"
    title = "Gemini CLI"
    docs = "https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".agents/skills/<name>/SKILL.md",
        ".gemini/skills/<name>/SKILL.md",
        "~/.agents/skills/<name>/SKILL.md",
        "~/.gemini/skills/<name>/SKILL.md",
        "<extension>/skills/<name>/SKILL.md",
    )
    discovery = ("four tiers, built-in then extension then user then workspace; within a "
                 "tier `.agents/skills` wins over `.gemini/skills`. Activation goes through "
                 "an `activate_skill` call that asks the human first")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
    }
    dirs = ("scripts", "references", "assets")
    # The published pages name the fields and do not state ceilings, so none are checked.
    limits = {}
    # "should match" - guidance rather than a refusal, so it is not enforced as one
    name_matches_dir = None
    notes = (
        "Activation is consented to by the human each time, so a skill that assumes it is "
        "already loaded will misread the situation.",
        "On activation the skill's own directory is added to the agent's allowed paths, "
        "which is what makes bundled assets readable.",
        "The name \"should match the directory name\" - stated as advice, not as a refusal.",
    )
