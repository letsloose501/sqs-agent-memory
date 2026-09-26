# Harness compatibility

<!-- sqs-allow-file: ST011, PB006 - the paths below are where OTHER environments keep
     their skills. They are this file's subject matter, not routes it takes, and
     none of them exists on the machine that reads it. -->

The one thing about a skill you cannot check on your own machine: it works here, and
whether it works anywhere else is a question your setup can never answer. This is the
module that answers it, and the rules it plays by.

```
python scripts/sqs.py harnesses               the registry: each row's page, and the day it was last read
python scripts/sqs.py harnesses --show        plus locations, discovery and caveats
python scripts/sqs.py compat <skill> --harness all
python scripts/sqs.py compat <skill> --harness cursor,codex --format json
python scripts/sqs.py check <skill> --harness all --strict     for CI
```

`compat` with harnesses prints the report below. `check --harness` folds the same
verdicts into the ordinary finding list as CP006 / CP007 / CP008, so a pipeline can
fail on them.

## The pipeline

```
Skill  ->  core.Skill        the file on disk
       ->  model.SkillModel  the normalized model: a list of features
       ->  harnesses/*       one adapter per environment, data first
       ->  portability.py    the engine: features x adapters -> verdicts
       ->  report            text, JSON, or findings for the normal pipeline
```

A feature is one thing the skill uses: a frontmatter field, a top-level directory, a
tool name out of `allowed-tools`, a hard-coded path into somebody's skill folder, or body
text a harness rewrites before the model reads it - `$ARGUMENTS`, a declared `$name`,
`${CLAUDE_SKILL_DIR}/...`, a load-time `` !`command` ``. Only Claude Code documents those
(checked against nine other pages, 23.09.2026), so elsewhere they come back UNKNOWN: they may
reach the model exactly as written. A placeholder counts where its value is used - a path
under a variable, `$ARGUMENTS` outside a heading - and not where a guide names the syntax.
Adapters classify features; they never read files. That is what keeps the engine
ignorant of any particular harness, which in turn is what makes adding one cheap.

## The five verdicts

| | Meaning |
|---|---|
| `PORTABLE` | the harness documents that it reads this |
| `ADAPTABLE` | it works, or works after a mechanical change |
| `HARNESS_SPECIFIC` | real on one harness, inert or absent on the others |
| `INVALID` | the harness publishes a rule that this breaks |
| `UNKNOWN` | the official documentation does not say |

**`UNKNOWN` is not `NOT_SUPPORTED`.** A gap in somebody's documentation is a gap in the
documentation. Printing it as an incompatibility invents one, and an invented
incompatibility reads exactly like a real one - which is how a compatibility tool stops
being believed. Where a table below has no entry, that is a recorded gap.

The per-harness headline is the most actionable thing found, not the worst-sounding:
`✗ Incompatible` when something is INVALID, then `⚠ Adaptation required`, then
`? Unknown`, and `✓ Compatible` when every feature is documented as read.

`HARNESS_SPECIFIC` carries two opposite meanings and the engine keeps them apart: a
field this harness alone reads (it works here, it just does not travel) and a path only
other harnesses read (it does not work here at all). With a single target, only the
second is reported as a problem by `check` - there is nowhere for the first to fail to
travel to. The `compat` report shows both, because there the question is different.

## What each harness reads

Ten adapters, each resting on that project's own documentation. Third-party write-ups
were used to find the pages and for nothing else.

| Harness | Own location | Also reads | Required | Documented directories |
|---|---|---|---|---|
| Claude Code | `.claude/skills`, `~/.claude/skills` | plugin `skills/` | name, description | references, scripts, assets |
| Codex | `.agents/skills`, `~/.agents/skills` | `/etc/codex/skills` | name, description | scripts, references, assets, agents |
| Cursor | plugin `skills/` | `~/.cursor/plugins/local` | name, description | skills, scripts, references, assets |
| Gemini CLI | `.gemini/skills`, `~/.gemini/skills` | `.agents/skills`, extensions | name, description | scripts, references, assets |
| Antigravity | `.agents/skills`, `~/.gemini/antigravity/skills` | `.agent/skills` (legacy) | **description only** | scripts, examples, resources |
| OpenCode | `.opencode/skills`, `~/.config/opencode/skills` | `.claude/skills`, `.agents/skills` | name, description | scripts, references, assets |
| Cline | `.cline/skills`, `~/.cline/skills` | - | name, description | docs, templates, scripts |
| Roo Code | `.roo/skills`, `~/.roo/skills` | `.agents/skills` | name, description | scripts, references, assets |
| Windsurf | `.windsurf/skills`, `~/.codeium/windsurf/skills` | `.claude/skills`, `.agents/skills` | name, description | scripts, references, assets |
| GitHub Copilot | `.github/skills`, `~/.copilot/skills` | `.claude/skills`, `.agents/skills` | name, description | **not published** |

