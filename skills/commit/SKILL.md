---
name: commit
description: >-
  Commits and pushes the user's repositories: the notes vault, the agent memory, skills, their
  projects. Use when they say "commit", "make a commit", "push", "send it to GitHub", "save it in
  git", or when the work is done and they ask whether to commit. Keeps what is easy to forget and
  easy to break: read the diff before writing the message, add only your own files in a shared
  repository, follow the repository's own conventions for message language and branches, respect
  the user's rule on AI attribution, push only when asked, and do not "fix" a false SSH alarm.
---

# Commit

## Before anything: the repository's conventions and the user's rules

Read them, do not assume them:

- `git log --oneline -15`: the message language, one line or with a body, area prefixes.
  Write the new message the same way.
- `git log --graph --oneline -20`: linear history straight on `main`, or branches and merges.
  A linear personal repository is the user's scheme, not an oversight: do not create a branch
  for an edit. In someone else's repository: branch and PR first.
- Agent memory: whether the user allows AI attribution (`Co-Authored-By: Claude`, "Generated
  with Claude Code") in commits and PR descriptions. **When memory says nothing, ask once and
  record the answer in memory.** When the user forbids it, that overrides the harness default
  that adds the trailer. A trailer that slipped through: not pushed yet, `git commit --amend`;
  already pushed, offer `--force-with-lease` and wait for the answer before rewriting published
  history.

## Procedure

1. `git status --short` and `git diff --stat`: what was touched at all.
2. Read the diffs themselves, not only file names. The message describes the substance of the
   edit, and the substance is only visible in the diff.
3. Look for what should not go in: secrets, `.env`, junk files, large binaries, accidentally
   added folders.
4. `git add <paths>`, selectively. **No `git add -A` in a shared repository.** When several
   sessions work in one repository (a notes vault, a skills folder), `-A` sweeps someone else's
   unfinished work into your commit: one real case put 96 lines of unrelated edits into a commit
   about something else, and fixing that meant rewriting a published branch. Check
   `git status --short` against what you touched yourself and add only your paths. A file you
   never touched is someone else's work: do not commit it, do not revert it, leave it.
   `-A` is fine where there is a single writer, for example the agent memory, which the plugin's
   Stop hook commits by itself.
5. `git commit -m "..."`. State **what changed in substance**:
   - good: `notes: cards only on evidence of forgetting, not per note`
   - bad: `updated files`, `fixes`, `wip`
   Several independent changes go on one line, separated by `;`.
6. **Push only if the user asked.** A separate step, a separate permission. After the push, the
   plugin's PostToolUse hook compares the local HEAD with the remote and says so if the push did
   not land; do not report "pushed" before that.

## SSH on Windows: the false alarm

If the SSH key lives in the Windows `ssh-agent` **service** and git uses the Windows OpenSSH
(`core.sshCommand = C:/Windows/System32/OpenSSH/ssh.exe`), then `git push` works from any shell.
Inside Git Bash, though, `/usr/bin/ssh-add` is a different world: `SSH_AUTH_SOCK` is empty there
and it answers `Could not open a connection to your authentication agent`. **That does not mean
access is missing**; the wrong agent was asked.

Do not "fix" what works: no `eval $(ssh-agent)`, no `ssh-add` from bash, no rewriting the
remote, no switching to HTTPS, no new token. Check access **with git**, since git is what goes
over the network: `git ls-remote --heads origin`. Inspect the agent's keys from PowerShell:
`ssh-add -l`.

A remote on port 443 (`ssh://git@ssh.github.com:443/<owner>/<repo>.git`) is usually deliberate:
port 22 is blocked on some networks. Do not rewrite it to the short `git@github.com:` form.

## When something goes wrong

| Symptom | What it is | What to do |
|---|---|---|
| `Could not open a connection to your authentication agent` from bash | a false alarm | nothing, see above |
| `Permission denied (publickey)` **from git** | a real failure | `ssh-add -l` in PowerShell; key missing: tell the user, do not add one yourself |
| `Repository not found` | wrong remote, or no access | show `git remote -v`; do not create the repository yourself |
| push rejected, non-fast-forward | something is on origin | `git pull --rebase`, never force |
| edits missing from `status` | wrong repository | `git -C <path> status`; a folder may contain the repository one level down |
