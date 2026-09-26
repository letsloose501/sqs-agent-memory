#!/usr/bin/env python3
"""
Integrity check for Claude Code skills - backpressure for two-stage loading.

A skill loads in two stages: SKILL.md first, then its references through the links
inside it. When a link is broken the agent does not crash and does not complain:
it silently skips the step, and the only way to notice is that the work came out
worse than usual. This script turns that silent breakage into a loud one.

Usage:  python check_skills.py                        # every skill
        python check_skills.py my-skill other-skill   # only these
        python check_skills.py --skills-dir ~/.claude/skills

Where the skills live is decided in this order: the `--skills-dir` flag → the
`CLAUDE_SKILLS_DIR` environment variable → the script's own folder, if skills sit
in it → `~/.claude/skills`.

What it catches:
  1. Broken routing - SKILL.md points at a references/… file that is not there.
     This is the main failure when a chunk is moved out into a reference: the
     instruction "open X" without X turns into a silently skipped step.
  2. Broken sibling links - inside references/ a neighbour is linked in the short
     markdown form, [text](neighbour.md). Check (1) cannot see those: different shape.
  3. Link to a skill that does not exist - ~/.claude/skills/<name>/… after a rename.
  4. Orphans - a file in references/ that nothing links to. A pruning candidate:
     either it was never wired up, or it is no longer needed.
  5. Oversized SKILL.md - it is loaded in full on every activation (see BUDGET).
  6. Broken frontmatter - without name/description the skill never activates.
  7. Agent Skills spec violations in the frontmatter: `description` length (1024
     max), the format and length of `name`, `name` not matching the folder,
     `compatibility` length (500 max). Claude Code does not enforce these limits
     today, so the breakage is silent: it works locally and falls over when the
     skill is published or run through `skills-ref validate`. Hence ⚠️, not ⛔.
  8. Broken section pointer - `references/foo.md` → "Section" where that heading no
     longer exists in the file. The file is in place, so check (1) stays quiet while
     the agent opens the reference and does not find what it came for. It breaks on
     a renamed heading, that is, on ordinary editing, with no file moves at all.
  9. Broken outbound path - a skill points at `~/Desktop/…/Note.md` and the note was
     renamed. For skills that read a knowledge vault before working this is the main
     source of silent degradation: the theory is gone and the work goes on anyway.
     Cyrillic is compared normalized: "ё" is sometimes stored as "е" + U+0308 (NFD),
     and then a live file reads as a missing one. A missing path through a tool's own
     folder (a dot-folder or a platform config root) is ST017, a warning: a tool not
     installed on this machine looks exactly like a broken path.
 10. Unknown frontmatter key - a typo such as `descriptoin:` kills the skill in
     silence: no field means no description, which means the agent never calls it.
 11. Duplicate `name:` across skills - one shadows the other, and which one wins is
     not something you can tell in advance.
 12. Oversized reference - references/ are read in full once they are reached. A
     30 KB file cancels the point of two-stage loading (see REF_BUDGET).
 13. Skill with no body - frontmatter present, instructions missing: it activates
     and says nothing.
 14. Too short a `description` - two words hold no trigger conditions, and trigger
     conditions are the only thing the agent uses to decide whether to open the
     skill (see DESC_MIN).
 15. Code as prose - a long block in an executable language sitting in the skill
     text (see SCRIPT_LINES). A step that is always done the same way belongs in
     `scripts/`, not in a paragraph: code in prose is retyped by the model every
     time, that is, probabilistically and for tokens, and it can neither be run nor
     fixed once and for all. The instruction only has to say when to call the script
     and how to read its output. Teaching pairs are exempt (see EXAMPLE_RE): that
     kind of code is shown, not executed, and in a file it would be dead.

Flags:
  --quiet   say nothing when everything is clean; print problems only
  --mark    PostToolUse hook mode: check nothing, only remember which skills were
            touched during the turn. Edits outside the skills folder are ignored.
            Understands Write/Edit (file_path) and Bash (command): without parsing
            the command the check is blind to edits made through heredoc, sed, mv
            and rm.
  --stop    Stop hook mode: if no skill was touched during the turn, stay silent;
            otherwise run the full check and block the stop until the errors are
            fixed. Checking at the end of the turn is deliberate: on PostToolUse the
            skill is still half-written, and a fresh SKILL.md would complain about
            references/ that the author is about to create with the next command.
  --hook    deprecated synonym for --mark.

Exit codes: 0 - clean, 1 - errors (⛔), 2 - the same in hook mode (the only code the
harness passes on to the model). Warnings (⚠️) never fail the run.
"""
import glob
import json
import os
import re
import sys
import unicodedata
from collections import namedtuple