The URLs are in each adapter and in `sqs.py harnesses`, so a verdict can always be
traced to the page it came from.

Three rows worth knowing by heart, because they are where identical-looking skills
diverge:

- **Antigravity makes `name` optional**, defaulting it to the folder. A skill relying on
  that is refused everywhere else, and `compat` is the only thing that will tell you.
- **OpenCode states that it ignores frontmatter it does not know.** That is why another
  harness's extension comes back ADAPTABLE there and UNKNOWN elsewhere: one of them
  published the behaviour and the others did not.
- **Copilot publishes no subdirectory names**, so every directory inside a skill comes
  back UNKNOWN there. The skill is probably fine; the documentation simply does not say.

Documented ceilings are checked where they exist - name 64 and description 1024 on
Claude Code, OpenCode and Roo Code; `name` equal to the folder on Claude Code, OpenCode
and Roo Code. A harness that published no ceiling has none checked, because unchecked
and passed are different things.

## Spec drift, which is a different question

`CP001` and `CP002` do not involve harnesses at all. The Agent Skills specification
names a small set of top-level fields and the strict reference validator refuses
everything else, while real clients warn and load anyway. So an extra field works
everywhere you would notice and fails at publication.

Where the field is a live extension of a real harness, `CP002` is **info** and says
what it costs. It never tells you to nest it under `metadata:`, because that would
switch the behaviour off. Only a field no harness in the registry reads gets that
advice.

## Adding a harness

Drop a file in `scripts/harnesses/`. Nothing else changes: the registry finds it, the
engine classifies through it, the report prints it.

```python
from .base import OPTIONAL, REQUIRED, HarnessAdapter

class Something(HarnessAdapter):
    name = "something"
    title = "Something"
    docs = "https://..."            # the page every line below rests on
    supports_skills = True
    locations = (".something/skills/<name>/SKILL.md",)
    fields = {"name": REQUIRED, "description": REQUIRED, "license": OPTIONAL}
    dirs = ("scripts", "references")
    limits = {"name": 64}           # leave out what the docs do not state
```

Then the rules that keep the table honest:

1. **One official page per adapter**, named in `docs`. If the project publishes nothing
   on skills, `supports_skills = None` and the tables stay empty.
2. **Leave out what you did not verify.** An empty `limits` means unchecked. A guessed
   ceiling is indistinguishable from a real one and turns a report into fiction.
3. **Run it against a skill you know works there** before trusting the row. A row nobody
   has tested against a real install is a guess wearing a table's clothes.
4. Overriding `classify` is a last resort. If two harnesses need different logic for the
   same kind of feature, the difference almost always belongs in a declaration the base
   class already reads.

## Plugins are containers, nothing more

Pointed at a plugin, the suite finds the skills inside it and says so:

```
plugin container `my-plugin`: 2 skill(s) checked, other plugin components
(commands, agents, hooks, manifest) were not analysed
```

That boundary is deliberate. Checking `plugin.json`, hooks, commands and agents is a
different tool's job, and a half-done version of it would be worse than none: it would
imply the rest had been looked at.

## Harnesses with no adapter yet

The official [client showcase](https://agentskills.io/clients) lists well over forty
products reading `SKILL.md`, each with a link to its own setup page. The registry here
holds ten. The rest are a recorded gap rather than a claim that they do not work:
Junie, Amp, Goose, VS Code, Kiro, Letta, OpenHands, Factory, Zed, Warp, Trae, Firebender,
Tabnine, Qodo, pi, Mux, Databricks, Snowflake, Spring AI, Laravel Boost and the others.

Adding one is the process above: read that product's own page, fill the declarations it
states, leave out what it does not, run the result against a skill you know works there.

Two cross-client facts from the client-implementation guide worth knowing whatever your
targets are:

- **`.agents/skills/` is the convention for cross-client sharing.** It is not in the
  specification, which defines only what goes inside a skill directory, but clients
  scan it so that skills installed by one are visible to the others. A skill meant to
  travel belongs there rather than in a vendor folder.
- **Real clients validate leniently**, and the guide says exactly how: a name that does
  not match its folder, or is over 64 characters, is a warning and the skill loads
  anyway; a missing or empty description, or unparseable YAML, and the skill is skipped.
  So the two failure classes are genuinely different, and the suite grades them that
  way: the first pair fail on `skills-ref validate` and at publication, the second pair
  fail everywhere, immediately.
