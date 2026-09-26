#!/usr/bin/env python3
"""The harness adapter contract.

An adapter describes one agent environment: whether it loads skills, where from,
which frontmatter it reads, which directories it documents, and what it forbids. It
describes **only what decides compatibility** - not the harness's plugin ecosystem,
its commands, or its configuration language.

Adapters are data first. The base class does the classifying, so a new harness is a
file of declarations plus its documentation URL, and the engine above never changes.
That is the whole point of the split: adding a harness must not touch the core.

The honesty rule that governs every table below: **what the official documentation
does not state is UNKNOWN, never "unsupported"**. An adapter that guesses reads exactly
like one that verified, and the reader has no way to tell them apart. Where a field is
left as None here, that is a recorded gap, not a denial.
"""

# Verdict for one feature on one harness.
PORTABLE = "PORTABLE"                  # documented as read here
ADAPTABLE = "ADAPTABLE"                # works, or works after a mechanical change
HARNESS_SPECIFIC = "HARNESS_SPECIFIC"  # real here, dead or meaningless elsewhere
INVALID = "INVALID"                    # this harness refuses it
UNKNOWN = "UNKNOWN"                    # the documentation does not say

ORDER = [INVALID, UNKNOWN, HARNESS_SPECIFIC, ADAPTABLE, PORTABLE]

REQUIRED = "required"
OPTIONAL = "optional"
EXTENSION = "extension"                # this harness alone reads it


class Verdict:
    """One classification, with the reason and what to do about it.

    `supported` splits the two things HARNESS_SPECIFIC can mean, which are opposites:
    a field this harness alone reads (supported here, does not travel) and a path only
    other harnesses read (does not work here at all). Without the flag, `--harness
    claude-code` reports `model:` as a problem while a `.claude/skills` path on Cline
    would be waved through - the same status, read the same way, in both directions.
    """

    __slots__ = ("status", "reason", "recommendation", "supported")

    def __init__(self, status, reason="", recommendation="", supported=False):
        self.status = status
        self.reason = reason
        self.recommendation = recommendation
        self.supported = supported

    def __repr__(self):
        return f"<{self.status} {self.reason[:40]!r}>"


