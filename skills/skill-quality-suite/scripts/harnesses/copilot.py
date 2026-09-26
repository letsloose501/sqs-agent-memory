#!/usr/bin/env python3
"""GitHub Copilot. Sources:
https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills
https://docs.github.com/en/copilot/concepts/agents/about-agent-skills

Read 23.09.2026. The concepts page names the locations and surfaces; the how-to page
carries the fields: `name` and `description` required, `license` optional, and
`allowed-tools` optional under Copilot's own tool names ("shell or bash"). It also covers
supporting files whole - "Copilot automatically discovers all of the files in the
skill's directory" - so no directory inside a skill is a portability question here,
where the adapter had reported every one of them as UNKNOWN. The name "Typically"
matches the directory: usual, not required.
"""
from .base import OPTIONAL, REQUIRED, HarnessAdapter


class Copilot(HarnessAdapter):
    name = "copilot"
    title = "GitHub Copilot"
    docs = "https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".github/skills/<name>/SKILL.md",
        ".claude/skills/<name>/SKILL.md",
        ".agents/skills/<name>/SKILL.md",
        "~/.copilot/skills/<name>/SKILL.md",
        "~/.agents/skills/<name>/SKILL.md",
    )
    discovery = ("loaded when relevant, across the cloud agent, code review, the CLI, the "
                 "app, and agent mode in VS Code and the JetBrains IDEs")

    fields = {
        "name": REQUIRED,
        "description": REQUIRED,
        "license": OPTIONAL,
        "allowed-tools": OPTIONAL,
    }
    dirs = ()
    reads_whole_folder = True
    limits = {}
    tool_namespace = "copilot"
    notes = (
        "The page names `.github/skills` as Copilot's own folder and reads `.claude/skills` "
        "and `.agents/skills` too.",
        "`allowed-tools` pre-approves Copilot's tools (`shell`, `bash`), not Claude Code's; "
        "the same field travels, the names in it do not.",
    )
