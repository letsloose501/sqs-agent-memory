---
name: notes
description: >-
  Knowledge system in Obsidian: takes raw information, checks and enriches it with sources
  (official sites, documentation, books, research) and writes a connected note that goes from
  simple to complex, with links, plus spaced-repetition cards and a dictionary. Use on: "take
  notes on / write up / break down this topic / add to my notes / to the vault / to Obsidian",
  "make a note about X", "extend note Y", "make cards from this", "add a term to the
  dictionary", "make a study plan for X", "sort my inbox"; or when text, notes or a summary
  arrive with the intent to put them into the knowledge base. A video link goes to `video` and a
  PDF file to `pdf`: they extract the text and call this skill. Not agent memory (that is
  `mistake` and `clean-memory`): this one writes only into the vault.
---

# Notes: a knowledge base in Obsidian

This skill turns raw information into notes that are **understood on first reading**, inside the
user's Obsidian vault. A note explains, cards consolidate, the dictionary connects topics, a study
plan leads from reading to mastery. The skill sets the process and the style; **the actual data
lives in the vault files, not here.**

- Vault: `${user_config.vault_dir}` (written `<vault>` in the references)
- Plugin root: `${CLAUDE_PLUGIN_ROOT}` (written `<plugin>` in the references)
- Notes language: **${user_config.notes_language}** (this file is in English; the notes are not).

## The principle

**One quality criterion: a person reading the topic for the first time must understand it fast.**
Not "complete", not "clever": *clear and to the point*. So: from simple to complex, the essentials
but in detail, no filler, with examples and links. A paragraph that does not help understanding
is removed.

Three rules keep the system honest:

- **The vault files are the source of truth.** MemPalace holds the structural map (what exists and
  where, `references/mempalace.md`): ask it before writing, to link notes and avoid duplicates; read
  the content itself from the files. If MemPalace is unavailable, search with Grep/Glob.
- **Do not invent facts or links.** Check sources on the web (WebSearch/WebFetch). No reliable
  confirmation: say so; never make up a URL or a number.
- **Link, do not duplicate.** One fact lives in one place; the rest link to it with `[[...]]`.

## Where things live

The vault's own map comes first: if `${user_config.vault_dir}/Vault map.md` exists, it is the
authority on folders and naming, and `references/vault-map.md` only fills the gaps. The starter
layout that `/agent-memory:setup` creates, the naming conventions and how to choose a place are in
**`references/vault-map.md`**. Open it when deciding where a note goes or when starting a topic.

## Before starting: load MemPalace

1. `mempalace_*` tools available: go on.
2. Deferred: `ToolSearch(query="mempalace")`, check that `mempalace_*` tools actually came back.
3. Missing, or calls fail with `Connection closed`: **`references/mempalace.md`**, sections "Loading
   it" and "When the palace breaks". It is a routine failure and takes minutes to fix.
4. Still no luck: **do not block**. Work with Glob/Grep, and tell the user the map will not be
   updated and duplicates have to be checked against the files.

## Modes

| # | Mode | Trigger | Process |
|---|---|---|---|
| **1** | Book | "I'm reading / finished / take notes on this book" | below, "Mode: Book" |
| **2** | **Note**, the main one | "take notes on / break down / add to the vault"; text sent to be filed | below, "Workflow: Note" |
| **3** | Cards | "make cards from this / from note X" | **`references/cards.md`** |
| **4** | Study plan | "how do I learn X / make a plan" | **`references/study-plan.md`** |
| **5** | Inbox | "sort my inbox / file the inbox" | **`references/mode-inbox.md`** |

Mode 5 **ends in mode 2**: each inbox item becomes a full note by the process below.

> **A video link does not come here.** The `video` skill checks the registry, extracts the
> transcript and then calls this skill with the text. A PDF goes to `pdf` the same way.

## Mode: Book

Files: `Books/<Category>/<Title>.md`, template `assets/book-template.md`, strictly. `base: true` in the
frontmatter marks a foundation book, to read first.

- **Update the status** (want / reading / read + date): find the file, change the frontmatter.
- **Fill the summary**: "Main ideas", "Quotes", "Summary" by `references/style-guide.md`. Cards only
  on a direct request (see `references/cards.md`, "When to make cards").

## Workflow: Note

The core. Follow the steps, thinking rather than mechanically.

**Where the material comes from.** By default, from an existing file with a title and some content
(links, books, text, code, images): the job is to grow that seed into a full note, using its content
as the backbone and as sources. Write from scratch only when asked.

1. **Understand the input and its place.** What topic, which folder (`references/vault-map.md`).
   Ask the map: `mempalace_search` by topic with `wing="vault"` (`references/mempalace.md`). Is there
   a note already (then extend it, do not create a second) and what is nearby? Read note content
   from the files. Without MemPalace, Glob/Grep the vault.