# A finding carries its rule code: the code is what `sqs.py explain` looks up,
# what a config file switches off, and what CI annotations group by. Prose alone
# cannot be any of those.
F = namedtuple("F", "code msg")

BUDGET = 15_000          # SKILL.md bytes - soft ceiling (~5-6k tokens per activation)
REF_BUDGET = 25_000      # reference bytes - it is opened whole, nobody splits it for you
DESC_MIN = 60            # shorter than this and a description holds no trigger conditions
SCRIPT_LINES = 15        # lines of code in prose - above this the block must become a file
SUBDIRS = ("references", "assets", "scripts", "templates")

# Languages in which a block in the text is a program, not an illustration. markdown,
# yaml, json and text are out: there a block shows the shape of a result, not a step.
CODE_LANGS = {"python", "py", "bash", "sh", "shell", "powershell", "ps1", "pwsh"}

# Frontmatter keys that mean something: the Agent Skills specification plus what
# Claude Code understands. Anything else is almost certainly a typo, and a typo in a
# key is not a syntax error: the field simply disappears along with its meaning.
KNOWN_KEYS = {
    "name", "description", "license", "compatibility", "allowed-tools",
    "metadata", "version",
    "disable-model-invocation", "model", "argument-hint", "user-invocable",
}


def resolve_skills_dir(argv):
    """Where the skills live.

    "The script's folder is the skills folder" is not safe to assume: the script can
    sit at the root of the skills tree, inside somebody's scripts/, or anywhere else.
    Hence the order: explicit flag → environment variable → the script's own folder,
    if skills really do sit in it → the standard location.
    """
    for i, a in enumerate(argv):
        if a == "--skills-dir" and i + 1 < len(argv):
            return os.path.abspath(os.path.expanduser(argv[i + 1]))
        if a.startswith("--skills-dir="):
            return os.path.abspath(os.path.expanduser(a.split("=", 1)[1]))
    env = os.environ.get("CLAUDE_SKILLS_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    here = os.path.dirname(os.path.abspath(__file__))
    if glob.glob(os.path.join(here, "*", "SKILL.md")):
        return here
    return os.path.expanduser(os.path.join("~", ".claude", "skills"))


SKILLS_DIR = resolve_skills_dir(sys.argv[1:])
# The "skills were touched this turn" mark: --mark writes it, --stop reads and clears
# it. Without it the Stop hook would have to run after every turn in every project.
MARKER = os.path.join(SKILLS_DIR, ".check-pending")

# A link to a file inside the skill: `references/foo.md`, `scripts/bar.py`.
# The negative lookbehind cuts off the case where the same "folder/file" pair turns
# out to be the tail of SOMEBODY ELSE'S path: `~/tools/scripts/x.py`
# is a tool outside the skills tree, and checking for it inside the skill folder makes
# no sense. Without this, any link to an external script is a false "file is missing".
LINK_RE = re.compile(r"(?<![\w./\\-])(?:" + "|".join(SUBDIRS) + r")/[\w./-]+\.\w+")
# cross-skill link: .../skills/<other skill>/references/foo.md or .../SKILL.md
CROSS_RE = re.compile(
    r"skills/([\w-]+)/((?:(?:" + "|".join(SUBDIRS) + r")/[\w./-]+\.\w+)|SKILL\.md)")
# a templated link to a directory: references/institutions/<slug>.md → the whole folder
WILDCARD_RE = re.compile(r"((?:" + "|".join(SUBDIRS) + r")/[\w./-]*?)/?<[^>]+>\.\w+")
# a markdown link to a neighbour in the same folder: [text](neighbour.md)
SIBLING_RE = re.compile(r"\]\((?!https?:|#)([\w.-]+\.\w+)\)")

# A path outside the skill - into a knowledge vault or into another skill. Only what
# sits entirely in backticks is taken: note names contain spaces and dashes, and such
# a path cannot be cut out of running prose without grabbing extra words.
VAULT_RE = re.compile(r"`([~$][^`\n]{3,200})`")

# A pointer to a section of a reference: `references/foo.md` → "Section" / «Раздел».
# Guillemets are not allowed between the file and the pointer: without that the window
# jumps over unrelated text and grabs a quotation that has nothing to do with a section.
#
# Both languages are matched on purpose. This script runs over skills written in
# Russian and in English, and a matcher that knows only one of them does not report
# less - it silently reports nothing, which is the failure mode the whole file exists
# to prevent.
SECPTR_RE = re.compile(
    r"((?:" + "|".join(SUBDIRS) + r")/[\w./-]+\.md)`?"      # the file
    r"[^\n«»]{0,40}?"                                       # a little text, no guillemets
    r"(?:→|->|sections?|раздел[аыов]*)"                     # an explicit section marker
    r"([^\n]{0,140})"                                       # rest of the line: sections live there
)
SECTION_RE = re.compile(r"«([^»]{2,80})»|\"([^\"\n]{2,80})\"|“([^”\n]{2,80})”")

# A code block in the text: ```python … ```. The fence length is remembered so that a
# nested block inside an example does not cut the outer one short.
CODE_RE = re.compile(r"^(?P<fence>`{3,})[ \t]*(\w+)[^\n]*\n(.*?)^(?P=fence)", re.M | re.S)

# Code that DEMONSTRATES rather than EXECUTES. A "bad - good" pair is teaching
# material: moving it into scripts/ would be throwing it away, not optimizing it.
# Length here is a sign of a thorough example, not of debt.
#
# The marker has to LABEL the block - to stand on its own line as a heading, usually
# in a comment (`# WRONG`). Looking for it anywhere inside the code is not allowed:
# words like "before" and "after" show up in ordinary comments, and "❌" shows up in a
# string that a real script prints. That exemption once hid a 49-line draft script,
# the very thing this check was written for.
#
# Russian and English markers both, for the reason given above SECPTR_RE.
EXAMPLE_RE = re.compile(
    r"^[ \t]*(?:#+|//)?[ \t]*"
    r"(?:WRONG|RIGHT|BAD|GOOD|BEFORE|AFTER|DON'T|DO|"
    r"НЕПРАВИЛЬНО|ПРАВИЛЬНО|ПЛОХО|ХОРОШО|БЫЛО|СТАЛО|ДО|ПОСЛЕ|❌|✅)"
    r"[ \t]*[-—:,]?[^\n]{0,60}$", re.M)

# Agent Skills specification: agentskills.io/specification.md
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DESC_MAX = 1024
NAME_MAX = 64
COMPAT_MAX = 500


def path_exists(p):
    """Whether such a file or folder exists, allowing for Unicode normalization.

    In one and the same string "ё" can be a single character (NFC) or the pair
    "е" + U+0308 (NFD). The bytes differ, the eye cannot tell, and `os.path.exists`
    answers "no" about a file that is there. So a miss is rechecked by comparing the
    names in the folder normalized.
    """
    p = os.path.expanduser(p.replace("$HOME", "~").replace("${HOME}", "~"))
    p = p.rstrip("/\\") or p
    if os.path.exists(p):
        return True
    parent, base = os.path.split(p)
    if not base or not os.path.isdir(parent):
        return False
    want = unicodedata.normalize("NFC", base).casefold()
    try:
        return any(unicodedata.normalize("NFC", n).casefold() == want
                   for n in os.listdir(parent))
    except OSError:
        return False


# Where tools keep their own state under the home folder: a dot-folder (`~/.claude`,
# `~/.config/<tool>`, `~/.mempalace`) or a platform config root. A path in there that this
# machine lacks is most often a tool not installed HERE (a CI runner, a fresh laptop), not a
# note that was renamed, and the two cannot be told apart from the text. Watched four times:
# `~/.claude/projects/`, `~/.claude/settings.json`, `~/.mempalace/config.json` and
# `~/.config/browser-harness/` each passed on the author's machine and failed ST011 on a clean
# runner, and each time the text was reworded to dodge the check.
CONFIG_ROOTS = (("appdata",), ("library", "application support"), ("library", "preferences"))


def environment_path(p):
    """Whether a home path runs through a tool's own folder rather than the user's files."""
    p = p.replace("$HOME", "~").replace("${HOME}", "~").replace("\\", "/")
    parts = [x for x in p.split("/")[1:] if x]
    if any(x.startswith(".") for x in parts[:-1]) or (parts and parts[0].startswith(".")):
        return True
    low = [x.casefold() for x in parts]
    return any(tuple(low[:len(root)]) == root for root in CONFIG_ROOTS)


def vault_paths(text):
    """Outbound paths from backticks - without templates and placeholders.

    `<name>.md` and `*` are the shape of a path, not a path: there is nothing to check.
    """
    out = set()
    for raw in VAULT_RE.findall(text):
        p = raw.strip().rstrip(".,;:)»")
        if not p.startswith(("~/", "~\\", "$HOME", "${HOME}")):
            continue
        if any(c in p for c in "<>*?|"):
            continue
        if " " in p and not re.search(r"\.\w{1,5}$|/$", p):
            continue                      # "~/something or other" from prose, not a path
        out.add(p)
    return out


def fm_field(fm, key):
    """A frontmatter key's value, block scalars (`>-`, `|`) included, collapsed to a line."""
    m = re.search(
        rf"^{key}:[ \t]*(>[-+]?|\|[-+]?)?[ \t]*\n?(.*?)(?=^[A-Za-z_][\w-]*:|\Z)",
        fm, re.M | re.S)
    return " ".join(m.group(2).split()) if m else None


def headings(path):
    """The set of a file's headings, normalized for comparison."""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return set()
    # MULTILINE is mandatory: without it ^ and $ only match the very start and end of
    # the text, no headings are collected at all, and the check idles while reporting
    # everything is clean.
    return {" ".join(h.split()).casefold()
            for h in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M)}


