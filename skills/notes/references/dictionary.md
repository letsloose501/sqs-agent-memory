# Dictionary

The dictionary is the connective layer of the whole vault. Any topic can link a word `[[Word]]`,
and the word lives once, in one place, gathering meaning. Words from **all** topics (programming,
philosophy, editing, self-development) go into one `Dictionary/`; that is what creates the
crossings between topics.

**One file is a word family, not one word.** A file per form scatters related words. Keep them
together: `Interpreter` holds *interpreter*, *interpret*, *interpretation*, each with its meaning,
examples and where to use it.

## Where

`Dictionary/` at the vault root. One file per family, named after the root word:

```
Dictionary/
  Interpreter.md      # interpreter, interpret, interpretation
  Abstraction.md      # abstraction, abstract, abstract (verb)
  Catharsis.md
```

## When to add

- A **new** content word appeared (a concept, a term; not an everyday word): add it.
- **First check whether the family exists** (Glob/Grep in `Dictionary/`). It does: add the form or
  meaning to the existing file. It does not: create one.

## File name

- The family's **root word**, singular: `Interpreter.md`.
- Other forms live inside the file.
- Abbreviations as they are used: `OOP.md`, `ADT.md` (expansion in the body).

## Structure

A card-like definition of the main word first, then the family: each form with its meaning, an
example and where to use it (including in speech).

```
---
tags:
  - Dictionary
  - <Source topic>      # where the word came from, e.g. Programming
---
# Interpreter

**Interpreter**: a program that executes code line by line, without compiling it first.

## Family

- **Interpreter** (noun): _a program that executes code._
  - Example: "Python is an interpreter, not a compiler."
  - In speech: about the runtime: "which interpreter is installed, 3.12?"
- **Interpret** (verb): _to execute code; more broadly, to construe._
  - Example: "the interpreter interprets bytecode."
- **Interpretation** (noun): _the process or result of construing._
  - Example: "an interpretation of the test results."

<More if needed: etymology, how it works, an analogy.>

## Links
- [[Note]]: where it is used
- [[Other word]]: a related concept

## Sources        <- when the definition is not trivial
- [Link](https://...)
```

The minimum for a new file is the main word and its definition; forms and examples are added as
they come up.

## Linking

- In the **source note**, the first mention is a link: `[[Interpreter]]` or with a word form
  `[[Interpreter|interpreting]]`. After that, plain text.
- In the **dictionary note**, link back to the topics that use the word ("Links"), closing the graph
  both ways.
- If a big topic note already covers the concept, keep the dictionary note short with
  `see [[Big note]]`, so there are not two truths.

A word family can grow into a topic: when a concept gathers enough, it becomes a full note by the
ordinary Note process. That is welcome.
