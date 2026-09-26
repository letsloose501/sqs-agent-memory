# Vault map

Root: the vault path given in `SKILL.md` (written `<vault>` below).

The right place for a note is half of its connectedness. Before creating a file, decide its topic and
put it next to its relatives. The live map of "what is where" is kept in MemPalace (`mempalace.md`);
this file is the general frame.

**The user's own map wins.** If the vault root has `Vault map.md`, read it first: it records the
folders that actually exist and any naming the user chose. When you create a new top-level topic,
add a line there. The layout below is only the starter one that `/agent-memory:setup` creates, with
folder names in English; the user may have renamed or translated them.

## Starter layout

```
<vault>/
├── Vault map.md       the vault's own map: top-level topics and what goes where
├── Inbox.md           one inbox for anything: thoughts, links, snippets (mode 5 sorts it)
├── Programming/       Basics/ at the root of each big topic, specifics deeper
├── Media/
├── Education/
├── Self-development/
├── Books/             one file per book by assets/book-template.md, grouped by category
├── Dictionary/        word families, one note per family (dictionary.md)
├── Cards/             spaced-repetition decks, mirroring the topics (cards.md)
├── Ideas/             things the user wants to build: one file per idea (NOT study notes)
├── Videos/            the registry of processed videos (video skill)
├── PDF/               the registry of processed PDFs (pdf skill)
└── Templates/  .obsidian/  .trash/   service folders: never written by this skill
```

## Conventions

- **The foundation of a topic goes into `<Topic>/Basics/`.** Specifics go deeper.
- **A big overview note gets a descriptive name**: `Health - brain and cognition`,
  `Planning - priorities and task management`. Such names are unambiguous to find and link.
- **File name = how you will link to it**: a plain noun phrase, spaces allowed, no invisible
  characters (accents or combining marks typed by accident break links).
- **One owner per concept.** Everyone else links to it.

## From what the user says to a folder

Decide by meaning, and confirm against the user's `Vault map.md` when it exists.

| The user says | Folder |
|---|---|
| code, a language, algorithms, git, databases | `Programming/...` |
| editing, video, content, script, color, music, design | `Media/...` |
| philosophy, psychology, languages, maths, history | `Education/...` |
| habits, productivity, learning, health, speech, sport | `Self-development/...` |
| a book, notes on a book | `Books/` |
| any new content word | `Dictionary/` |
| "I want to build", "I have an idea", a project concept | `Ideas/` |

## A new topic

When no folder fits:

1. Propose a short name and a place (top level or inside an existing topic).
2. When it is ambiguous, **ask**; do not guess silently.
3. Create `<Topic>/Basics/` if the topic will grow, and add the topic to `Vault map.md`.

## What goes where

- Topic notes: the topic's folder.
- Words: `Dictionary/`.
- Cards: `Cards/<Topic>/...`.
- Study plans: next to the topic, `<Topic> - study plan.md` (study-plan.md).
- Diagrams: `<Topic>/Diagrams/`.
- Raw dumps: `Inbox.md`, then mode 5 files them.
- Service folders (`Templates/`, `.obsidian/`, `.trash/`, the attachments folder): never written.