def collect(text, mentioned, cross, wildcard_dirs, cross_full=None):
    """Sort the links found in a text into local, cross-skill and templated ones."""
    for skill, rel in CROSS_RE.findall(text):
        cross.add(rel)
        if cross_full is not None:
            cross_full.add((skill, rel))
    for d in WILDCARD_RE.findall(text):
        wildcard_dirs.add(d.rstrip("/"))
    mentioned |= set(LINK_RE.findall(text))


def collect_pointers(text, source, pointers):
    """"File plus section" pointers: (where from, which file, which section).

    The tail after the pointer is parsed in full - that is how the form
    'sections "A" and "B"' is caught, where one line names several sections.
    """
    for target, tail in SECPTR_RE.findall(text):
        for groups in SECTION_RE.findall(tail):
            section = next((g for g in groups if g), None)
            if section:
                pointers.append((source, target, section))


def frontmatter(text):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else None


IMPORT_RE = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import|import[ \t]+([\w.,\t ]+))", re.M)


def reached_by_import(root, mentioned):
    """Modules pulled in, transitively, by the scripts the skill links.

    A tool split across files is linked by its entry point only: listing its imports in
    SKILL.md would be documentation nobody reads, and it would go stale on the first
    refactor. Without following the imports every module but the entry point reads as an
    orphan - and a warning that fires on correct code is a warning that gets ignored,
    which costs more than the orphan check is worth.
    """
    queue = [m for m in mentioned if m.endswith(".py")]
    seen, extra = set(queue), set()
    while queue:
        rel = queue.pop()
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        folder = os.path.dirname(rel)
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            continue
        for from_mod, plain in IMPORT_RE.findall(src):
            for name in ([from_mod] if from_mod else plain.split(",")):
                mod = name.strip().split(" as ")[0].split(".")[0].strip()
                if not mod:
                    continue
                base = f"{folder}/{mod}" if folder else mod
                found = []
                if os.path.isfile(os.path.join(root, base + ".py")):
                    found = [base + ".py"]
                elif os.path.isfile(os.path.join(root, base, "__init__.py")):
                    # A package is reached as a unit. Its members often have no import
                    # edge at all - a registry that discovers its plugins at runtime is
                    # the normal case - so following only static imports would report
                    # every one of them as an orphan.
                    found = sorted(
                        f"{base}/{f}" for f in os.listdir(os.path.join(root, base))
                        if f.endswith(".py"))
                for cand in found:
                    if cand not in seen:
                        seen.add(cand)
                        extra.add(cand)
                        queue.append(cand)
    return extra


