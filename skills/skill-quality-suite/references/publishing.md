# Before the skill leaves the machine

Everything here is invisible while the skill only runs at home, and obvious the moment
somebody else installs it.

```
python scripts/sqs.py all <skill> --strict --agents claude-code --lang en
```

`all` is `check` plus the publish module. `--strict` makes warnings count, which is what
you want on the last pass and not before.

## The gate

Nothing goes out until every one of these is true.

1. **`check --strict` is clean.** Errors are non-negotiable; warnings at this stage are
   decisions, so make each one consciously and write the reason in `sqs.config.json`
   rather than leaving it to be rediscovered.
2. **No secret ever existed in the file.** `SE001` reads the working tree, not the
   history. If a credential was ever committed, rotate it - removing it now leaves it in
   every clone.
3. **No path that only resolves on your machine** (`PB003`). `~` is fine; an absolute
   path naming an account is not, and it publishes whose machine it is.
4. **No pointer into material the reader has no copy of** (`PB006`) - a personal vault,
   a private repository, an email address. A skill that reads a note before working
   degrades in silence for anyone without that note: the theory is simply gone and the
   work goes on anyway.
5. **A license** (`PB001`). Without one nobody may legally reuse the skill.
6. **A README for the human** (`PB002`). SKILL.md talks to the agent. Somebody deciding
   whether to install needs a page that talks to them: what it does, what it needs
   installed, what it refuses to do.
7. **Manifest and skill agree on the version** (`PB005`).
8. **Only the skill ships** (`PB015`). A `SKILL.md` at the repository root beside
   `tests/`, `docs/` or `.github/` means the installer copies all of it, and marketplace
   scanners read a test fixture of an attack as an attack. Keep the skill in
   `skills/<name>/`. Marketplace audits (skills.sh) run when a version is installed, not
   when it is committed, so the installed version is the one judged.
9. **One documentation language, and it is the repository's** (`PB004`, with `--lang`).
   Translate rather than mix. The exception worth keeping is a skill whose subject is
   the language - one working with local services, local retail, local paperwork; there
   the examples are the content.

## What the publish module cannot see

- **Whether the skill still works after the personal paths came out.** Strip them, then
  run the skill once end to end. This is the step people skip, and it is the one that
  breaks: a route that used to resolve through a vault note now resolves nowhere, and
  nothing errors.
- **Whether the description means anything to a stranger.** Yours is tuned to the
  wordings you use. Read it as somebody who has never seen the skill: does it say what
  the thing is before it says when to fire?
- **Whether the references still make sense unbundled.** A reference that starts
  "as in the other skill" is a dangling pointer once the other skill is not installed.

## The forked-copy trap

A published copy of a local skill is a **fork, not a mirror**. Paths differ; language
heuristics differ; the local version keeps machine-specific routing the public one must
not have. That means:

- the two files drift, and the drift is invisible until somebody reports a bug you
  cannot reproduce;
- `cp` over the public copy silently reintroduces whatever the fork deliberately removed.

Port edits deliberately, one at a time, and run `sqs.py all --strict --lang <language>`
on the published copy afterwards - not on the local one you just edited.
