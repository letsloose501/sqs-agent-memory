# The mistakes journal

A folder of short notes the agent writes the moment it notices it was wrong, and a review
that turns repeats into changes a skill cannot skip. `improve` and `discover` read it, so
the mistakes made with a skill show up next to the findings about it. Open this before
recording a mistake, before reviewing the journal, and when `improve` section 4 names
entries.

## Recording

One file per mistake, named `YYYY-MM-DD-short-gist.md`, four fields:

```
MISTAKE: what I did wrong
WHY:     what caused it
FIX:     how it was fixed now
PATTERN: how not to repeat it
```

The pattern is the part worth keeping, and it is written for a class of cases, not for
today's command. Bad: "`ls-remote` can print nothing". Good: "empty output is not a
result until the exit code has been read". The first is true once; the second catches the
next tool that does the same.

Name the skill when the mistake happened inside one - `` `skill-name` ``, a path such as
`skill-name/references/x.md`, or "the skill-name skill" - because that is how the suite
finds it. A bare word is not matched: in a real journal it credited the verb "commit" to a
skill called `commit`.

Then read the file back. On one real journal, five of fifty-five entries had been cut to
the last word of a sentence when written, and the lesson went with the session.

Record without being asked, and whoever found the mistake: the user or the agent itself.
Do not look for duplicates or propose a rule while recording - that needs the whole folder
at once, which is the review's job.

## Reviewing

Periodically - weekly works - read the whole folder, group the entries by what went wrong,
and raise each group one step:

- **once** is noise until it repeats;
- **two alike** are a rule, written into the skill where the mistake happened;
- **three alike** are a script or a gate - a check the agent cannot skip, because a rule
  it already had did not stop it.

"Alike" is read off the patterns, never off a count. On a real journal the four entries
naming one skill were four different mistakes; a count would have ordered a gate for
nothing. Write what the review decided in a log beside the journal, then clear the
folder. Keep the folder under git: the cleared entries stay in its history, the suite
still counts them, and a mistake that returns after a review is exactly the one to see.

A rule written from an entry fixes the principle behind it, not today's example: find
the sentence in the skill that produced the mistake and rewrite it to cover the class.
Appending "and if X, do Y" is a patch; patches pile up and start to contradict each other.
Close the change with a backtest - today's case and at least one older one from the
journal.

## What the suite reads

Point it at the folder: `"mistakes": "path/to/mistakes"` in `sqs.config.json`, or
`--mistakes-dir`. Then:

- `sqs.py improve <skill>`, section 4 - the entries that name the skill, newest first, with
  their patterns, which of them are still open and which a review already cleared;
- `sqs.py discover`, section 3 - every skill the journal names, and how often.

Both read `MISTAKE`/`WHY`/`FIX`/`PATTERN` and the Russian `ОШИБКА`/`ПОЧЕМУ`/`РЕШЕНИЕ`/`ПАТТЕРН`.
Nothing is written, nothing leaves the machine, and nothing is decided: the suite shows
the entries, and grouping them stays with whoever reads the patterns.