# A file-scoped waiver in a file's header: `sqs-allow-file: ST011`, or `*` for all.
# The escape hatch for a file whose subject IS the thing a check hunts for - a table of
# other environments' paths, a registry of dangerous patterns.
WAIVER_RE = re.compile(r"sqs-allow-file:\s*([A-Z]{2}\d{3}(?:\s*,\s*[A-Z]{2}\d{3})*|\*)")


def waived(body, code):
    """Whether this file's first lines waive that code."""
    for line in body.split("\n", 25)[:25]:
        m = WAIVER_RE.search(line)
        if m and (m.group(1) == "*" or code in m.group(1)):
            return True
    return False


def check(skill):
    root = os.path.join(SKILLS_DIR, skill)
    md = os.path.join(root, "SKILL.md")
    errors, warnings = [], []
    name, slash_only = None, False

    if not os.path.isfile(md):
        return [F("ST015", "no SKILL.md")], [], 0, None

    with open(md, encoding="utf-8") as f:
        text = f.read()
    size = len(text.encode("utf-8"))

    # 1. frontmatter - required fields and conformance to the specification
    fm = frontmatter(text)
    if fm is None:
        errors.append(F("SP001", "no frontmatter (--- at the start of the file)"))
    else:
        for key, code in (("name:", "SP002"), ("description:", "SP003")):
            if key not in fm:
                errors.append(F(code, f"frontmatter has no `{key}`"))

        # Spec limits are warnings, not errors: Claude Code does not enforce them
        # today and the skill works. It breaks on publication and `skills-ref validate`.
        name = fm_field(fm, "name")
        if name:
            if name != skill:
                errors.append(F("SP004", 
                    f"`name: {name}` does not match the folder name `{skill}` - "
                    f"the spec requires they match; rename one of the two"))
            if len(name) > NAME_MAX:
                warnings.append(F("SP005", f"`name` is {len(name)} chars > {NAME_MAX} per the spec"))
            if not NAME_RE.match(name):
                warnings.append(F("SP006", 
                    f"`name: {name}` is off-spec: lowercase latin letters, digits and "
                    f"single hyphens only, never at the edges"))

        desc = fm_field(fm, "description")
        if desc is not None:
            if not desc:
                errors.append(F("SP007", "`description` is empty - the skill will never trigger"))
            elif len(desc) > DESC_MAX:
                warnings.append(F("SP008", 
                    f"`description` is {len(desc)} chars > {DESC_MAX} per the spec "
                    f"({len(desc) - DESC_MAX} over) - Claude Code tolerates it, "
                    f"publication and `skills-ref validate` do not"))

        compat = fm_field(fm, "compatibility")
        if compat and len(compat) > COMPAT_MAX:
            warnings.append(F("SP009", f"`compatibility` is {len(compat)} chars > {COMPAT_MAX} per the spec"))

        # A skill disabled for the model is only ever called by slash. It needs no
        # trigger words: the decision is the human's, not the description's.
        slash_only = (fm_field(fm, "disable-model-invocation") or "").lower() == "true"
        if desc and not slash_only and len(desc) < DESC_MIN:
            warnings.append(F("QL001", 
                f"`description` is {len(desc)} chars < {DESC_MIN} - it holds no trigger "
                f"conditions, and those are what the agent uses to decide whether to open it"))

        # A typo in a key does not break the YAML: the field just vanishes with its meaning.
        for key in re.findall(r"^([A-Za-z_][\w-]*):", fm, re.M):
            if key not in KNOWN_KEYS:
                warnings.append(F("SP010", 
                    f"unknown frontmatter key `{key}:` - a typo? "
                    f"the harness ignores it in silence"))

    # 2. collect every link to the skill's files - from SKILL.md and from the references
    mentioned, cross, wildcard_dirs, cross_full = set(), set(), set(), set()
    pointers = []
    sources = [("SKILL.md", text)]        # file name and body - see items 8 and 15
    collect(text, mentioned, cross, wildcard_dirs, cross_full)
    collect_pointers(text, "SKILL.md", pointers)
    for sub in SUBDIRS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for dirpath, _, files in os.walk(d):
            for fn in files:
                if fn.endswith((".md", ".txt")):
                    full = os.path.join(dirpath, fn)
                    with open(full, encoding="utf-8", errors="replace") as f:
                        body = f.read()
                    rel_here = os.path.relpath(full, root).replace("\\", "/")
                    sources.append((rel_here, body))
                    collect(body, mentioned, cross, wildcard_dirs, cross_full)
                    collect_pointers(body, rel_here, pointers)
                    # sibling markdown links resolve from the file's own folder
                    for sib in SIBLING_RE.findall(body):
                        target = os.path.join(dirpath, sib)
                        if not os.path.exists(target):
                            here = os.path.relpath(full, root).replace("\\", "/")
                            errors.append(F("ST002", f"broken sibling link: {sib} (from {here})"))
                        else:
                            mentioned.add(os.path.relpath(target, root).replace("\\", "/"))

    # 2b. a link to the skill's own file by full path (`~/.claude/skills/video/scripts/…`)
    #     is our own route, not somebody else's. Without this step a script that the
    #     skill calls the only way it can (by full path, or it would not run from an
    #     arbitrary folder) counted as an orphan - and the "orphan" class stopped
    #     meaning anything.
    mentioned |= {rel for other, rel in cross_full if other == skill}

    # 3. broken links - but only those not explained by a link into another skill
    others = {d for d in os.listdir(SKILLS_DIR)
              if os.path.isdir(os.path.join(SKILLS_DIR, d)) and d != skill}
    for rel in sorted(mentioned - cross):
        if os.path.exists(os.path.join(root, rel)):
            continue
        elsewhere = [o for o in others if os.path.exists(os.path.join(SKILLS_DIR, o, rel))]
        if elsewhere:
            warnings.append(F("ST010", 
                f"path with no skill name: {rel} - it lives in `{elsewhere[0]}`, "
                f"spell it out as `~/.claude/skills/{elsewhere[0]}/{rel}`"))
        elif not os.path.isdir(os.path.join(root, rel.split("/", 1)[0])):
            # The folder does not exist at all - this is almost always an example of a
            # path in SOMEBODY ELSE'S repository, not our own routing. Not an error:
            # otherwise the hook fails on every edit because of examples in the text.
            warnings.append(F("ST009", f"path with no such folder in the skill: {rel} - looks like an example, not a route"))
        else:
            errors.append(F("ST001", f"link to a file that does not exist: {rel}"))

    # 3b. section pointers: the file is there, the heading in it is not
    heads_cache = {}
    for source, target, section in pointers:
        full = os.path.join(root, target)
        if not os.path.isfile(full):
            continue                      # a missing file is check 3's job, no need to repeat it
        if full not in heads_cache:
            heads_cache[full] = headings(full)
        heads = heads_cache[full]
        if not heads:
            continue                      # no headings at all - nothing to compare against
        want = " ".join(section.split()).casefold()
        if not any(want == h or want in h for h in heads):
            warnings.append(F("ST008", 
                f"pointer to a section that is gone: {target} → \"{section}\" (from {source})"))

    # 4a. a module imported by a linked script is reached through it, not orphaned
    mentioned |= reached_by_import(root, mentioned)

    # 4. orphans
    on_disk = set()
    for sub in SUBDIRS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for dirpath, _, files in os.walk(d):
            for fn in files:
                if fn.startswith(".") or "__pycache__" in dirpath:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                on_disk.add(rel)
    for rel in sorted(on_disk - mentioned):
        # the folder is wired in by a template (references/types/<type>.md) - not orphans
        if any(rel.startswith(d + "/") for d in wildcard_dirs):
            continue
        warnings.append(F("ST005", f"orphan (nothing links to it): {rel}"))

    # 5. cross-skill links: does the skill exist, and the file inside it
    for other, rel in sorted(cross_full):
        if other == skill:
            # our own file named by full path: it slipped past check 3 (which subtracts
            # cross links), so its existence is verified here
            if not os.path.exists(os.path.join(root, rel)):
                errors.append(F("ST001", f"link to a file that does not exist: {rel}"))
            continue
        if not os.path.isdir(os.path.join(SKILLS_DIR, other)):
            errors.append(F("ST003", f"link to a skill that does not exist: {other} (in {rel})"))
        elif not os.path.exists(os.path.join(SKILLS_DIR, other, rel)):
            errors.append(F("ST004", f"skill {other} has no file {rel}"))

    # 6. budget - for SKILL.md and for references alike: the second stage is paid for in
    #    context too, just later. A 30 KB reference is opened whole, nobody splits it.
    if size > BUDGET:
        warnings.append(F("ST006", f"SKILL.md is {size} B > the {BUDGET} B budget - something can move into references/"))
    for rel in sorted(on_disk):
        if not rel.endswith(".md"):
            continue
        try:
            rsize = os.path.getsize(os.path.join(root, rel))
        except OSError:
            continue
        if rsize > REF_BUDGET:
            warnings.append(F("ST007", 
                f"{rel} is {rsize} B > the {REF_BUDGET} B budget - it is opened whole, split it"))

    # 7. body: frontmatter present, instructions missing - the skill activates and says nothing
    main_body = text[text.find("\n---", 3) + 4:] if fm is not None else text
    if not main_body.strip():
        errors.append(F("SP014", "no body: frontmatter is there, instructions are not"))
    elif len(main_body.strip()) < 30 and not slash_only:
        warnings.append(F("ST013", f"body is {len(main_body.strip())} chars - the skill is nearly empty"))

    # 8. outbound paths: the note was renamed and the skill still calls it by the old name
    reported = set()
    for src, body in sources:
        if waived(body, "ST011"):
            continue
        for p in sorted(vault_paths(body)):
            if p in reported or path_exists(p):
                continue
            reported.add(p)
            if environment_path(p):
                if not waived(body, "ST017"):
                    warnings.append(F("ST017", f"not on this machine: {p} (in {src}) - a tool's own "
                                               "folder; a missing install looks the same as a broken path"))
            else:
                errors.append(F("ST011", f"no such path: {p} (in {src})"))

    # 9. code as prose instead of a file. Substantive lines are counted: blank lines and
    #    comment lines do not make a program, and the threshold drifts on them.
    for src, body in sources:
        for _, lang, code in CODE_RE.findall(body):
            if lang.lower() not in CODE_LANGS or EXAMPLE_RE.search(code):
                continue
            payload = [ln for ln in code.splitlines()
                       if ln.strip() and not ln.strip().startswith("#")]
            if len(payload) > SCRIPT_LINES:
                warnings.append(F("ST012", 
                    f"code as prose: {src} - a ```{lang} block of {len(payload)} lines "
                    f"> {SCRIPT_LINES}; move it into scripts/ and leave the call and how "
                    f"to read its output in the text"))

    return errors, warnings, size, name


