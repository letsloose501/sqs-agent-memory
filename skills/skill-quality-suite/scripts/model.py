#!/usr/bin/env python3
"""The normalized skill model: what a skill *uses*, independent of any harness.

`core.Skill` is the file on disk. This is the layer above it: the skill reduced to a
list of features - a frontmatter field, a directory, a tool name, a hard-coded path
into some harness's skill folder. Adapters classify features; they never read files.

That separation is what keeps a new harness cheap. An adapter answers "what do I do
with feature X", and it can only answer that if X arrives in a shape nobody's parser
invented on the spot.
"""
import re

from core import Skill, strip_code

# A path into a harness's skill tree, hard-coded in the text. The alternatives come
# from the adapter registry, so a new harness widens this automatically.
_PATH_TAIL = r"[\w./<>-]*"

# A placeholder a harness substitutes in the body; a backslash before `$` escapes it.
SUBST_RE = re.compile(r"(?<!\\)\$(?:\{(?P<var>[A-Z][A-Z0-9_]*)\}|(?P<args>ARGUMENTS)(?:\[\d+\])?"
                      r"|(?P<pos>\d+)|(?P<name>[A-Za-z_][\w-]*))")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _without_fences(text):
    """The text with fenced code blocks blanked out, line count kept."""
    out, fence = [], None
    for line in text.split("\n"):
        m = _FENCE_RE.match(line)
        if m and fence is None:
            fence = m.group(1)[0]
            out.append("")
            continue
        if m and fence is not None and m.group(1)[0] == fence:
            fence = None
            out.append("")
            continue
        out.append("" if fence else line)
    return "\n".join(out)


def parse_tools(raw):
    """`allowed-tools` as {tool name: [scopes]}, in the order the entries were written.

    Module-level rather than inside `SkillModel`, because `publish` compares two
    versions of the same field and has to read it exactly the way the adapters do - a
    second parser that splits on commas turned `Agent(a, b, c)` into three tools.
    """
    if not raw:
        return {}
    raw = re.sub(r"(?:^|\s)-\s+", " ", raw.replace("[", " ").replace("]", " "))
    scopes = {}
    for m in re.finditer(r"([A-Za-z][\w:.-]*)(?:\(([^)]*)\))?", raw):
        name, scope = m.group(1), (m.group(2) or "").strip()
        scopes.setdefault(name, [])
        if scope:
            scopes[name].append(scope)
    return scopes


class Feature:
    """One thing the skill uses, in a shape an adapter can judge."""

    __slots__ = ("kind", "key", "detail", "where", "line")

    def __init__(self, kind, key, detail="", where=None, line=None):
        self.kind = kind
        self.key = key
        self.detail = detail
        self.where = where
        self.line = line

    def label(self):
        return {
            "frontmatter-field": f"`{self.key}:`",
            "layout-dir": f"`{self.key}/`",
            "tool": f"tool `{self.key}`",
            "harness-path": f"path `{self.key}`",
            "body-syntax": f"`{self.key}` in the body",
        }.get(self.kind, f"{self.kind} {self.key}")

    def __repr__(self):
        return f"<{self.kind} {self.key}>"


