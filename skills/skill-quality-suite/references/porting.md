# Porting a skill to another harness

For "make this skill work on Cursor" (or Codex, Gemini CLI, any harness in
`sqs.py harnesses`). The suite does not rewrite a skill for you - it has no `port` command,
on purpose. The adapter tables go stale between checks, and a port built from a stale table
silently rewrites somebody's file. So the agent does the port itself, on the user's machine,
from the target's own documentation read at the moment of porting.

## 1. See what the suite already knows

```
sqs.py compat <skill> --harness <target>      the verdict and every problem, with reasons
sqs.py harnesses --show                       the target's page, locations, and `checked` date
```

The report is a starting list, not the answer. Every row rests on the page named beside it,
as of the `checked` date printed in the table.

## 2. Read the target's page yourself - every time

Open the documentation URL `sqs.py harnesses` prints for the target and read it now. Four of
the ten pages had moved by the first check (23.09.2026), and fields had come and gone. Read
for exactly these, and quote the sentence each answer rests on:

- where skills are discovered - project and user folders, legacy folders, plugin paths;
- which frontmatter fields are required, which optional, which only this harness reads;
- whether `name` has to equal the folder name;
- which subdirectories it names, or whether it makes every file in the folder available;
- whether it rewrites anything in the body - `$ARGUMENTS`, `` !`command` ``, variables.

If the page says something different from the adapter, **the page wins**. Tell the user what
differs and that the adapter needs a fresh check (`scripts/harnesses/<name>.py`, `checked`);
do not edit the adapter as part of the port. If the page has moved, follow it. If it cannot be
read, say so - what the page does not state stays unknown, and a guess is not a port.

## 3. Find the target on this machine

- Is the harness installed, and which of its documented folders exist here? Ask whether the
  skill should live in the project folder or the user-wide one, if both are documented.
- Is there already a skill with this name there? **Stop and ask.** Never overwrite one.

## 4. Plan the port, then show it

One line per change, each with the verdict or the page quote behind it:

| What the report or page says | What to do |
|---|---|
| a required field is missing | add it |
| `name` must match the folder and does not | rename the copy's folder, not the field, unless the user prefers otherwise |
| a field only the source harness reads (`model:`, `context:`, ...) | drop it from the copy, or move it under `metadata:` if the target documents ignoring unknown keys; say what behaviour it carried |
| a directory the target does not name, and SKILL.md links it | usually leave it; rename only if the page names a different folder and nothing else can reach it - then fix every link |
| `$ARGUMENTS`, `$0`, `${CLAUDE_SKILL_DIR}/...`, `` !`cmd` `` in the body | rewrite as prose or an explicit step: what the value is, which command to run and when |
| `allowed-tools` with the source's tool names | translate to the target's names if its page documents them; otherwise state the restriction in the instructions |
| a hard-coded path into the source harness's folder | make it relative to the skill, or name the dependency in the text |

Show the plan and wait for the user's go-ahead before writing anything.

## 5. Write a copy, never the original

Write the ported skill into the target's folder (or a scratch folder the user names). The
original stays as it was - it still serves the harness it was written for. Keep the port to
the plan: a change nobody listed is a change nobody reviewed.

## 6. Verify, and say what is still unverified

```
sqs.py compat <copy> --harness <target>       Compatible, or only the unknowns you explained
sqs.py check <copy>                           the port broke no link and no field
```

A clean report means the copy matches the documentation, not that it works. Until the skill
has been invoked once in the target harness, say "ported, not yet run there" - ask the user
to call it once, and read what happened.

## 7. Report

What changed and why (with the quotes), what stays unknown and why, where the copy lives,
and the one test the user still has to run.