def skills_in(blob):
    """Skill names mentioned as paths inside a text.

    The path to the skills folder is written in several ways: `~/.claude/skills/bars`,
    `C:\\Users\\you\\.claude\\skills\\bars`, and in git-bash also
    `/c/Users/you/.claude/skills/bars`. The full path is no anchor here - we hold on
    to its two-part tail (`.claude/skills`) and take the name that follows it.
    """
    norm = blob.replace("\\", "/")
    parts = [p for p in os.path.normpath(SKILLS_DIR).replace("\\", "/").split("/") if p]
    tail = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    found, seen_root = set(), False
    for m in re.finditer(re.escape(tail) + r"(?:/([\w.-]+))?", norm, re.I):
        seen_root = True
        who = m.group(1)
        if who and not who.startswith(".") and not who.endswith(".py"):
            found.add(who)
    if seen_root and not found:
        found.add("*")                    # the folder was touched, which skill is unreadable
    return found


def touched_skills():
    """Which skills this tool call touched.

    Write/Edit put the path in `file_path`, Bash puts a whole command in `command`.
    Reading only `file_path` means not seeing edits through heredoc, sed, mv and rm,
    and skills are edited that way as often as with an editor.
    """
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return set()
    ti = payload.get("tool_input") or {}
    blob = " ".join(
        str(ti.get(k, "")) for k in ("file_path", "command", "path", "notebook_path"))
    return skills_in(blob) if blob.strip() else set()


