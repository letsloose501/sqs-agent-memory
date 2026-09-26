---
name: grilling
description: >-
  A decision-tree interview: round after round it draws out what the user has not yet put into
  words, until no assumption is left silently accepted. Use only where a clear plan and analysis
  are needed: the concept of a project or feature, the idea of a video or script, a plan for a
  period, a choice of architecture or niche; and on the words "grill me", "interrogate my idea",
  "stress-test this plan", "poke holes in this". NOT for routine: an ordinary note, a video
  transcript, a vault entry, a text edit, an answer to a question; there an interview only gets
  in the way. It does not do the work; it brings the decision to clarity before the work. A quiz
  on knowledge ("test me on X", a mock interview) is a different job: that checks what the
  person remembers, this checks what they have thought through.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

## Round zero

Before mapping the tree, ask the questions the tree hangs from. A design tree
starts *below* these, so it inherits them silently:

1. **Why** - what changes for you once this exists?
2. **Not doing it** - what happens if you don't? If the honest answer is "not
   much", say so and stop. A cheap no beats an expensive yes.
3. **Prior art** - does this already exist? What is wrong with using that
   instead of building?
4. **Done** - what single observable fact will tell you it worked?

For anything that ends in code, round zero also settles:

5. **Stack** - what, and *what for*: one line per choice naming what it replaces
   or saves. Recommend one, don't survey five.
6. **Scale** - throwaway script, MVP, or something to maintain for years. This
   decides how much process the work deserves and is a decision, not a mood.

Round zero uses the same format as every other round: numbered questions, your
recommended answer under each, then wait.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

## Not every branch is worth walking

The frontier is a list of questions you _could_ ask, not a quota. A branch whose
answer changes nothing about the work is politeness, not design - drop it before
asking. Judge a question by what breaks if it stays unanswered; if nothing
breaks, it was never on the frontier.

The user may also call time early - a grilling session runs long, and theirs is
the only clock that counts. When they do, stop asking and go straight to writing
the outcome.

## What survives the session

A settled decision has two halves, and the second one is the one that gets lost:
what was chosen, and **what was rejected and why**. The conversation holds both,
but the conversation does not survive - so the rejected half has to be written
down, or the next session proposes it again and the user argues it down twice.

The same applies to branches you dropped or never reached. An assumption is
silent whether it was never raised or raised and abandoned, and this skill
exists to leave none of those.

So when the grilling ends - frontier empty or user called time - write the
outcome wherever the work will live (issue, spec, plan, note, the PRD itself),
in three parts:

- **Decided** - the choice, one line each.
- **Rejected** - the option and the reason it lost, one line each.
- **Still open** - branches dropped as not worth it, or unreached because time
  was called; mark which of the two each one is.

That record is the only artifact this skill produces; the work itself belongs to
whichever skill does it. Do not start that work until the user confirms you have
reached a shared understanding.
