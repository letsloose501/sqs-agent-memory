# Agent memory

Long-term memory for any AI agent working with this person. **Not tied to one agent, model
vendor or account**: a plain git repository of markdown files. Claude Code, another coding
agent, a new laptop: it works wherever there is a filesystem and git.

If you are an agent reading this for the first time, start with `MEMORY.md`. It is the index:
one line per entry.

## What lives where

```
agent-memory/
├── README.md      <- you are here: how to use this
├── SCOPES.md      <- what may be edited and what is read-only
├── MEMORY.md      <- index of all entries, LOADED INTO CONTEXT WHOLE
├── *.md           <- the entries themselves, one entry = one fact
├── claude/
│   └── rules.md   <- working rules, loaded into every session
├── mistakes/      <- draft journal of mistakes, reviewed and emptied weekly
└── scripts/
    ├── history.tsv            <- memory health over time (memory_eval.py)
    └── consolidation-log.md   <- what each weekly review found; only grows
```

Next to it live the **skills** (procedural memory) and the **Obsidian vault** (knowledge about
the world). Memory answers "what do I know about this person and their work", skills answer
"how do I do this", the vault answers "what is known about the topic".

## Entry format

```markdown
---
name: <short-slug, same as the file name>
description: <one line; the entry is recalled by it, so it matters more than the body>
metadata:
  type: user | feedback | project | reference
---

<the fact; for feedback and project, add **Why:** and **How to apply:** lines>
Links to neighbours: [[their-slug]].
```

Types: `user` (who they are), `feedback` (how to work with them), `project` (current work and
constraints), `reference` (pointers to outside resources).

## Rules that keep memory from rotting

**Write only what cannot be re-derived.** A procedure goes into a skill. Knowledge about the
world goes into the vault. "What I did on such a day" goes into a commit message. Memory gets
the person's preferences, their decisions with reasons, and tool pitfalls. Test: *could I
recover this by searching the vault or the git log?* If yes, it does not belong here.

**Retire what is outdated, do not overwrite it.** Mark from which date it no longer holds and
what replaced it. "It was the 7th, now it is the 13th" is itself knowledge.

**A repeated mistake is not written twice: it moves up a step.** An entry is passive, a rule
works while it is read, a hook works always.

**No secrets here, ever.** Passwords, tokens, keys, payment details are not stored even for a
moment: git history is irreversible. A hook blocks the common formats.

## Privacy

This repository holds personal facts. Its remote, if any, must be **private**. Nothing from it
goes into a public repository.
