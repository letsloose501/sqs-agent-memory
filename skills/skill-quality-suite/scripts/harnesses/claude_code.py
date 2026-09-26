#!/usr/bin/env python3
"""Claude Code. Source: https://code.claude.com/docs/en/skills

Checked 23.09.2026 against the skills page itself; before that the adapter pointed at
the product's repository and carried the specification's rules as if they were Claude
Code's. The page says otherwise on three counts: `name` is optional and "Defaults to the
directory name"; in a personal or project skill it "sets only the display label", and
"the command still comes from the directory name" - so nothing here requires the two to
match; and no 64- or 1024-character ceiling is stated. What is stated is that the
combined `description` and `when_to_use` are "truncated at 1,536 characters in the skill
listing".
"""
from .base import EXTENSION, OPTIONAL, HarnessAdapter


class ClaudeCode(HarnessAdapter):
    name = "claude-code"
    title = "Claude Code"
    docs = "https://code.claude.com/docs/en/skills"
    checked = "2026-09-23"
    supports_skills = True

    locations = (
        ".claude/skills/<name>/SKILL.md",
        "<subdir>/.claude/skills/<name>/SKILL.md",
        "~/.claude/skills/<name>/SKILL.md",
        "<plugin>/skills/<name>/SKILL.md",
    )
    discovery = ("name and description are held in context; the body and its references "
                 "load when the description matches, or when `/<directory-name>` is typed")

    fields = {
        # optional, defaulting to the directory name; `description` is "recommended"
        "name": OPTIONAL,
        "description": OPTIONAL,
        "license": OPTIONAL,
        "compatibility": OPTIONAL,
        "metadata": OPTIONAL,
        "allowed-tools": OPTIONAL,
        "when_to_use": EXTENSION,
        "argument-hint": EXTENSION,
        "arguments": EXTENSION,
        # Not Claude Code's alone: Cursor documents the same field.
        "disable-model-invocation": EXTENSION,
        "user-invocable": EXTENSION,
        "disallowed-tools": EXTENSION,
        "model": EXTENSION,
        "effort": EXTENSION,
        "context": EXTENSION,
        "agent": EXTENSION,
        "background": EXTENSION,
        "hooks": EXTENSION,
        # Cursor documents a field of the same name, also a glob list
        "paths": EXTENSION,
        "shell": EXTENSION,
    }
    # The page shows `scripts/` in its example and names no other subdirectory.
    dirs = ("scripts",)
    # "Reference supporting files from `SKILL.md` so Claude knows what each file contains
    # and when to load it"
    loads_linked_files = True
    limits = {"compatibility": 500}
    # Documented not to be required: the directory names the command, `name` the label.
    name_matches_dir = False
    tool_namespace = "claude-code"
    # The page's "String substitutions" and "dynamic context injection" sections, read
    # 23.09.2026. Nine other harness pages were asked the same question and none
    # mentions either, so everywhere else these come back UNKNOWN, not unsupported.
    body_syntax = ("$ARGUMENTS", "$N", "$name", "!`command`",
                   "${CLAUDE_SESSION_ID}", "${CLAUDE_EFFORT}", "${CLAUDE_SKILL_DIR}",
                   "${CLAUDE_PROJECT_DIR}", "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PLUGIN_DATA}")
    notes = (
        "`name` only labels a personal or project skill; the command is the directory "
        "name. In a plugin, `name` sets the command segment after the plugin prefix.",
        "`description` and `when_to_use` together are cut at 1,536 characters in the "
        "listing the model chooses from - the key use case has to come first.",
        "`disable-model-invocation: true` removes the description from the agent's reach: "
        "the skill costs no context and only a human can call it.",
        "Also found: nested `.claude/skills` under a subdirectory being worked in, "
        "directories added with `--add-dir`, and a managed-settings location.",
    )
