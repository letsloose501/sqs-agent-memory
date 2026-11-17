# Fact-check: running the checker (for the author)

Step 7 of the Note workflow. The checker's own brief is `fact-check.md`; this file is for you,
the author, and the checker never reads it: it holds the cases and the reasoning a checker must
not see.

## Why a separate pass

The author has already convinced itself the note is right: it sees its own path to each
sentence, not the sentence. Two failures of that kind, both caught late and by hand:

- **An invented mechanism about the user's own setup.** A note on background agents had a
  section "how this looks in our setup" saying a scheduled task "starts the agent directly, so
  two firings can collide". Neither the article nor any file said so; it was a plausible
  mechanism written on the fly. A mechanism is a claim like a number is, and it needs a source.
- **A search summary retold as a paper's finding.** "Agents meet process requirements far less
  often than completion ones; the small model under 3%" came from a search synthesis. The paper
  shows the opposite on loose scores for the top models, and "under 3%" is the small model's
  strict score: the qualifier was dropped.

Asking yourself to "double-check" does not fix this: it reruns the same reasoning.

## When to run

- **Always** on a note created or extended from sources (an article, a video transcript, a
  PDF, a paper): before step 8 (link check) and, for a video, before the transcript is deleted,
  because the transcript is one of the sources.
- **Skip** for a pure rewording, a link fix, or a note with no claims taken from a source.

## How to launch

`Agent`, `subagent_type: "general-purpose"`, `model: "sonnet"` (heavy reading, and every
verdict comes with a quote that is cheap to check). Several notes from one batch: one checker
per note, launched in parallel. The prompt carries exactly three things: the note's path (and
which sections are new), the sources, and the brief's path.

**Sources as files where you can.** A transcript or extracted PDF text is already a file: pass
it. A web article read through WebFetch reaches the checker only as summaries, and in the
calibration below that produced four false `UNSUPPORTED` items on one article. For a short,
central article, save its text first (the `browser` skill's page text into a scratch file) and
pass that file next to the URL.

**Never put into the prompt:** why you wrote a sentence, what you were unsure about, which claims
you "already checked", that the note "looks good", or a pointer to this file. That is the
reasoning that makes a checker sign off, or tells it the answer.

```
You are the checker, not the author. The note below was written by someone else; you
do not see their reasoning. Your job is to find claims the sources do not support.

NOTE: <path>            (new or changed sections: <list, or "whole note">)
SOURCES:
- <path or URL>
- ...

Procedure and answer format: ${CLAUDE_PLUGIN_ROOT}/skills/notes/references/fact-check.md.
Follow it exactly. Do not open other files under ${CLAUDE_PLUGIN_ROOT}/skills/notes/.
```

## What to do with the verdict

- **CLEAN**: go on to step 8.
- **FIX**: for each problem, either correct the sentence from the source, mark it in the same
  sentence ("not checked", "per the video"), or delete it. Then rerun the checker on the changed
  sections. An `UNSUPPORTED` item you can refute with the source (you read it, the checker saw
  only a summary) is not fixed by editing: log it below.

Do not argue with the checker in the prompt: it lacks your context on purpose. If it was wrong,
that is a reason to fix its brief.

## Calibration (sonnet, split brief)

| Case | Expected | Got |
|---|---|---|
| a note with an invented paragraph about the user's setup | FIX on the three own-setup claims | FIX on all three; plus a real find in the user's files (a scheduled task that already had a run lock), which the "corrected" note also had wrong |
| the paper finding with a dropped loose/strict qualifier | FIX | FIX, quoting the paper's table for both scoring modes |
| a note believed clean | CLEAN | FIX on one word ("came to it independently"), which no source says; 26 of 27 claims SUPPORTED, the setup claims checked against the scripts themselves |

## Lessons from the calibration

- **A checker's brief must not contain the cases it is calibrated on.** On the first run the
  cases sat in the checker's own brief, and both checkers cited them ("the same error as the
  earlier case"): the answer leaked, and the run proved nothing. The brief was split: the
  checker reads `fact-check.md` only, the cases live here.
- **WebFetch summaries hide sentences.** Four claims that were in the article came back
  `UNSUPPORTED` because the checker saw only summaries. Hence the second targeted prompt and the
  "summary only" label in the brief, and saved article text in the prompt.

## Disagreement log

<!-- date | what the checker said | what was true | what changed -->

_empty so far_
