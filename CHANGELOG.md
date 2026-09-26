# Changelog

The version lives in `.claude-plugin/plugin.json`; a tag `vX.Y.Z` on a commit where it matches
publishes a release with the section below as its notes.

## Unreleased

- Bundled SQS 2.2.0: a missing path into a tool's own folder (`~/.claude`, `~/.config/<tool>`,
  `~/.mempalace`) is ST017, a warning, instead of ST011; the three `sqs-allow-file: ST011` waivers
  that worked around it are gone, and CI runs the v2.2.0 action.

## 0.0.1 - 2026-09-26

First public version.

- Agent memory in a git repository: index, entries with `type` and `source`
  (stated / observed / inferred), working rules loaded at every session start, a mistakes journal
  with dead ends.
- Hooks: memory scope guard (secrets, entry format, protected files, `<private>` text kept out of
  memory and the vault), memory context when a file is read, long heredoc guard, PowerShell
  `-LiteralPath` rewrite, push-landed check, vault link gate, skill structure check, memory autocommit.
- Skills: setup, notes, video, pdf, vault-index, mistake, memory-review (with a deterministic journal
  pre-sort), clean-memory, browser, graphics, latex, commit, router, skill-quality-suite, and
  adapted Matt Pocock skills (grilling, grill-me, to-spec, to-tickets, implement, tdd, codebase-design).
- MemPalace as the Obsidian vault index, with install and embedder configuration docs.
