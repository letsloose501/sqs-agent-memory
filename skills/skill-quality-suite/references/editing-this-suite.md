# Editing this suite

What to run and what to keep true when the change is to skill-quality-suite itself,
not to a skill it checks.

Commands below run from the repository root. The skill is `skills/skill-quality-suite/`;
the corpus (`tests/`), the page generator (`tools/`), the documentation site (`docs/`) and
CI sit beside it, because an installer copies only the skill's folder, and a corpus of
deliberately malicious skills has no place in somebody's skills directory.

The rule codes are the join key of the whole thing: `rules.py` is the single place a code
is defined, and every engine emits codes from it. After adding or changing a rule:

```
python skills/skill-quality-suite/scripts/sqs.py rules --audit
                                           registry against the engines, and against the corpus
python tests/run_tests.py               every case, then the unit checks
```

`rules --audit` fails when an engine emits a code the registry does not carry, when the
registry carries a row nothing emits, or when a rule has no confidence and
false-positive grading. It also reports how many rules the corpus has ever observed
firing.

Two pages are generated rather than written, because a hand-written page about a tool
is a snapshot of what the tool did the day somebody wrote it:

```
python tools/build_docs.py              docs/quality-rules.md and examples/README.md
python tools/build_docs.py --check      fails when either has gone stale
```

`tests/fixtures/` is that corpus: small skills trees with an `expect.json` beside each,
listing the codes the suite must report and the codes it must not. A new rule needs a
**positive** case there - a rule nobody has watched fire is not a rule that works - and
the two cases that matter most are `clean/` and `escape-hatches/`, which must report
**nothing at all**. A linter is judged by what it stays quiet about.

The evaluation layer has its own fixture, `tests/evaluation/`, driven by the `fake`
provider: it replays canned runs so the confusion matrix, the two arms and the
regression diff are tested without a model in the loop.

The structure module is `scripts/check_skills.py`, imported rather than shelled out to.
It also runs standalone, and as a `PostToolUse` + `Stop` hook pair. Parsing its printed
output back into findings would be a second, drifting source of truth, so it carries the
rule codes itself.

A new harness is one file in `scripts/harnesses/` and nothing above it changes: the
registry finds it, the engine classifies through it, the report prints it. Its
declarations come from that project's own documentation, and what the documentation
does not state is left out - an empty `limits` means unchecked, which is not the same
as passed.

New heuristics earn their place by being **checkable**: a rule that cannot name a file
and a line does not belong in a linter - it belongs in the reading pass, where a human
applies judgement. A linter that cries wolf stops being read, and then the real findings
go unread with it.
