---
name: vault-index
description: >-
  Fills the MemPalace index of the Obsidian vault in batches: finds notes that have no summary
  card yet, reads each and writes a card that says what question the note answers, so semantic
  search finds it by the words someone would actually ask. Use on "index my vault", "fill the
  palace", "the search does not find my notes", "card the notes", after importing an existing
  vault, or from a scheduled task. One run = one batch.
---

# Fill the vault index

The MemPalace index is **summary cards**, one per note: name, path, what it answers, terms, links. It
exists to find a note when the exact word is unknown: grep will never find "where was the thing about
the agent getting dumber on long tasks", because the note does not contain "dumber".

- Vault: `${user_config.vault_dir}`
- Script: `${CLAUDE_PLUGIN_ROOT}/scripts/vault_index.py` (runs on any Python; it re-launches itself in
  the MemPalace tool environment, where chromadb and the embedder live)

**Do not fill it with `mempalace mine`.** Measured on a real 1100-note vault: `mine` added 1043 drawers
of raw text, including an inbox with a list of films, and eight test queries returned byte-identical
results before and after those drawers were removed. The index is made by the summary, not by volume.

**Do not depend on the `mempalace_*` MCP tools here.** The server starts with the app; when it did not
connect, a task waiting for its tools hangs. The script writes directly, with the palace's own
embedder (a different embedder silently breaks search for the whole palace).

## Steps

**1. Take a batch.**

```bash
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/vault_index.py" gaps --vault "${user_config.vault_dir}"
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/vault_index.py" gaps --vault "${user_config.vault_dir}" --batch 40
```

30 to 50 notes per batch. More, and the quality of summaries drops faster than speed grows. Stubs (a
title and empty headings) are neither listed nor counted in coverage.

**2. Read every note.** Actually read the file; do not guess from its name.

**3. Write the cards into a JSON file** in the scratchpad and add them in one call:

```json
[
  {"path": "Programming/Git.md",
   "summary": "how to keep history, branch and merge without losing work; what a remote is",
   "terms": "repository, commit, branch, hash, staging",
   "links": "[[Terminal]], [[Databases]]"}
]
```

```bash
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/vault_index.py" add --vault "${user_config.vault_dir}" --from-json "<scratchpad>/batch.json" --agent vault-index
```

The script skips notes already carded and paths that do not exist, and prints what it added.

**4. The summary is the line that matters: a symptom and a question, not a table of contents.**
A card "Index types" summarised as "B-tree and selectivity" is found by "types of database indexes"
but **not** by "a database query takes forever", because the summary has no words about a slow query.

- bad: "sections: definition, types, examples"
- good: "how keyset differs from offset and why offset slows down on deep pages"

Think: in what words will the user ask about this in six months, having forgotten the title?

**Spell notation out in words.** An embedder does not connect `O(1)` with "constant time" or `WAL` with
"write-ahead log". Write "in O(1), that is, constant time" and "write-ahead log (WAL)".

**Never copy phrasing from test queries.** Putting an evaluation query into a card raises the number
without improving anything: the summary is written from the note, never from the test.

**5. Check the palace after a large write**, since the vector index can drift from sqlite:

```bash
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/notes/scripts/mempalace_doctor.py"
```

"Healthy" or "within flush lag": done. Anything else: follow its instructions.

## Limits

- **Do not edit the vault.** This task only reads notes and writes to the index.
- Do not commit anything.
- Blocked on a permission prompt: do not wait silently; finish the run and say where it stopped.

## Report

One block: how many cards were added, which sections, coverage before and after (from `gaps`), what is left.
