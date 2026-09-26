# agent-memory

[![ci](https://github.com/letsloose501/sqs-agent-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/letsloose501/sqs-agent-memory/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/letsloose501/sqs-agent-memory)](https://github.com/letsloose501/sqs-agent-memory/releases)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

A Claude Code plugin that gives the agent a memory that outlives the session, and gives you a
knowledge base that fills itself from what you read and watch.

- **Agent memory in git.** A private repository of small markdown facts: who you are, how you want
  the work done, decisions and their reasons, tool pitfalls. Claude reads its index at the start of
  every session, in every project, and writes to it as it learns. Every change is a commit, so any
  edit can be seen and reverted.
- **Working rules loaded every session.** `claude/rules.md` in the memory repository: how to verify
  before saying "verified", why a number is either found or absent, why decisions come with their
  grounds. Edit them; they are yours.
- **An Obsidian vault as the knowledge base.** Notes written from simple to complex, linked to each
  other, with sources checked on the web, from text, videos and PDFs.
- **MemPalace as the vault index.** One summary card per note, so a note is found by the question
  you would ask, not by the words in its title.
- **Memory where it is used.** Reading a file brings in what memory knows about it; every entry
  says whether the user stated it, the work showed it, or the agent inferred it; approaches that
  failed are kept as dead ends so nobody re-derives them.
- **Hooks that hold the line.** Secrets never reach memory, broken wiki links block the end of a
  turn, a `git push` that did not land is reported, long heredocs and a PowerShell delete that would
  silently do nothing are stopped.

## What is inside

| Skill | What it does |
|---|---|
| `setup` | first-time setup: memory repo + private GitHub remote, starter vault, MemPalace config |
| `notes` | turns raw text into vault notes: simple to complex, links, dictionary, cards, study plans |
| `video` | video link to transcript (captions or Whisper) to notes; frames of a piece when the text is blind |
| `pdf` | any PDF to markdown, scans read by eye, then notes |
| `vault-index` | fills the MemPalace index in batches of summary cards |
| `mistake` | records a mistake the agent made and fixed, for the weekly review |
| `memory-review` | weekly pass: a deterministic pre-sort of the journal by failure class, repeats across sessions, stale facts, dead ends; empties the journal |
| `clean-memory` | tidy memory or the palace now, nothing deleted without a yes |
| `browser` | scripted work with websites through a separate Chrome, the site's own API before the DOM |
| `graphics` | template infographics (AntV, vendored) and charts from real data, offline |
| `latex` | compilable LaTeX: documents, snippets, Beamer slides |
| `commit` | safe commits: read the diff, add only your files, respect the repo's conventions |
| `skill-quality-suite` | lint, validate and security-scan Agent Skills ([SQS](https://github.com/letsloose501/sqs-skills)) |
| `router` | which skill for which task, and the chains they run in |
| `grilling`, `grill-me`, `to-spec`, `to-tickets`, `implement`, `tdd`, `codebase-design` | from an idea to shipped code, adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) |

| Hook | When | What |
|---|---|---|
| `session_start.py` | session start | prints the working rules; after a compaction, what was in progress |
| `guard_memory_scope.py` | before Write/Edit | keeps `<private>` text out of memory and the vault, blocks secrets, requires `source` on entries, protects README/SCOPES |
| `file_context.py` | before Read | when a file is read, surfaces the memory entries and journal lessons that name it (once per session) |
| `guard_heredoc.py` | before Bash | blocks long heredocs, which break silently |
| `guard_literalpath.py` | before PowerShell | rewrites a delete of a `[bracketed]` name to `-LiteralPath` |
| `check_push_landed.py` | after Bash/PowerShell | compares HEAD with the remote after `git push` |
| `verify_vault.py` | after edits / at stop | blocks the end of a turn on new broken wiki links |
| `check_skills.py` (SQS) | after edits / at stop | checks the structure of skills you edit in `~/.claude/skills` |
| `memory_autocommit.py` | at stop | commits memory changes and pushes to the private remote |

## Install

Step by step, including Obsidian, a GitHub account and MemPalace: **[docs/install.md](docs/install.md)**.

Short version, with git, uv, MemPalace and a GitHub login already in place:

```text
/plugin marketplace add letsloose501/sqs-agent-memory
/plugin install agent-memory@agent-memory
/agent-memory:setup
```

Requirements: Claude Code, git, [uv](https://docs.astral.sh/uv/), [MemPalace](https://github.com/MemPalace/mempalace)
(`uv tool install mempalace`), [Obsidian](https://obsidian.md). Windows, macOS and Linux; the
PowerShell guard only acts on Windows.

## How the pieces fit

```
you work with Claude ──> memory repo (git, private remote)    what it knows about you
        │                    MEMORY.md index + entries + claude/rules.md + mistakes/
        │
        ├── text / video / PDF ──> notes ──> Obsidian vault      what is known about the world
        │                                      │
        │                                      └──> MemPalace cards   how to find it by meaning
        │
        └── hooks: guard memory, check links, check pushes, commit memory
```

Rule of thumb for where something goes: a fact about you or a decision with its reason goes to
memory; knowledge about the world goes to the vault; a procedure that is always done the same way
goes into a skill or a script. If it can be recovered from the vault or the git log, it does not
belong in memory.

## Privacy

Everything stays on your machine except what you choose to push: the memory repository goes to a
**private** GitHub repository you create during setup. MemPalace runs locally; its search model runs
on your CPU or GPU. The video skill sends audio to Groq only if you add a Groq key and use tier 3.

## License

Apache-2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Third-party parts keep their own licenses
(MIT for Matt Pocock's skills and AntV Infographic), listed in NOTICE. Ideas taken without code:
file context on Read and `<private>` tags from [claude-mem](https://github.com/thedotmack/claude-mem),
outcome-based journal reflection and provenance tags from [graphify](https://github.com/Graphify-Labs/graphify).