class SkillModel:
    """A skill as features, plus the few raw facts adapters validate directly."""

    def __init__(self, skill, world=None):
        self.skill = skill
        self.folder = skill.folder
        self.fields = dict(skill.fm)
        self.body = skill.body
        self.features = []
        if skill.ok:
            self._extract(world)

    # ---- extraction -------------------------------------------------------

    def _extract(self, world):
        for key in sorted(self.fields):
            self.features.append(Feature("frontmatter-field", key, where="SKILL.md"))

        self._dirs()
        self._tools()
        self._paths(world)
        self._body_syntax()

    def _body_syntax(self):
        """Text in the body a harness rewrites before the model sees it.

        `$ARGUMENTS`, `$0`, a declared `$name`, `${CLAUDE_SKILL_DIR}` and the like are
        replaced with values, and `` !`cmd` `` with a command's output - on a harness that
        documents them. Elsewhere they may reach the model exactly as written, and a step
        that reads their value reads the placeholder instead.

        Placeholders are counted outside fenced blocks only: a hook config quoted in a code
        block to explain the syntax is documentation, and on another harness it should stay
        literal. Inline code counts, because that is where a command the agent is told to
        run is written. A command injection counts everywhere - it runs inside an ordinary
        code block too (`CB004`). A bare `$1` counts only when the skill takes arguments,
        or every price in prose would read as a placeholder.
        """
        from capabilities import _injections                        # noqa: PLC0415
        body, offset = self.body, self.skill.text.count("\n", 0, len(self.skill.text)
                                                        - len(self.body))
        visible = _without_fences(body)
        named = set(re.findall(r"[A-Za-z_][\w-]*", str(self.fields.get("arguments", ""))))
        # declared, not mentioned: a guide to the syntax says `$1` without taking any
        takes_args = bool(named) or "argument-hint" in self.fields
        for m in SUBST_RE.finditer(visible):
            line_start = visible.rfind("\n", 0, m.start()) + 1
            if visible[line_start:m.start()].lstrip().startswith("#"):
                continue                   # a heading names the syntax; it uses nothing
            if m.group("var"):
                # A variable is a step when a path hangs off it - `${CLAUDE_SKILL_DIR}/x.py`.
                # "Use ${CLAUDE_PLUGIN_ROOT} for portability" is a guide naming the term:
                # measured on the 51 skills here, every bare mention sat in such a guide.
                if not visible.startswith("/", m.end()):
                    continue
                key = "${" + m.group("var") + "}"
            elif m.group("args"):
                key = "$ARGUMENTS"
            elif m.group("pos"):
                if not takes_args:
                    continue
                key = "$N"
            elif m.group("name") in named:
                key = "$name"
            else:
                continue
            self.features.append(Feature("body-syntax", key, m.group(0), where="SKILL.md",
                                         line=offset + visible.count("\n", 0, m.start()) + 1))
        for line, command, _ in _injections(self.skill):
            self.features.append(Feature("body-syntax", "!`command`", command,
                                         where="SKILL.md", line=line))

    def _dirs(self):
        """Top-level directories, marked by whether anything in the text links them.

        The distinction matters: a skill's own folder becomes readable once the skill
        activates, so a directory that SKILL.md links is very likely reachable even on a
        harness whose documentation never names it. A directory nothing links is not
        reachable anywhere, and that is a different problem.
        """
        import os
        try:
            entries = sorted(os.listdir(self.skill.root))
        except OSError:
            return
        text = "\n".join(t for _, t in self.skill.texts())
        for e in entries:
            if e.startswith(".") or e == "__pycache__" or self.skill.ignored(e):
                continue
            if not os.path.isdir(os.path.join(self.skill.root, e)):
                continue
            linked = re.search(r"(?<![\w-])" + re.escape(e) + r"/", text) is not None
            self.features.append(
                Feature("layout-dir", e, "linked" if linked else "unlinked", where=e))

    def _tools(self):
        """Entries of `allowed-tools`, which are harness tool names, not spec vocabulary.

        Three spellings, all seen in published skills: an inline list `[Read, Glob]`, a
        YAML block list that the flat frontmatter parser folds into `- Read - Write -
        Bash(ls *)`, and scoped entries whose parentheses carry a command pattern rather
        than part of the name.

        The first version matched `[A-Za-z][\\w:.()-]*`, which stops at the space inside
        `Bash(ls *)` and yields the tool name `Bash(ls`. Measured against the official
        plugin marketplace on disk: every scoped entry came out truncated, and one
        published skill with a long scoped list produced forty "tool names" that were
        fragments of shell commands - `p`, `null`, `git`, `maxdepth` - each then handed
        to an adapter to be judged as harness tool vocabulary. The scope belongs in
        `detail`, where an adapter can ignore it; only the name is the name.
        """
        for name, found in parse_tools(self.fields.get("allowed-tools", "")).items():
            detail = "scoped to " + "; ".join(found) if found else ""
            self.features.append(Feature("tool", name, detail, where="SKILL.md"))

    def _paths(self, world):
        """Hard-coded paths into some harness's skill tree.

        The one portability failure that survives every other check: the skill runs
        perfectly on the machine it was written on, and on any other harness the path
        resolves to nothing - in silence, because a missing reference is a skipped step,
        not an error.
        """
        if world is None:
            return
        fragments = sorted(world.location_fragments(), key=len, reverse=True)
        if not fragments:
            return
        alts = "|".join(re.escape(f) for f in fragments)
        rx = re.compile(r"(?<![\w-])(" + alts + r")" + _PATH_TAIL)
        for rel, text in self.skill.texts():
            for m in rx.finditer(strip_code(text) if rel.endswith(".md") else text):
                self.features.append(Feature(
                    "harness-path", m.group(1), m.group(0),
                    where=rel, line=text.count("\n", 0, m.start()) + 1))

    # ---- views ------------------------------------------------------------

    def unique(self):
        """Features deduplicated by (kind, key); the first occurrence keeps the place."""
        seen, out = set(), []
        for f in self.features:
            if (f.kind, f.key) in seen:
                continue
            seen.add((f.kind, f.key))
            out.append(f)
        return out


def model_of(path_or_skill, world=None):
    skill = path_or_skill if isinstance(path_or_skill, Skill) else Skill(path_or_skill)
    return SkillModel(skill, world)
