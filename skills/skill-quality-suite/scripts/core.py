#!/usr/bin/env python3
"""Shared parsing for every module of the suite.

One skill is read once and handed to every engine. Without that each module would
re-open the same files and, worse, parse the frontmatter its own way - and the
modules would start disagreeing about what the skill says.

Pure stdlib on purpose: the suite has to run from a git hook on a machine where
nothing was installed.
"""
import fnmatch
import os
import re
import unicodedata

SUBDIRS = ("references", "assets", "scripts", "templates")
IGNORE_FILE = ".sqsignore"
TEXT_EXT = (".md", ".txt")


class Finding:
    """One thing the suite has to say about one skill.

    `code` is the join key into rules.py; `severity` may differ from the rule's
    default when the engine knows the case is worse or milder than usual.
    """

    __slots__ = ("code", "severity", "msg", "skill", "root", "where", "line")

    def __init__(self, code, msg, severity=None, skill=None, where=None, line=None):
        self.code = code
        self.msg = msg
        self.severity = severity
        self.skill = skill          # the folder name, for the report
        self.root = None            # the folder's absolute path, for a real file URI
        self.where = where          # file inside the skill, if the finding has a place
        self.line = line

    def __repr__(self):
        return f"<{self.code} {self.severity} {self.msg[:40]!r}>"


def fold(s):
    """NFC-normalised casefold: `ё` stored as `е` + U+0308 compares equal to `ё`."""
    return unicodedata.normalize("NFC", s).casefold()


def path_exists(p):
    """Existence check that survives Unicode normalisation drift on Windows paths."""
    p = os.path.expandvars(os.path.expanduser(p))
    if os.path.exists(p):
        return True
    parent, base = os.path.split(p)
    if not base or not os.path.isdir(parent):
        return False
    want = unicodedata.normalize("NFC", base)
    try:
        return any(unicodedata.normalize("NFC", e) == want for e in os.listdir(parent))
    except OSError:
        return False


# A frontmatter key at the top level. Continuation lines are indented, so anchoring
# at column zero is what separates a key from a line of a block scalar.
FM_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$")


def parse_frontmatter(text):
    """Frontmatter as (raw, dict, style) without a YAML dependency.

    `style` records how each value was written - "plain", "quoted" or "block" - because
    a block scalar is a portability finding in its own right (SP015) and a plain parse
    would throw that away.

    Returns (None, {}, {}) when the file has no frontmatter at all.
    """
    if not text.startswith("---"):
        return None, {}, {}
    end = text.find("\n---", 3)
    if end == -1:
        return None, {}, {}
    raw = text[3:end].strip("\n")

    values, styles, key, buf, style = {}, {}, None, [], None
    for line in raw.split("\n"):
        m = FM_KEY_RE.match(line)
        if m:
            if key is not None:
                values[key] = " ".join(b.strip() for b in buf).strip()
                styles[key] = style
            key, rest = m.group(1), m.group(2).strip()
            if rest in (">", ">-", "|", "|-", ">+", "|+"):
                buf, style = [], "block"
            elif rest[:1] in "\"'" and rest[-1:] == rest[:1] and len(rest) > 1:
                buf, style = [rest[1:-1]], "quoted"
            else:
                buf, style = [rest], "plain"
        elif key is not None and line.strip():
            buf.append(line.strip())
    if key is not None:
        values[key] = " ".join(b.strip() for b in buf).strip()
        styles[key] = style
    return raw, values, styles


def read_ignores(root):
    """Path globs from `.sqsignore` at the skill root, relative to it."""
    path = os.path.join(root, IGNORE_FILE)
    if not os.path.isfile(path):
        return []
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.split("#", 1)[0].strip().lstrip("/")
                if line:
                    out.append(line.replace("\\", "/"))
    except OSError:
        return []
    return out


class Skill:
    """A skill on disk, read once."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.folder = os.path.basename(self.root)
        self.md_path = os.path.join(self.root, "SKILL.md")
        self.ok = os.path.isfile(self.md_path)
        self.text = ""
        if self.ok:
            with open(self.md_path, encoding="utf-8", errors="replace") as f:
                self.text = f.read()
        self.size = len(self.text.encode("utf-8"))
        self.fm_raw, self.fm, self.fm_style = parse_frontmatter(self.text)
        if self.fm_raw is None:
            self.body = self.text
        else:
            self.body = self.text[self.text.find("\n---", 3) + 4:]
        self.name = self.fm.get("name", "")
        self.description = self.fm.get("description", "")
        self.ignores = read_ignores(self.root)

    @property
    def slash_only(self):
        return self.fm.get("disable-model-invocation", "").lower() == "true"

    def ignored(self, rel):
        """Whether `.sqsignore` takes this path out of every engine's view.

        For material that sits inside the skill folder and is not skill payload: a
        test corpus, vendored third-party files, generated output. It is not a way to
        silence a finding - that is what `sqs-allow` and the config are for. What is
        listed here is not read at all, so nothing about it is checked and nothing
        about it is claimed.
        """
        rel = rel.replace("\\", "/")
        for pat in self.ignores:
            if fnmatch.fnmatch(rel, pat) or rel == pat.rstrip("/"):
                return True
            head = pat.rstrip("/") + "/"
            if rel.startswith(head) or fnmatch.fnmatch(rel, head + "*"):
                return True
        return False

    def walk(self):
        """(relative path, bytes size, is-text) for every file the skill carries."""
        for dirpath, dirnames, files in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__" and not d.startswith(".")
                           and not self.ignored(os.path.relpath(os.path.join(dirpath, d),
                                                                self.root))]
            for fn in files:
                if fn.startswith("."):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, self.root).replace("\\", "/")
                if self.ignored(rel):
                    continue
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                yield rel, size, fn.endswith(TEXT_EXT)

    def texts(self):
        """(relative path, contents) for SKILL.md and every text file under it.

        This is what the text-reading engines iterate. SKILL.md comes first so a
        report reads top-down.
        """
        yield "SKILL.md", self.text
        for rel, _, is_text in sorted(self.walk()):
            if rel == "SKILL.md" or not is_text:
                continue
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8", errors="replace") as f:
                    yield rel, f.read()
            except OSError:
                continue


def discover(skills_dir, names=None):
    """Every skill folder under `skills_dir`, or only the named ones."""
    if names:
        return [Skill(os.path.join(skills_dir, n)) for n in names]
    out = []
    for d in sorted(os.listdir(skills_dir)):
        full = os.path.join(skills_dir, d)
        if d.startswith(".") or not os.path.isdir(full):
            continue
        if os.path.isfile(os.path.join(full, "SKILL.md")):
            out.append(Skill(full))
    return out


def line_of(text, index):
    """1-based line number of a character offset, for a finding that has a place."""
    return text.count("\n", 0, index) + 1


INLINE_CODE_RE = re.compile(r"`{1,2}[^`\n]+`{1,2}")


def strip_code(text):
    """The same text with code blanked out, newlines kept.

    Fenced blocks and inline spans both go: inside them the text is a quotation of a
    literal, not an instruction. Without this, a skill that lists `fix` and `wip` as
    bad commit messages is reported for containing placeholders, and a linter that
    cries wolf stops being read.
    """
    text = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), text)
    out, i, n = [], 0, len(text)
    fence = re.compile(r"^(`{3,}|~{3,})", re.M)
    while i < n:
        m = fence.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        marker = m.group(1)
        close = re.compile(r"^" + re.escape(marker) + r"[ \t]*$", re.M)
        c = close.search(text, m.end())
        end = c.end() if c else n
        out.append("\n" * text.count("\n", m.start(), end))
        i = end
    return "".join(out)
