# Making a new skill

The order matters more than any of the individual steps. A skill written before the work
has been done once contains good intentions; a skill written from a finished run contains
the traps. Only the second kind survives contact.

## Step 1 - do the work once, without a skill

Sit through one real instance of the task with the user. Take notes on the decisions,
not the outcome: where you guessed, what the user corrected, which step you almost
skipped, what you had to look up twice.

The completion criterion: **the work is finished and the user accepted it.** A half-run
teaches nothing, because the traps are at the end.

## Step 2 - decide whether it is a skill at all

- Will the **agent** need to reach it on its own, or will another skill? Then it is
  model-invoked, and it pays permanent context load for its description.
- Will only the human ever type its name? Then `disable-model-invocation: true`, the
  description becomes a one-line human-facing summary, and the skill costs no context at
  all. You become the index that remembers it exists.
- Is it one step that is always performed identically? That is a **script**, not a
  skill. Prose describing a fixed procedure is retyped by the model every run:
  probabilistic, expensive, unrunnable and unfixable.

## Step 3 - scaffold

```
python scripts/sqs.py new my-skill
python scripts/sqs.py new my-skill --seed invoice --seed receipt   # and what you already ask
```

With `--seed`, it also reads your own Claude Code transcripts for prompts carrying those
words and prints where each one went. Most of them already reaching one skill is the
answer to Step 2 in disguise: that skill may need a branch, not a neighbour. The prompts
are your own words - candidate trigger wordings to read, not to paste.

Creates `my-skill/SKILL.md` with the frontmatter and the three headings that matter, and
a `references/` folder. The template's TODOs are there to be replaced, not filled in
politely - `QL007` reports any that survive.

**Add an optional frontmatter field only when it changes how the skill is reached or how
it runs.** `name` and `description` are the whole requirement; everything else exists to
alter behaviour, and a field that alters none is decoration that every reader has to
parse and every harness has to tolerate. The test is a sentence: *what breaks if I delete
this line*. No answer means delete it.

## Step 4 - write the rules out of the run

Go back to the notes from step 1 and turn each decision into an instruction. Then apply
the discipline the rules cannot enforce themselves:

- **Steps first, in order.** Each ends on a condition the agent can check. "Every
  modified file accounted for", not "understanding reached".
- **Unverifiable requirement -> a `bad -> good` pair** with the reason they differ. A
  pair can be compared; a requirement passes on the author's opinion.
- **No references invented for symmetry.** A reference exists because some branch needs
  it and others do not. If every branch needs it, it belongs in SKILL.md.
- **No fabricated examples.** Without real reference material, say so in the skill
  rather than shipping a plausible generic. A generic example teaches the agent to
  produce generics.

The reading pass in [`writing-rubric.md`](writing-rubric.md) is the full version of this
step. Run it before you consider the draft finished.

## Step 5 - check, then route

```
python scripts/sqs.py check my-skill --strict
python scripts/sqs.py evals                        static routing invariants
python scripts/sqs.py evals --live --skill my-skill    what the model actually does
```

**A bundled helper is code, so it gets a test the way code does.** Anything under
`scripts/` that the skill tells the agent to run needs one focused test of its own, and
the ones you touched get run before you call the edit finished - not the whole suite, the
touched ones. A helper is the part of a skill that fails silently and absolutely: prose
that drifts still half-works, a script with a broken path does nothing and reports
nothing. `QL011` catches the one failure mode a reader can see from the outside, a script
that blocks waiting for input; everything else needs the test.

A new skill changes the routing of every neighbour whose topic it touches - the
description is a shop window, and a new window changes what the street looks like. The
static pass catches the invariant breakage; only the live pass catches "the agent now
sends half of the neighbour's work here".

## Step 6 - register it where a human will look

A skill nobody remembers exists is a skill that never fires. Add it to whatever router
or index you keep, and if the tree has routing cases, add the wordings you would
actually use as new cases. Description edits after this point move the routing of
everything nearby, so re-run step 5 each time.

## Editing an existing skill

`python scripts/sqs.py improve my-skill` puts in one place what the suite can say
reliably about it: every finding with the registry's fix, the prompts in your history
that really routed to it, the ones a neighbour won that its description shares words
with, and where the agent's work went after it loaded - a lookup it repeats from session
to session, a note it reads whole every time, a file it rereads with nothing changed.
Whether a prompt was *meant* for the skill is not in it - that takes a model,
which is paid, so the report offers it and never runs it.

The same discipline, in reverse order.

1. **Search the history first.** The trap you are about to fix may already have been
   analysed, and the second analysis will contradict the first.
2. **Find the passage that produced the behaviour** and rewrite it so the whole class of
   cases falls under it. Appending "and if X, then Y" is overfitting: the patches
   accumulate, start arguing with each other, and eventually nobody dares touch the file.
3. **More than two or three new "and if" clauses in one edit** means the edit should have
   been one general rule. Give yourself the task back.
4. **Touched the `description`? Re-run the routing checks.** One word there moves the
   routing of the neighbours.
5. **Close the edit by naming what it fixes**: today's case *and at least one older one*.
   Only today's means it is a patch. Scripts verify the wiring and the routing; the old
   case is run by hand.
