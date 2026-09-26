# agent-memory

[![ci](https://github.com/letsloose501/sqs-agent-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/letsloose501/sqs-agent-memory/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/letsloose501/sqs-agent-memory)](https://github.com/letsloose501/sqs-agent-memory/releases)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**A memory, a knowledge vault and a working toolkit for Claude Code, built so you can read,
diff and measure what it does.**

Three things an agent lacks out of the box, in one plugin:

- **It forgets.** Memory here is plain Markdown in your own git repository, found by content and
  scored on questions you write, so a change that makes it worse shows up as a number.
- **It learns nothing from what you read.** Videos, PDFs, articles and raw notes become linked
  notes in an Obsidian vault, sources checked, indexed so a note is found by the question you
  would ask.
- **Its tools break quietly.** The skills and hooks here were written from real runs, carry the
  traps those runs hit, and check their own output: a PDF page with no text layer, a video already
  processed, a push that did not land, a wiki link that points nowhere, a PowerShell delete that
  would silently do nothing.

## Why the memory is different

- **You can read every byte of it.** One Markdown file per fact, one line per fact in the index.
  Every change is a git commit to a private repository you own: see it, diff it, revert it. The
  search index is built for one call and thrown away; there is nothing else to trust.
- **It is measured, not promised.** `memory_eval.py` scores search on your own reference
  questions and appends the result to a history file, next to index size, stale facts and entries
  nobody can reach. Every hook is tested both ways on three operating systems in CI, and the tests
  were themselves checked against deliberate breakage of the code they guard.
- **Hooks refuse, they do not persuade.** A secret never reaches memory, text you mark
  `<private>` never gets written down, a `git push` that did not land is reported, a new broken
  wiki link blocks the end of a turn. A rule in a prompt can be forgotten; a hook that exits 2 cannot.
- **Every fact says where it came from.** An entry is `stated` by you, `observed` in the work, or
  `inferred` by the agent. Inferred entries are hypotheses until confirmed, and the weekly review
  treats them that way.
- **Two languages, one memory.** You talk in your language, entries are mostly English. The agent
  searches with both wordings at once, and an entry written in one language is not outvoted by
  entries half-matching both.

## Measured

On the author's memory: 150 entries, about half of them still in Russian, 34 reference questions
worded without the entries' title words.

| | top 3 | top 5 |
|---|---|---|
| first run: mostly English wordings, index lines not used | 23 / 34 | 26 / 34 |
| English and Russian wordings, index lines used, ranks summed | 28 / 34 | 30 / 34 |
| wordings fused by their best rank | 31 / 34 | 32 / 34 |
| after rewriting two weak descriptions | 33 / 34 | 34 / 34 |
| 12 held-out questions, written afterwards | 12 / 12 | 12 / 12 |

The two description rewrites were made against the reference set itself, which is why the
held-out set exists. Trigram matching, and fusing it with word matching, scored lower than word
matching alone, so it is not the default. A search takes about 0.4 s including interpreter start
(Windows, one run). Your numbers will differ: write your own questions in `eval/recall-cases.tsv`
and the review will grow them from real sessions.

## How it works

```
you work with Claude ──> memory repo (git, private remote)    what it knows about you
        │                    MEMORY.md index + entries + claude/rules.md + mistakes/
        │                    └── memory_recall.py: search by content, open by level
        │
        ├── text / video / PDF ──> notes ──> Obsidian vault      what is known about the world
        │                                      │
        │                                      └──> MemPalace cards   how to find it by meaning
        │
        └── hooks: guard memory, check links, check pushes, commit memory
```

**Memory.** Claude Code loads `MEMORY.md` into every session and reads only its first 200 lines
or 25 KB. The plugin keeps the index under 150 lines and 20 KB, and finds everything else by
content: `memory_recall.py recall "<English>" "<your words>"` answers with one line per hit (name,
type, description, the line that matched) and pastes nothing; `read <name> --level
abstract|outline|full` opens one entry only as deep as the task needs. The session start hook
prints the exact command, so the agent knows the search exists. Ranking is BM25 over SQLite FTS5
with an English stemmer and Russian ending stripping, from the Python standard library.

**Rules.** `claude/rules.md` in the memory repository is printed at every session start: how to
verify before saying "verified", why a number is either found or absent, why a decision comes with
its grounds. They are yours to edit.

**Vault.** Notes are written from simple to complex, linked to each other, with sources checked on
the web, from text, videos and PDFs. MemPalace keeps one summary card per note, searched by meaning
on your own CPU or GPU.

**Upkeep.** Mistakes the agent made and fixed go to a journal. A weekly review sorts it by failure
class, finds what repeated across sessions, retires stale facts, fixes descriptions search could
not match, keeps failed approaches as dead ends, and proposes, never performs, deletions.

Rule of thumb for where something goes: a fact about you or a decision with its reason goes to
memory; knowledge about the world goes to the vault; a procedure that is always done the same way
goes into a skill or a script. If it can be recovered from the vault or the git log, it does not
belong in memory.

## Compared with

- **Claude Code's built-in auto memory.** This plugin builds on it: the same `MEMORY.md`, pointed
  at a git repository shared by all your projects. It adds history you can revert, rules at every
  session start, search past the index ceiling, guards on what gets written, and the measurements.
- **[tigerless-labs/agent-memory](https://github.com/tigerless-labs/agent-memory).** A full memory
  runtime around the same core ideas (Markdown as the truth, a rebuildable FTS5 index, answers by
  path, then reading by level), with its own store layout, automatic distillation at session end
  and support for Codex CLI. Pick it if you want one store across several agents and automatic
  capture; pick this plugin if you want a memory you curate with the agent, a knowledge vault and
  a toolkit next to it, and hooks that hold the line. The staged reading here follows its design.

## The toolkit

Twenty skills, grouped by the job. `router` knows the chains between them and names the route
when a task spans several.

**Knowledge in: from anything you read or watch to a linked note**

| Skill | What it does, and what sets it apart |
|---|---|
| `notes` | raw text to an Obsidian note that goes from simple to complex, with sources checked on the web, links to existing notes, a dictionary and spaced-repetition cards; reads the vault first so it does not duplicate |
| `video` | a video link to a transcript on a three-rung ladder (ready captions, captions by another route, Whisper), a registry that catches a video already processed, and frames of a piece when the words alone do not say what is on screen |
| `pdf` | any PDF, including scans: finds pages with no text layer and reads them by eye from a render instead of trusting OCR, then hands the text to `notes` |
| `vault-index` | writes a MemPalace summary card per note, saying what question the note answers |
| `graphics` | infographics from ready templates (lists, comparisons, funnels, roadmaps) and charts from real data, offline |
| `latex` | compilable LaTeX: theorems and proofs, derivations, tables, TikZ, Beamer slides |

**Office files**

Word, PowerPoint and Excel go through Anthropic's own
[`document-skills`](https://github.com/anthropics/skills) (`docx`, `pptx`, `xlsx`, plus a `pdf` for
editing PDFs). `setup` offers to install them and `router` sends Office work there. They are not
copied into this plugin because their license forbids redistribution; in the Claude desktop and web
apps they are already built in.

**Work on the web**

| Skill | What it does, and what sets it apart |
|---|---|
| `browser` | scripted work with sites through a separate Chrome profile, never your main browser: open, fill, click, walk result pages, extract; the site's own API or embedded JSON comes before parsing the page, and telemetry is off |

**Code: from an idea to shipped work**

| Skill | What it does, and what sets it apart |
|---|---|
| `grilling` | an interview in rounds that surfaces what you have not put into words yet: why, what if you do not, does it already exist, how you will know it worked; for plans and decisions, not routine |
| `to-spec`, `to-tickets` | a spec from the conversation, then tickets that declare what blocks what; local Markdown by default, no tracker needed |
| `implement`, `tdd` | builds from the tickets test-first, then runs the built-in review |
| `codebase-design` | a shared vocabulary for module depth and seams, read when the shape of the code is decided |
| `commit` | reads the diff, stages only the files of this task, follows the repository's own conventions, confirms the push landed |

The code chain is adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills).

**Skills themselves**

| Skill | What it does, and what sets it apart |
|---|---|
| `skill-quality-suite` | lint, validate and security-scan Agent Skills, and check which skill a request would route to ([SQS](https://github.com/letsloose501/sqs-skills)) |
| `router` | which skill for which task, and the chains they run in |

**Memory upkeep**

| Skill | What it does, and what sets it apart |
|---|---|
| `setup` | first run and repair: memory repository with a private GitHub remote, starter vault, MemPalace, Claude Code pointed at the memory |
| `mistake` | the agent records a mistake it made and fixed, right away, without being asked |
| `memory-review` | the weekly pass: the journal sorted by failure class, repeats across sessions, stale facts, dead ends, search misses; applies safe fixes, proposes the rest |
| `clean-memory` | tidy memory or the vault index now; nothing is deleted without your yes |

**Hooks and scripts**

| Hook | When | What |
|---|---|---|
| `session_start.py` | session start | prints the working rules and the memory search command; after a compaction, what was in progress |
| `guard_memory_scope.py` | before Write/Edit | keeps `<private>` text out of memory and the vault, blocks secrets, requires `source` on entries, protects README/SCOPES |
| `file_context.py` | before Read | when a file is read, surfaces the memory entries and journal lessons that name it (once per session) |
| `guard_heredoc.py` | before Bash | blocks long heredocs, which break silently |
| `guard_literalpath.py` | before PowerShell | rewrites a delete of a `[bracketed]` name to `-LiteralPath` |
| `check_push_landed.py` | after Bash/PowerShell | compares HEAD with the remote after `git push` |
| `verify_vault.py` | after edits / at stop | blocks the end of a turn on new broken wiki links |
| `check_skills.py` (SQS) | after edits / at stop | checks the structure of skills you edit in `~/.claude/skills` |
| `memory_autocommit.py` | at stop | commits memory changes and pushes to the private remote |

| Script | What |
|---|---|
| `memory_recall.py` | search entries by content (`recall`), open one by level (`read`), score a reference set (`eval`) |
| `memory_eval.py` | index size, unreachable entries, missing descriptions, stale facts, sources, search score; history over time |
| `journal_reflect.py` | deterministic pre-sort of the mistakes journal for the weekly review |
| `vault_index.py` | writes MemPalace summary cards for vault notes |

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

## Limits

- **Claude Code only, for now.** The hooks and the session start are Claude Code's. The scripts
  are plain command-line Python and run from any agent that can use a shell, but nothing wires them
  into another harness yet.
- **Search matches words, not meaning.** A question that shares no word with an entry misses it.
  The remedy here is descriptions that name what an entry is for in the words of the task; the
  weekly review fixes the ones search could not match. The vault, by contrast, is searched by
  meaning through MemPalace.
- **One person's memory.** Two machines writing to the same memory at the same moment has not
  been tested.
- **The numbers above come from one memory.** They show the method works on it, not what you will
  get; that is what your own reference set is for.

## Privacy

Everything stays on your machine except what you choose to push: the memory repository goes to a
**private** GitHub repository you create during setup. MemPalace runs locally; its search model runs
on your CPU or GPU. The video skill sends audio to Groq only if you add a Groq key and use tier 3.

## License

Apache-2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Third-party parts keep their own licenses
(MIT for Matt Pocock's skills and AntV Infographic), listed in NOTICE. Ideas taken without code:
file context on Read and `<private>` tags from [claude-mem](https://github.com/thedotmack/claude-mem),
outcome-based journal reflection and provenance tags from [graphify](https://github.com/Graphify-Labs/graphify),
search that answers by path and reading by level from
[tigerless-labs/agent-memory](https://github.com/tigerless-labs/agent-memory).