2. **Enrich and check.** Fill the gaps in the input into a whole picture. Check facts, dates,
   versions, numbers. Pick **sources** (official documentation, books, research) and verify them on
   the web. Selection and format: `references/style-guide.md`.
3. **Write the note** strictly by **`references/style-guide.md`**: simple to complex, terms in bold
   with a definition, examples and analogies, tables for comparisons, ASCII diagrams for processes,
   a "Sources" section at the end. Where a picture explains better than text and ASCII (color,
   geometry, curves, shape), draw an SVG by **`references/diagrams.md`** and check it by rendering.
   Skeleton: `assets/note-template.md`.
4. **Link into the vault.** From the map and the files, find notes and terms worth linking
   `[[Note#Section|text]]`. Where it makes sense, add a link back from the related note.
5. **Dictionary.** Every **new** content word (any topic) goes into `Dictionary/` by
   `references/dictionary.md`: **one note per word family**; the first mention in the text links `[[Word]]`.
6. **Cards only on evidence that the topic is being forgotten.** A written note does not by itself
   produce cards. There are exactly two reasons: the user asked, or a review or quiz showed the
   topic slipping. Then create or extend `Cards/<Topic>/<...>.md` by `references/cards.md`.
7. **Check the links, always, before reporting.** Run on every created and changed file:
   ```bash
   uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/notes/scripts/check_links.py" --vault "${user_config.vault_dir}" "path/to/Note.md" "path/to/Other.md"
   ```
   It catches the two mistakes that otherwise land silently: a link to a note that does not exist,
   and a `#Section` anchor missing from the target. **Never write a section name from memory**:
   copy the heading from the target file. Exit 0 is clean, 1 means broken links, each with what to
   do. Do not report done until it is 0. (A Stop hook re-checks touched notes at the end of the
   turn and blocks on new broken links.)
8. **Update the map.** Put the new note (and new terms) into MemPalace so the next sessions know the
   structure. Two ways, the second more reliable:
   - the tools `mempalace_check_duplicate`, then `mempalace_add_drawer(wing="vault", ...)`
     (`references/mempalace.md`);
   - **the script, when the tools are missing**:
     ```bash
     uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/vault_index.py" add --vault "${user_config.vault_dir}" --path "<path from the vault root>" --summary "<what it answers>" --terms "..." --links "..."
     ```
   The palace's MCP server starts with the app; if it did not, the `mempalace_*` tools stay missing
   until a restart, and waiting for them hangs the work. Do not wait and do not skip: use the script,
   it writes directly with the palace's own embedder.

   **The summary is a symptom, not a table of contents.** The card is found by it. A card "Index
   types" summarised as "B-tree and selectivity" is not found by "a database query takes forever".
   Write the words the user will search with in six months, having forgotten the title.
9. **Report briefly.** What was created or updated (note, N cards, which terms, which links), with
   paths the user can open.

## Scripts

| Script | When |
|---|---|
| **`scripts/check_links.py`** | step 7, **always** before reporting; with no files it checks the whole vault |
| `scripts/mempalace_doctor.py` | the palace fails with `Connection closed` (`references/mempalace.md`) |
| `${CLAUDE_PLUGIN_ROOT}/scripts/vault_index.py` | step 8 without MCP; `gaps` shows notes missing from the index |

## References

Open the one the situation needs; do not load them all.

| Reference | When |
|---|---|
| **`references/style-guide.md`** | writing a note: **always** in Note mode |
| **`references/vault-map.md`** | deciding where a note goes; a new topic |
| **`references/mempalace.md`** | before writing (the map) and after; the palace broke |
| **`references/cards.md`** | making cards: format, selection, how many |
| **`references/dictionary.md`** | adding a term to the dictionary |
| **`references/diagrams.md`** | a picture explains better than text and ASCII |
| **`references/mode-inbox.md`** | mode 5: the inbox |
| **`references/study-plan.md`** | mode 4: a study plan |

Skeletons are form, not a style sample (style is in `references/style-guide.md`):
`assets/note-template.md`, `assets/cards-template.md`, `assets/term-template.md`, `assets/book-template.md`.

## Principles

- **Understood on first reading** beats completeness and cleverness.
- **Load MemPalace before starting, ask the map before writing, update it after.**
- **Check sources**; never invent links or numbers.
- **Check internal links with the script, not by eye.** A note or section name written from memory
  is the most common mistake: plausible, and therefore invisible.
- **Essentials in detail**: every sentence carries a fact.
- **Write in ${user_config.notes_language}.**
- **Do not touch service folders** (`.obsidian/`, `.trash/`, `Templates/`, the attachments folder).