def read_marker():
    try:
        with open(MARKER, encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()}
    except OSError:
        return set()


def write_marker(names):
    try:
        with open(MARKER, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(names)))
    except OSError:
        pass                              # the mark is a convenience, not a precondition


def clear_marker():
    try:
        os.remove(MARKER)
    except OSError:
        pass


def positional(argv):
    """Skill names from the arguments - without mistaking `--skills-dir <path>` for one."""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a == "--skills-dir":
            skip = True
        elif not a.startswith("-"):
            out.append(a)
    return out


def main():
    args = positional(sys.argv[1:])
    mark = "--mark" in sys.argv or "--hook" in sys.argv
    stop = "--stop" in sys.argv
    quiet = stop or "--quiet" in sys.argv

    if mark:
        names = touched_skills()
        if names:
            write_marker(read_marker() | names)
        return 0                          # on PostToolUse we only mark, never judge

    touched = None
    if stop:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
        if payload.get("stop_hook_active"):
            return 0                      # the stop was already blocked - do not loop
        touched = read_marker()
        if not touched:
            return 0                      # no skill was touched this turn, nothing to check
        clear_marker()

    every = sorted(
        d for d in os.listdir(SKILLS_DIR)
        if os.path.isdir(os.path.join(SKILLS_DIR, d))
        and not d.startswith(".")
        and os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md"))
    )
    # Vendored skills (installed as-is from upstream) are listed under "ignore" in
    # sqs.config.json, the list the rest of the suite already honours. Their upstream quirks
    # are not the author's to fix, and one of them failing here would block the Stop hook
    # for every skill in the tree.
    vendored = set()
    try:
        with open(os.path.join(SKILLS_DIR, "sqs.config.json"), encoding="utf-8") as fh:
            vendored = set(json.load(fh).get("ignore", []))
    except (OSError, ValueError):
        pass
    targets = args or [d for d in every if d not in vendored]

    total_err = 0
    lines = []
    by_name = {}
    # names of vendored skills still take part in the duplicate-name check: a shadowed name is a
    # real fault whoever wrote the skill
    for skill in (d for d in every if d in vendored and d not in targets):
        name = check(skill)[3]
        if name:
            by_name.setdefault(name, []).append(skill)
    for skill in targets:
        errors, warnings, size, name = check(skill)
        if name:
            by_name.setdefault(name, []).append(skill)
        total_err += len(errors)
        # Warnings: on a manual run, for every skill; in the Stop hook, only for the
        # ones edited this turn (the author has already seen the others and will not
        # sit down to fix them); on a bare --quiet, never - there only breakage matters.
        show_warn = bool(warnings) and stop and ("*" in touched or skill in touched)
        if quiet and not errors and not show_warn:
            continue
        lines.append(f"{'⛔' if errors else ('⚠️ ' if warnings else '✅')} {skill}  ({size} B)")
        lines.extend(f"     ⛔ {e.code} {e.msg}" for e in errors)
        if show_warn or not quiet:
            lines.extend(f"     ⚠️  {w.code} {w.msg}" for w in warnings)

    # A duplicate `name` across skills: the harness picks one and says nothing about the
    # other, and which one it picks is not knowable in advance. A global check, hence here.
    for name, dirs in sorted(by_name.items()):
        if len(dirs) > 1:
            total_err += 1
            lines.append(
                f"⛔ ST014 duplicate `name: {name}` - folders {', '.join(dirs)}; one shadows the other")

    if quiet:
        if lines:
            # in the hook the reader is the model, and the harness hands it stderr, not stdout
            print("The skill check found breakage that needs fixing:" if total_err
                  else "Skills were edited, the check has remarks:", file=sys.stderr)
            print("\n".join(lines), file=sys.stderr)
        if not total_err:
            return 0
        # in hook mode exit code 2 is the only one the harness passes to the model;
        # with code 1 the message would settle in a log and nobody would read it
        return 2 if stop else 1

    print("\n".join(lines))
    print()
    print(f"skills: {len(targets)} · errors: {total_err}")
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
