---
name: clean-memory
description: Use when the user wants agent memory cleaned up right now, on either surface - the file memory repository (contradictions, outdated facts, drifted descriptions, episodes instead of facts) or the MemPalace vault index (stray or duplicate drawers). Use on "clean the memory", "tidy memory", "remove this from memory", "forget X", "clean the palace", "/clean-memory". Nothing is deleted without an explicit yes.
argument-hint: "[keyword]"
---

# Clean up memory

Memory lives on two surfaces, cleaned differently. First work out which one is meant.

| Surface | What is there | Cleaned by |
|---|---|---|
| **File memory** `${user_config.memory_dir}` | facts about the user, decisions, pitfalls; `mistakes/` | editing files, under git |
| **MemPalace** | the index of the vault `${user_config.vault_dir}`: what lives where | `mempalace_delete_drawer` |

The user said "clean the memory" without saying which: **ask in one line**.

## File memory

It is under git, so cleaning is safe: everything is recoverable through `git log -p`.

1. Read `MEMORY.md` and the folder.
2. Look for four things:
   - **contradictions**: two entries say different things about the same subject;
   - **outdated**: the date passed, the work is done, the fact no longer holds;
   - **description drifted from content**: the entry will stop being recalled;
   - **episodes instead of facts**: "did X on such a day" is derivable from git and the vault.
3. **Retire what is outdated, do not overwrite it**: mark from which date it no longer holds and
   what replaced it.
4. Deleting a whole file: **only with the user's confirmation**.
5. Keep the index under 150 lines and 20 KB: one line per entry. Measure:
   `python "${CLAUDE_PLUGIN_ROOT}/scripts/memory_eval.py" --memory "${user_config.memory_dir}" --dry`

## MemPalace

1. `mempalace_status`: how many drawers, how they are spread across wings.
2. **Narrow the scope before listing.** There can be thousands of drawers. Ask for a wing and
   room or a keyword, then `mempalace_list_drawers` with `wing`, `room`, `limit`, `offset`, or
   `mempalace_search(query=...)` when the user gave a word.
3. Show compactly: number, ID, first 80 characters.
4. Delete one at a time with `mempalace_delete_drawer(drawer_id=...)` (the parameter is
   `drawer_id`, not `id`).
5. After deleting: `mempalace_status` and a summary.

**Mass deletion breaks the index.** Remove a sizeable share of drawers and the vector index
(HNSW) drifts from sqlite; vector search switches itself off ("vector search disabled"). The
fix is `mempalace repair --mode from-sqlite --archive-existing --yes`, a long rebuild that
leaves a copy of the palace on disk (`~/.mempalace/palace.*`); remove old copies, keeping the
newest as a rollback point. Diagnose first with
`python "${CLAUDE_PLUGIN_ROOT}/skills/notes/scripts/mempalace_doctor.py"`.

## Rules

- **Never delete without an explicit yes.** Neither a file nor a drawer.
- In doubt, show the whole content, not the first 80 characters.
- Do not judge an entry by its file name: read it, and read both before calling two duplicates.

## Arguments

`/agent-memory:clean-memory docker` searches both surfaces for the word and proposes what it finds.

$ARGUMENTS
