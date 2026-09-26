# MemPalace: the map of the vault

<!-- sqs-allow-file: ST011 - this file describes paths in the user's home that exist only after installation (config files, profiles); they are absent on a fresh machine or in CI. -->

MemPalace is a local MCP memory that holds the **structural map of the vault**: which notes exist,
where, what they answer, how they connect. It lets the next session know the structure **without
rescanning the whole vault**, and it finds a note by meaning when the exact word is unknown. The notes
themselves live in Obsidian; MemPalace **indexes** them, it does not replace them.

> The source of truth is the vault files. MemPalace is a pointer to them. When they disagree, trust the file.

In this setup the palace is **only the vault index**. Session snapshots are switched off
(`hooks.auto_save: false` in `~/.mempalace/config.json`): measured on one real palace they took 96 %
of the volume and never answered a question. The mistakes journal lives in the memory repository.

## Structure: wing, room, drawer

| Level | Meaning here | Example |
|---|---|---|
| **wing** | the whole vault | `vault` |
| **room** | a top-level folder | `Programming`, `Media`, `Dictionary` |
| **drawer** | one note or term: a summary card | the note "Git" |

## What a drawer holds

A **short pointer card**, not a copy of the note:

```
Git.md - how to keep history, branch and merge without losing work; what a remote is
Path: Programming/Git.md
Terms: repository, commit, branch, hash, staging
Links: [[Terminal]], [[Databases#SQL]]
```

Raw note text in the index is useless: on a real 1100-note vault, 1043 raw drawers removed changed
the results of none of the test queries. That is why the index is filled with cards
(`vault_index.py`), not with `mempalace mine`.

## Tools

Parameter names change between MemPalace versions. **Before the first write in a session, look at
the tool's live schema**, not at this file.

- **Reading the map** (before writing):
  - `mempalace_search(query="<topic or term>", wing="vault", limit=5)`: related notes.
  - `mempalace_list_drawers(wing="vault", room="<Topic>", limit=30)`: what the topic already has.
  - `mempalace_list_rooms(wing="vault")`: the real room names. Take room names from here, never
    invent one: a plausible new room next to the real ones silently splits the map.
- **Writing the map** (after creating or editing a note):
  - `mempalace_check_duplicate(content="<text>", threshold=0.9)`: is there such a drawer already.
  - `mempalace_add_drawer(wing="vault", room="<Topic>", content="<card>", added_by="notes")`.
- **Maintenance:** `mempalace_status`; `mempalace_delete_drawer(drawer_id="<id>")` (the parameter is
  `drawer_id`; delete only at the user's request, see `clean-memory`).

**A failed `add_drawer` does not mean nothing was written.** The call can die with `Connection
closed` or `Error in compaction` after the document already reached sqlite; only the vector index
update failed. Do not retry blindly: list the room or search for the content first, or you get a duplicate.

## When to read and when to write

- **At the start of Note mode**: `mempalace_search` by topic to learn whether a note exists, what is
  nearby and what to link. Read the note itself from the file.
- **After writing** a note or a new term: add its card. A new dictionary term: a card in room `Dictionary`.
- Cards (`Cards/`) are not indexed separately: they mirror notes.

## Loading it (before starting)

1. **Tools present?** `mempalace_*` available: done.
2. **Deferred?** The names are listed but the schemas are not loaded: `ToolSearch(query="mempalace")`,
   and check that `mempalace_*` tools came back, not random matches.
3. **Missing entirely?** The server did not start in this session. The plugin's `.mcp.json` runs
   `mempalace-mcp`; the usual causes are MemPalace not installed (`uv tool install mempalace`) or
   `mempalace-mcp` not on PATH (`uv tool update-shell`, then restart the app). A new server only
   appears in a **new** session. Tell the user and use `vault_index.py` in the meantime.

## When the palace breaks

Symptom: `Connection closed` or `Internal tool error` on any `mempalace_*` call, or `mempalace_status`
reporting `HNSW index holds N elements but sqlite has M`.

**It is a routine failure.** Start with the doctor, it diagnoses from numbers in a second:

```bash
uv run --no-project "<plugin>/skills/notes/scripts/mempalace_doctor.py"
```

It reads `chroma.sqlite3` and the index metadata read-only, shows live processes, and tells apart
four cases: **phantom nodes**, **HNSW lagging behind sqlite**, **healthy** (the stdio server itself
died: restart the client, no repair needed) and **busy** (processes hold the files). `--fix` repairs:
stops the processes, checks disk space for the archive, rebuilds, restores the embedder.

**Not every `Connection closed` is a broken palace.** If the doctor says healthy, a repair would be
a long rebuild for nothing; the fix is restarting the client.

By hand:

1. **Stop live processes** (otherwise the files are locked).
2. **Rebuild** (minutes, depending on size):
   `mempalace repair --mode from-sqlite --archive-existing --yes`
   The `from-sqlite` mode is required: the default mode goes through chromadb and fails the same way.
3. **Record the embedder** if the doctor says so: `mempalace palace set-embedder --model <model>`.
4. **Remove old snapshots.** Each rebuild with `--archive-existing` leaves a copy in
   `~/.mempalace/palace.pre-rebuild-*`. They pile up silently. Once the new palace answers searches,
   remove all but the newest; deleting is the user's decision.

No data is lost: documents live in `chroma.sqlite3`, the HNSW index is derived from it.

> **Do not write into the palace while a repair runs.** Finish work that does not touch MemPalace
> (the notes themselves), wait for exit code 0, then write the cards.

## Filling the index for an existing vault

When the vault already has notes the index does not know, use the `vault-index` skill: it takes
batches of uncarded notes (`vault_index.py gaps --batch 40`), reads each and writes cards.
