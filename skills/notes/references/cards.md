# Cards for spaced repetition

Cards consolidate what a note explained. They work through the Obsidian plugin
**Spaced Repetition** (community plugin `obsidian-spaced-repetition`; grading buttons Easy / Good /
Hard). The goal is **active recall**, not rereading.

## When to make cards (and when not)

A card is made **on evidence that the topic is being forgotten**, not because a note was written. A
note explains; what gets forgotten is not what was explained but what cannot be reproduced. A deck
built "just in case" is never reviewed: one real vault collected almost four thousand such cards,
and they all had to be deleted.

The evidence is one of two:

1. **A quiz or review showed the topic slipping** (the user failed to recall it, confused it with
   something else). Take the wording from that failure: it hits exactly what they confuse.
2. **A direct request** for a specific topic ("make cards from this").

**A note by itself produces no cards.** In doubt, do not create them.

## Where they live

`Cards/` at the vault root, **mirroring the topic structure**:

```
Cards/
  Programming/
    Git.md
    Python.md
  Philosophy/
    Stoicism.md
```

One file = one topic or subtopic. If the file exists, **extend it**; do not create a second.

## File format

**The first line is a tag**; the plugin builds decks from it. Hierarchy: `#Cards/<Section>/<Topic>`,
multi-word parts joined with underscores:

```
#Cards/Programming/Git
```

Then the cards, grouped by divider lines that follow the logic of the note:

```
#Cards/Programming/Git

--- BASICS ---

What is Git
?
A distributed version control system. Tracks the history of changes, lets you roll back and work in a team

--- BRANCHES ---

What is a branch
?
An independent line of development: a "parallel reality" of the project. Lets features grow apart without breaking main
```

## Card types

Pick the type for the material.

- **Basic** (`?`): question, answer. The main type.
- **Reversible** (`??`): when both directions matter (term and definition, command and action):
  ```
  git status
  ??
  Show state: modified, staged and untracked files
  ```
- **Single line** (`::`): for very short pairs: `Commit hash :: a unique commit ID, e.g. a3f9c1b`
- **Cloze**: hide the key word inside the sentence; `==...==` becomes the gap:
  ```
  Git was created by ==Linus Torvalds== in ==2005== for Linux kernel development
  ```

## What becomes a card ("only what is needed")

Cards do not duplicate the note; they pull out **what must stay in the head**:

- **definitions** of key terms ("What is X?");
- **purpose** ("Why do branches exist?");
- **differences and comparisons** ("How does revert differ from reset?"): the most valuable kind;
- **command or syntax to action** (`git stash`: what it does);
- **when to use what** and **typical traps**.

**No cards** from filler, the obvious, whole long lists (split into meaningful pieces or skip), or
anything the user does not plan to recall. 15 precise cards beat 50 for the count.

## How many

As many as there are **separate facts worth remembering**, usually not one per paragraph. A small
topic: 5-15; a big one: dozens, each justified. Test: if the question could be skipped with nothing
lost, skip it.

## Wording

- **Atomic**: one card, one fact.
- **Precise question**, answer in 1-3 sentences, in the note's language.
- **Self-contained answer**: understandable without looking at the note.
- **Unambiguous**: one expected answer.

## Technical details

- **Separate cards with a blank line**: it ends a card for the plugin.
- **Never touch the plugin's comments.** After reviews the plugin appends schedules like
  `<!--SR:!2026-06-21,3,250-->`. When extending a file, do not remove or change them; just add new
  cards. New cards need no schedule.
