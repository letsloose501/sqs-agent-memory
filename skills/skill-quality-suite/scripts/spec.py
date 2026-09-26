#!/usr/bin/env python3
"""Spec conformance the structure engine does not cover.

check_skills.py already validates the frontmatter fields themselves (SP001-SP010,
SP014). What is left is the packaging: the layout the Agent Skills specification
names, the file shapes a strict loader rejects, and the weight the skill carries.

Every finding here is one a skill survives locally and fails on publication, which is
why they exist as a separate pass: the author never sees them until it is too late.
"""
import os
import re

from core import Finding

# `evals/` is named by the official skill-creation guidance, which puts eval files
# inside the skill directory. It was reported as a non-standard directory until
# that page was read - a rule wrong about the thing it checks.
ALLOWED_DIRS = {"references", "assets", "scripts", "evals"}
# The Agent Skills validation rules, from the authoring guide: neither field may carry
# an XML tag, and the name may not carry a vendor word. Both refusals arrive at upload,
# after the skill is finished, so they are worth catching at home.
XML_TAG = re.compile(r"<[A-Za-z/][^>\n]{0,60}>")
RESERVED_IN_NAME = ("anthropic", "claude")
# Files that are repository furniture rather than skill payload. `sqs.py publish`
# wants README.md to exist; the spec pass only notes that it ships inside the folder.
EXTRANEOUS = {"readme.md", "changelog.md", "license", "license.md", "license.txt",
              "makefile", "package.json", "pyproject.toml", ".gitignore"}
BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".zip", ".pdf",
              ".woff", ".woff2", ".ttf", ".ico", ".mov")
ASSET_BUDGET = 1_000_000        # one megabyte per file: it travels with every install
MAX_DEPTH = 2                   # references/<file>.md - one hop is the whole idea


def unclosed_fence(text):
    """Line number of a fence nothing closes, or None.

    Counted per marker length, because a ```` ```` ```` block legitimately contains a
    ``` block, and a naive count reads the inner one as the outer one's close.
    """
    stack = []
    for i, line in enumerate(text.split("\n"), 1):
        s = line.lstrip()
        if not (s.startswith("```") or s.startswith("~~~")):
            continue
        ch = s[0]
        marker = s[:len(s) - len(s.lstrip(ch))]
        if stack and stack[-1][0] == marker and not s[len(marker):].strip():
            stack.pop()
        elif not stack or len(marker) > len(stack[-1][0]):
            stack.append((marker, i))
    return stack[0][1] if stack else None


def check(skill, cfg=None):
    cfg = cfg or {}
    allowed = ALLOWED_DIRS | set(cfg.get("allow_dirs", []))
    out = []

    if not skill.ok:
        return out

    # SP011 - an unclosed fence turns every instruction after it into code
    for rel, text in skill.texts():
        line = unclosed_fence(text)
        if line:
            out.append(Finding("SP011", f"unclosed code fence opened at line {line}",
                               where=rel, line=line))

    # SP015 - a block scalar parses everywhere and is rejected by strict loaders
    if skill.fm_style.get("description") == "block":
        out.append(Finding("SP015", "`description` is a block scalar (`>-` / `|`) - valid YAML, "
                                    "flagged non-portable by the vendor-neutral validators",
                           where="SKILL.md"))

    # SP018 / SP019 - the two validation rules that only bite on upload
    for field in ("name", "description"):
        value = skill.fm.get(field) or ""
        m = XML_TAG.search(value)
        if m:
            out.append(Finding("SP018", f"`{field}` contains `{m.group(0)}`",
                               where="SKILL.md"))
    # SP020 - the looser half SP018 does not cover. The validator the reference
    # skill-creation tooling ships refuses ANY angle bracket in a description, and its
    # packager runs that validator first - so `a -> b` or `files <10MB` is a skill that
    # loads locally and cannot be packaged. Reported only when SP018 did not already
    # name a tag, so one bracket is one finding.
    desc = skill.fm.get("description") or ""
    if ("<" in desc or ">" in desc) and not XML_TAG.search(desc):
        i = min(p for p in (desc.find("<"), desc.find(">")) if p >= 0)
        out.append(Finding("SP020", f"`description` contains a bare angle bracket: "
                                    f"\"{desc[max(0, i - 20):i + 20].strip()}\"",
                           where="SKILL.md"))
    low = (skill.name or "").lower()
    reserved = [w for w in RESERVED_IN_NAME if w in low]
    if reserved:
        out.append(Finding("SP019", f"`name: {skill.name}` contains "
                                    f"{', '.join(reserved)}", where="SKILL.md"))

    # SP012 / SP013 - what sits at the skill root
    try:
        entries = sorted(os.listdir(skill.root))
    except OSError:
        return out
    for e in entries:
        full = os.path.join(skill.root, e)
        if e.startswith(".") or e == "__pycache__" or skill.ignored(e):
            continue
        if os.path.isdir(full):
            if e not in allowed:
                out.append(Finding("SP012", f"`{e}/` is not one of "
                                            f"{', '.join(sorted(allowed))}", where=e))
        elif e != "SKILL.md" and e.lower() in EXTRANEOUS:
            out.append(Finding("SP013", f"`{e}` ships inside the skill folder", where=e))

    # SP016 / SP017 - weight and depth
    for rel, size, _ in skill.walk():
        if size > ASSET_BUDGET:
            out.append(Finding("SP016", f"{size // 1000} KB - every install carries it",
                               where=rel))
        elif rel.lower().endswith(BINARY_EXT) and size > 200_000:
            out.append(Finding("SP016", f"binary asset, {size // 1000} KB", where=rel))
        depth = rel.count("/")
        if depth > MAX_DEPTH and rel.endswith(".md"):
            out.append(Finding("SP017", f"{depth} levels down - a reference is reached "
                                        f"in one hop or not at all", where=rel))
    return out
