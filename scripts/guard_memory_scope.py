"""PreToolUse hook: guards the agent memory repository on every Write/Edit.

Why. Every future session reads the memory. A conclusion one session drew from a chance
occasion and wrote into the rules steers everyone's work tomorrow, and nobody is left to
correct it, because each next session sees it as a given. A gate is cheaper than cleaning up.

Three checks, in this order:
  1. Secrets anywhere in memory: blocked always, no unlock. A key that reached a git commit
     is compromised and gets revoked, not deleted.
  2. Entry format: a new root entry written whole must carry name, description and type.
     An entry is recalled by its description; without one it is invisible.
  3. Protected scopes: the constitution (README.md, SCOPES.md in the memory root) and any
     entry with `protected: true` in its frontmatter. Unlock for one run with
     AGENT_MEMORY_UNLOCK=1, which is never set automatically.

Input: the harness JSON on stdin. Output: 0 lets it through, 2 blocks (stderr explains).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from _common import memory_dir, read_payload, utf8_stdio

CONSTITUTION = {"readme.md", "scopes.md"}
PROTECTED_RE = re.compile(r"^\s*protected:\s*true\s*$", re.M | re.I)

# Only formats with a recognisable prefix: guessing by entropy fires on hashes and paths.
SECRET_RE = re.compile(
    r"(gsk_[A-Za-z0-9]{20,}"           # Groq
    r"|sk-[A-Za-z0-9]{20,}"            # OpenAI-compatible
    r"|sk-ant-[A-Za-z0-9_-]{20,}"      # Anthropic
    r"|ghp_[A-Za-z0-9]{20,}"           # GitHub personal
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"   # Slack
    r"|AKIA[0-9A-Z]{16}"               # AWS
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b)"  # card number
)

FORMAT_HINT = """Blocked: a memory entry without its required fields.

  file: {name}
  missing: {missing}

An entry is recalled by its `description`; without it the entry is invisible: the next
session will not find it, however valuable the body is. So the format is a gate, not a hope.

Entry header:

  ---
  name: <short-slug, the file name without .md>
  description: <one line: the entry is recalled by it>
  metadata:
    type: user | feedback | project | reference
  ---

The mistakes/ draft, the MEMORY.md index and the constitution are exempt."""

SECRET_HINT = """Blocked: this looks like a secret in memory text.

  file: {name}
  matched: {kind}

Secrets do not belong in memory, not even for a moment. Git history is irreversible: a key
that reached a commit is compromised and gets REVOKED, not deleted.

Remove the value. If you need to remember that the key exists, write WHERE it lives (an
environment variable, a password manager), never the value."""

HINT = """Blocked: a write into a protected area of memory.

  file: {name}
  reason: {why}

This area is edited only at the user's direct request (see SCOPES.md in the memory root).
Show the proposed edit in chat and ask. If they agree, rerun with AGENT_MEMORY_UNLOCK=1 in
the environment.

Free to write: ordinary entries in the memory root and the mistakes/ draft."""


def main() -> int:
    utf8_stdio()
    mem = memory_dir()
    if mem is None:
        return 0
    payload = read_payload()
    if payload.get("tool_name") not in ("Write", "Edit", "NotebookEdit"):
        return 0
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path", "")
    if not raw:
        return 0
    try:
        path = Path(raw).resolve()
        root = mem.resolve()
        inside = path.is_relative_to(root)
    except (OSError, ValueError):
        return 0
    if not inside:
        return 0

    text = " ".join(str(tool_input.get(k, "")) for k in ("content", "new_string"))
    m = SECRET_RE.search(text)
    if m:
        print(SECRET_HINT.format(name=path.name, kind=m.group(0)[:12] + "..."), file=sys.stderr)
        return 2

    # Format: judged only on a whole-file Write; an Edit sends a fragment, not a document.
    if payload.get("tool_name") == "Write":
        special = path.name.casefold() in CONSTITUTION | {"memory.md"}
        if path.parent == root and not special and path.suffix.lower() == ".md":
            body = str(tool_input.get("content", ""))[:600]
            missing = [f.rstrip(":") for f in ("name:", "description:", "type:") if f not in body]
            if missing:
                print(FORMAT_HINT.format(name=path.name, missing=", ".join(missing)), file=sys.stderr)
                return 2

    # The human's unlock opens a scope, never a secret or a format error (both checked above).
    if os.environ.get("AGENT_MEMORY_UNLOCK") == "1":
        return 0

    why = None
    if path.name.casefold() in CONSTITUTION and path.parent == root:
        why = "the memory constitution: rules about the rules"
    elif path.exists():
        try:
            if PROTECTED_RE.search(path.read_text(encoding="utf-8", errors="replace")[:800]):
                why = "the entry is marked protected: true"
        except OSError:
            pass
    if not why:
        return 0
    print(HINT.format(name=path.name, why=why), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