class HarnessAdapter:
    """One agent environment.

    Subclasses override the declarations. Overriding `classify` is a last resort: if
    two harnesses need different logic for the same kind of feature, the difference
    usually belongs in a declaration the base class already consults.
    """

    name = ""                 # stable id used on the command line
    title = ""                # what a human calls it
    docs = ""                 # the official page every row below rests on
    # The day every row below was last read against `docs`, as YYYY-MM-DD, or None for
    # never. A table that cannot say when it was last true rots without a sign: four of
    # the ten pages had moved by 23.09.2026, and fields had come and gone, while the
    # report read the same. Set it after reading the page, never as part of an edit.
    checked = None
    supports_skills = None    # True / False / None when the docs do not say

    skill_format = "SKILL.md with YAML frontmatter"
    locations = ()            # documented discovery paths, most specific first
    discovery = ""            # one line on how the harness finds and activates a skill

    # field -> REQUIRED / OPTIONAL / EXTENSION
    fields = {}
    # documented subdirectories inside a skill
    dirs = ()
    # does the harness document that every file in the skill's folder is available once
    # it loads? Then no directory name is a portability question
    reads_whole_folder = None
    # does it document that a file SKILL.md points at is loaded when needed? Then a
    # directory the skill links is not a question either, named or not
    loads_linked_files = None
    # documented ceilings; a field absent here has no documented limit
    limits = {}
    # does the harness document that `name` has to equal the folder name?
    name_matches_dir = None
    # does the harness document that it ignores frontmatter it does not know?
    ignores_unknown_fields = None
    # does the harness document `allowed-tools`, and under whose tool names?
    tool_namespace = None
    # body text this harness documents rewriting before the model reads it, spelled the
    # way `model.SkillModel` keys it: "$ARGUMENTS", "$N", "$name", "!`command`",
    # "${VARIABLE}"
    body_syntax = ()
    # anything else worth saying in a report, one line each
    notes = ()

    # ---- the contract the engine calls -----------------------------------

    def detect(self, root):
        """Whether this harness's own layout is present at `root`.

        Used to guess the targets when the user names none. A path match is evidence,
        not proof: a `.claude/skills` folder in a repository says the author had Claude
        Code in mind, nothing more.
        """
        import os
        for loc in self.locations:
            if loc.startswith("~") or loc.startswith("/") or ":" in loc[:3]:
                continue
            head = loc.split("/")[0]
            if head and os.path.isdir(os.path.join(root, head)):
                return True
        return False

    def get_capabilities(self):
        """Everything a report needs to explain a verdict."""
        return {
            "name": self.name, "title": self.title, "docs": self.docs,
            "checked": self.checked,
            "supports_skills": self.supports_skills, "format": self.skill_format,
            "locations": list(self.locations), "discovery": self.discovery,
            "fields": dict(self.fields), "dirs": list(self.dirs),
            "limits": dict(self.limits), "notes": list(self.notes),
        }

    def get_documentation_url(self):
        return self.docs

    # ---- classification ---------------------------------------------------

    def classify(self, feature, world):
        """How this harness treats one feature of the skill.

        `world` is the adapter registry, so a field can be recognised as *another*
        harness's extension rather than as something nobody has ever heard of. The two
        deserve different answers and only the registry can tell them apart.
        """
        handler = getattr(self, f"_kind_{feature.kind.replace('-', '_')}", None)
        if handler:
            return handler(feature, world)
        return Verdict(UNKNOWN, f"{self.title} does not document {feature.kind}")

    def _kind_frontmatter_field(self, feature, world):
        role = self.fields.get(feature.key)
        if role in (REQUIRED, OPTIONAL):
            return Verdict(PORTABLE, f"read by {self.title}")
        if role == EXTENSION:
            return Verdict(HARNESS_SPECIFIC,
                           f"`{feature.key}:` is a {self.title} extension",
                           "Keep it if this harness is a target; elsewhere it is inert.",
                           supported=True)
        owners = world.owners_of_field(feature.key)
        others = [o for o in owners if o != self.name]
        if others and self.ignores_unknown_fields:
            return Verdict(ADAPTABLE,
                           f"`{feature.key}:` belongs to {', '.join(others)}; "
                           f"{self.title} documents that it ignores fields it does not know",
                           "Nothing to do: it is inert here, not an error.")
        if others:
            return Verdict(UNKNOWN,
                           f"`{feature.key}:` belongs to {', '.join(others)}; "
                           f"{self.title} does not document what it does with it",
                           "Try it, or move the field under `metadata:`.")
        if self.ignores_unknown_fields:
            return Verdict(ADAPTABLE, f"{self.title} ignores frontmatter it does not know")
        return Verdict(UNKNOWN,
                       f"no harness in the registry documents `{feature.key}:`",
                       "Nest it under `metadata:`, which the specification reserves for this.")

    def _kind_layout_dir(self, feature, world):
        if feature.key in self.dirs:
            return Verdict(PORTABLE, f"{self.title} documents `{feature.key}/`")
        if self.reads_whole_folder:
            return Verdict(PORTABLE, f"{self.title} documents that every file in the "
                                     f"skill's folder is available")
        if feature.detail == "linked" and self.loads_linked_files:
            return Verdict(PORTABLE, f"{self.title} documents that files SKILL.md points "
                                     f"at are loaded when needed, and SKILL.md links "
                                     f"`{feature.key}/`")
        if feature.detail == "linked":
            return Verdict(ADAPTABLE,
                           f"{self.title} does not name `{feature.key}/`, and SKILL.md links "
                           f"into it",
                           "Usually fine, since a skill's own folder is readable once the "
                           "skill activates. Verify once on this harness.")
        return Verdict(UNKNOWN,
                       f"{self.title} does not document `{feature.key}/` and nothing links it",
                       "Link it from SKILL.md, or move it under a documented directory.")

    def _kind_body_syntax(self, feature, world):
        owners = world.owners_of_syntax(feature.key)
        if feature.key in self.body_syntax:
            if owners == [self.name]:
                return Verdict(HARNESS_SPECIFIC,
                               f"{self.title} rewrites {feature.label()} before the model "
                               f"reads it; no other harness documents that",
                               "Keep it if this harness is a target; elsewhere it may reach "
                               "the model as written.", supported=True)
            return Verdict(PORTABLE, f"{self.title} documents {feature.label()}")
        if owners:
            return Verdict(UNKNOWN,
                           f"{feature.label()} is rewritten by {', '.join(owners)}; "
                           f"{self.title} does not document it, so it may reach the model "
                           f"as written",
                           "If the skill has to travel, do not let a step depend on it: say "
                           "in prose what the value is or how to get it.")
        return Verdict(UNKNOWN, f"no harness in the registry documents {feature.label()}",
                       "Check the spelling against the harness that should rewrite it.")

    def _kind_tool(self, feature, world):
        if self.tool_namespace is None:
            return Verdict(UNKNOWN,
                           f"{self.title} does not document `allowed-tools`",
                           "Do not rely on the restriction holding here.")
        if self.tool_namespace == "claude-code":
            return Verdict(HARNESS_SPECIFIC,
                           f"`{feature.key}` is a {self.title} tool name",
                           "Tool names are not part of the skill specification; state the "
                           "restriction in the instructions as well.")
        return Verdict(UNKNOWN, f"`{feature.key}` under {self.title} tool names")

    def _kind_harness_path(self, feature, world):
        # The fragment is the head of a location (`.claude/skills`), the declaration is
        # the whole pattern (`.claude/skills/<name>/SKILL.md`), so the test is whether a
        # location starts with the fragment. Comparing the other way round matches
        # nothing and quietly reports every harness as not reading its own folder.
        frag = feature.key.replace("\\", "/").strip("/")
        if any(loc.replace("\\", "/").lstrip("~").lstrip("/").startswith(frag)
               for loc in self.locations):
            return Verdict(PORTABLE, f"{self.title} loads skills from `{feature.key}`")
        owner = world.owners_of_location(feature.key)
        others = [o for o in owner if o != self.name]
        return Verdict(HARNESS_SPECIFIC,
                       f"`{feature.key}` is where "
                       f"{', '.join(others) if others else 'another harness'} keeps skills; "
                       f"{self.title} does not read it",
                       "Point at the file relatively, or name the dependency in the text "
                       "instead of hard-coding a path.")

    # ---- validation -------------------------------------------------------

    def validate_skill(self, model):
        """[(status, message, recommendation)] for this harness's own hard rules.

        Only what the documentation states. A limit this harness never published is
        absent from `limits`, and absent means unchecked, not passed.
        """
        out = []
        for field, role in sorted(self.fields.items()):
            if role == REQUIRED and not model.fields.get(field):
                out.append((INVALID, f"`{field}:` is required by {self.title}",
                            f"Add `{field}` to the frontmatter."))
        for field, ceiling in sorted(self.limits.items()):
            value = model.fields.get(field) or ""
            if len(value) > ceiling:
                out.append((INVALID,
                            f"`{field}` is {len(value)} characters, over the {ceiling} "
                            f"{self.title} documents",
                            f"Shorten `{field}`."))
        if self.name_matches_dir and model.fields.get("name") and \
                model.fields["name"] != model.folder:
            out.append((INVALID,
                        f"{self.title} requires `name` to equal the folder "
                        f"(`{model.fields['name']}` vs `{model.folder}`)",
                        "Rename the folder or the field."))
        return out
