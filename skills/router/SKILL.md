---
model: haiku
name: router
description: >-
  Map of the agent-memory skills and the chains they are meant to run in. Read it when the user
  sets a task and the route is not obvious: unclear which skill solves it, the task has several
  steps, or you are about to do by hand what a skill already covers. Also on direct words:
  "which skill", "where do I start", "what is the best way to do this", "is there a skill for
  this".
---

# Route

Name the route and offer the first step; do not recite the skill list. One line in the user's
language, like "route: `/agent-memory:grilling` -> `/agent-memory:to-spec` -> `/agent-memory:to-tickets`
-> `/agent-memory:implement`, start with the interview?", and that is all. Do not ask permission for
every next step: ask at forks.

If a skill covers the task and you already started by hand, stop and offer the skill. If no skill
covers it, say so and work by hand; do not stretch the nearest one over it.

All skills below live in the `agent-memory` plugin: call them as `/agent-memory:<name>`.

## Forks that are easy to get wrong

**Text in hand versus text to extract.** Ready text, a summary, notes: straight to `notes`. A video
link: `video`, which extracts the transcript and calls `notes` itself. A PDF, a book, a scan: `pdf`,
which also calls `notes` itself. Never call `notes` directly on a link or a file.

**Knowledge from a video, or how the video is made.** `video` is for knowledge: a lecture, a talk, a
tutorial, a podcast interview, a bare link. If the user wants to understand how a clip, ad or vlog is
built (hooks, pacing, editing), that is not `video`: say so and do it by hand, or ask "the knowledge
from it, or how it is made?".

**Memory or the vault.** A fact about the user, their decisions, a tool pitfall: agent memory
(the memory repository). Knowledge about the world: the vault, through `notes`. A procedure that is
always done the same way: a skill or a script. Test: could this be recovered from the vault or the
git log? Then it does not belong in memory.

**A skill as the subject.** Work on a skill (check it, fix one that half-works, prepare it for
publishing, read a stranger's before trusting it) goes to `skill-quality-suite`. Writing a new one
from scratch goes to the official `skill-creator` if it is installed, then `skill-quality-suite
check`. A note about how skills work is `notes`: the topic being skills does not make it skill work.

## Chains

### Knowledge into the vault
`video` / `pdf` -> `notes`, or `notes` directly when the text is in hand. A diagram inside a note:
`notes` draws analogue pictures itself and calls `graphics` for templates and data charts. New notes
reach the MemPalace index through `notes` step 8; a vault that grew without it: `vault-index`.

### Code, a project, a feature
Three entrances, one channel:

```
A. an idea of their own  ->  grilling   --+
B. someone else's brief  ------------------+->  to-spec -> codebase-design -> to-tickets -> implement
C. a clear task          ------------------+
```

- **`grilling`**: the interview that surfaces unstated assumptions (why, what if not,
  does it exist already, the sign of success, stack, scale), then the decision tree.
- **`to-spec`**: what and why, and the boundaries; no paths or signatures, so it survives a refactor.
- **`codebase-design`**: modules, seams, interface depth. A reference read at the moment the shape is decided.
- **`to-tickets`**: order and blocking; tickets as local markdown in `.scratch/` unless the project
  names a tracker.
- **`implement`**: the build, with `tdd` inside.

Scale decides how much of the chain is needed:

| What | Route |
|---|---|
| One edit, a bug with a clear repro | none, just work |
| A feature in a living project | `to-tickets` -> `implement` |
| A new project or MVP | the full chain |
| A timed algorithm task | no route at all |

**Look at what exists first** (a plan note, a repository, tickets in `.scratch/`) and enter the chain
at the first step not yet done. A detailed plan with acceptance criteria already is a spec.

To check finished work: the built-in `/code-review`, `/security-review`, `/simplify`. To commit: `commit`.

### A decision outside code
`grilling` for anything that needs a clear plan: a niche, the structure of a vault section, a plan
for a period, a contested architecture. Not for routine (a note, a video, an edit, an answer): there
an interview only gets in the way.

### A website
Reading a public page, docs or an API: WebFetch or curl, no browser. Doing something on a site (a
form, filters, pages of results, a JS-rendered page, WebFetch returned an empty shell): `browser`.
The user wants to watch, or it is their own dev server: the app's built-in browser. It needs their
logins from their main Chrome: Claude in Chrome.

### Formulas, proofs, slides
`latex`: a full `.tex`, a snippet, or Beamer slides.

### Memory
Gave a wrong answer and corrected it: `mistake`, at once, without a reminder. Clean up now:
`clean-memory`. The weekly pass (repeats across sessions, stale facts, the journal emptied):
`memory-review`. First install, or paths changed: `setup`.

## When no skill is needed

A short question, a single file edit, a search through the vault, a conversation. A skill is a
procedure for multi-step work, not a wrapper around every action.
