---
name: mistake
description: Record a mistake the agent made and corrected, so the lesson outlives the session. Run it yourself, without a reminder, whenever you gave a wrong answer and fixed it, went down a wrong path and redid the work, misread the request, or a tool behaved unlike you expected; also when the user says "remember this mistake", "log this", "/mistake". It only records; it decides nothing.
argument-hint: "[what went wrong]"
---

# Record a mistake

The entry goes into the **file memory under git**: `${user_config.memory_dir}/mistakes/`.
Not into MemPalace: the palace is the index of the notes vault, not a journal. A file can be
read, edited, diffed and reverted, which is exactly what a mistakes journal needs.

## This skill only records

It decides nothing. The weekly review (`/agent-memory:memory-review`) reads the whole folder,
groups entries by substance, moves repeats one step up (a rule, then a hook), writes the
analysis into `${user_config.memory_dir}/scripts/consolidation-log.md` and empties the folder. Hence:

- **Do not look for duplicates.** Grouping needs the whole folder at once; a session sees only
  its own mistake.
- **Do not propose a rule or a hook.** The step is set from the whole picture: once is noise,
  twice is a rule, three times is a hook. That count is invisible from inside one session.
- **Write freely and in detail.** It is a draft, and nothing is lost: the folder is under git.

One exception: the user said to create a rule or hook. Then it is their decision, and it is
done as an ordinary task, not inside this skill.

## Steps

**1. Write the entry: four lines, in English** (the user's verbatim words stay in quotes as
they are).

```
MISTAKE: [what I did wrong]
WHY: [what caused it]
FIX: [how it was fixed now]
PATTERN: [how not to repeat it: the valuable part]
```

Put the effort into PATTERN and phrase it so it covers a **class of cases**, not today's
command: "empty output is not a result until you have looked at the exit code", not "`ls-remote`
can print nothing".

**2. Write the file** `mistakes/YYYY-MM-DD-short-gist.md` (Latin letters) with those four lines.
Do not touch `MEMORY.md`: this folder is not in the index. Do not ask for confirmation.

**3. Read back the file you just wrote.** All four fields present, text not cut off. This is
not paranoia: in one real journal five of 55 entries turned out to be a single broken word,
the structure lost on write, and the lesson with it. The mistake-catching tool fell for the
most common mistake in its own journal: claiming something was written without checking.
A field is empty or cut: rewrite it now; the context leaves with the session.

**4. Report in one line**: "recorded a mistake: <gist>". No analysis, no proposals.

## Arguments

The user may describe the mistake: `/agent-memory:mistake mixed up the port in the config`

$ARGUMENTS
