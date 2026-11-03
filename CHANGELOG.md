# Changelog

The version lives in `.claude-plugin/plugin.json`; a tag `vX.Y.Z` on a commit where it matches
publishes a release with the section below as its notes.

## Unreleased

- Memory use: `scripts/memory_usage.py` counts, from session transcripts, the sessions that opened
  each entry (Read, `memory_recall.py read`, cat/sed/head/Get-Content, also through Claude Code's
  per-project memory folder). It lists entries opened often but missing from the index and index
  lines opened in no session; sweeps that open everything (the review itself) are counted apart.
  Idea from ACE and REALM. `memory-review` phase 2 item 5.
- Lost facts: `scripts/memory_preservation.py` compares each entry modified in the window with its
  earlier version and lists numbers, dates and links that disappeared, gone from all memory or only
  moved. A translation keeps them, so a faithful rewrite passes. Exit 1 is a report, exit 2 a git
  failure. Idea from TrustMem. `memory-review` phase 2 item 6.
- Monthly outcome: `scripts/monthly_review.py` measures the share of the month's mistakes that
  resemble one recorded earlier, from git history, and appends it to `scripts/monthly.tsv`. A month
  with no mistakes is written as an empty share, not 0 %.
- `guard_memory_scope.py` blocks invisible characters (control, zero-width, bidi, tag; ZWJ allowed
  for emoji) in memory and vault writes, with no unlock: they are either an escape the Write/Edit
  argument decoded into a real control character, or a carrier for hidden instructions.
- Tests: 14 new cases; 10 targeted mutations of the new code, each turned its own test red.
- README: what the plugin gives the agent and the user, and an install table saying what each
  prerequisite is for.

- Transcript digest: `scripts/transcript_digest.py` does the mechanical half of phase 1 of
  `memory-review`. It picks the week by the last entry inside each transcript (not mtime), reads all
  projects but skips generated `*evals*` ones, keeps only the user's own messages, lists rejected
  tool calls and groups failed ones by signature across distinct sessions (`REPEAT` from two; a
  shell failure is keyed by its exit code and last output line, not the bare "Exit code N").
  Grepping raw transcripts matched the rules text that rides in every turn, so it found noise.
  Five tests, each shown to fail on a matching break of the script.
- Memory search: `scripts/memory_recall.py`. `recall` ranks all entries (project and journal
  ones too) with BM25 over SQLite FTS5 and answers with one line per hit, never the entry itself;
  `read --level abstract|outline|full` opens one entry as deep as needed. Several wordings are fused
  by their best reciprocal rank, so an English query and the user's own words work together and an
  entry written in one language is not outvoted by entries half-matching both. Standard library
  only, no index on disk. The session start hook prints the command with real paths.
- `memory_eval.py` scores the search on `eval/recall-cases.tsv` in the memory repo (top 3 and top 5,
  three new history columns; an older history file gets the new header). No reference set prints
  "not set up" and writes empty fields, not zeros. `memory-review` says how to grow the set and
  that a description names what the entry is for, not only the tool's name.
- Removed `grill-me`: it only called `grilling`, which runs on "grill me" by itself. The router
  now names `/agent-memory:grilling`.
- README: positioning covers the toolkit, skills grouped by job, measured search numbers, limits.
- Office files: `setup` stage 4b installs Anthropic's `document-skills` (docx, pptx, xlsx, pdf) with
  the user's consent, `router` sends Office work there. Not bundled: their license forbids
  redistribution.

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
