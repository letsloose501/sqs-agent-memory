"""PreToolUse hook: guards the agent memory repository (and, for private text, the vault) on Write/Edit.

Why. Every future session reads the memory. A conclusion one session drew from a chance
occasion and wrote into the rules steers everyone's work tomorrow, and nobody is left to
correct it, because each next session sees it as a given. A gate is cheaper than cleaning up.

Four checks, in this order:
  1. Private text: anything inside <private>...</private> never reaches memory or the vault.
     No unlock. The user marks what is for this conversation only (the idea comes from
     claude-mem's privacy tags). What the hook cannot see: the same content retold without the
     tags; that part is a rule in claude/rules.md, not a gate.
  2. Secrets anywhere in memory: blocked always, no unlock. A key that reached a git commit
     is compromised and gets revoked, not deleted.
  3. Entry format: a new root entry written whole must carry name, description, type and
     source. An entry is recalled by its description; without one it is invisible. `source`
     says where the fact came from (stated by the user / observed in work / inferred by the
     agent), after graphify's EXTRACTED vs INFERRED edge tags: an inferred entry is a
     hypothesis and must read as one.
  4. Protected scopes: the constitution (README.md, SCOPES.md in the memory root) and any
     entry with `protected: true` in its frontmatter. Unlock for one run with
     AGENT_MEMORY_UNLOCK=1, which is never set automatically.

Input: the harness JSON on stdin. Output: 0 lets it through, 2 blocks (stderr explains).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from _common import memory_dir, read_payload, utf8_stdio, vault_dir

CONSTITUTION = {"readme.md", "scopes.md"}
PROTECTED_RE = re.compile(r"^\s*protected:\s*true\s*$", re.M | re.I)
PRIVATE_RE = re.compile(r"<\s*/?\s*private\s*>", re.I)
SOURCE_RE = re.compile(r"^\s*source:\s*(stated|observed|inferred)\s*$", re.M | re.I)

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

PRIVATE_HINT = """Blocked: <private> text on its way into {where}.

  file: {name}

The user marked this part as private: it is for this conversation only and is never stored in
memory or the vault, not even paraphrased. Remove it (and anything retelling it), then write
the rest."""

FORMAT_HINT = """Blocked: a memory entry without its required fields.

  file: {name}
  missing: {missing}

An entry is recalled by its `description`; without it the entry is invisible. `source` says
where the fact came from, so the next session knows how far to trust it.

Entry header:

  ---
  name: <short-slug, the file name without .md>
  description: <one line: the entry is recalled by it>
  metadata:
    type: user | feedback | project | reference
    source: stated | observed | inferred
  ---

  stated   = the user said it (quote them when it matters)
  observed = seen in the work: a command output, a file, a measurement
  inferred = the agent's conclusion; a hypothesis until confirmed

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


def inside(path: Path, root: Path | None) -> bool:
    if root is None:
        return False
    try:
        return path.is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def main() -> int:
    utf8_stdio()
    mem, vault = memory_dir(), vault_dir()
    payload = read_payload()
    if payload.get("tool_name") not in ("Write", "Edit", "NotebookEdit"):
        return 0
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not raw:
        return 0
    try:
        path = Path(raw).resolve()
    except OSError:
        return 0
    in_mem, in_vault = inside(path, mem), inside(path, vault)
    if not (in_mem or in_vault):
        return 0
    text = " ".join(str(tool_input.get(k, "")) for k in ("content", "new_string", "new_source"))

    if PRIVATE_RE.search(text):
        print(PRIVATE_HINT.format(where="memory" if in_mem else "the vault", name=path.name), file=sys.stderr)
        return 2
    if not in_mem:
        return 0
    root = mem.resolve()

    m = SECRET_RE.search(text)
    if m:
        print(SECRET_HINT.format(name=path.name, kind=m.group(0)[:12] + "..."), file=sys.stderr)
        return 2

    # Format: judged only on a whole-file Write; an Edit sends a fragment, not a document.
    if payload.get("tool_name") == "Write":
        special = path.name.casefold() in CONSTITUTION | {"memory.md"}
        if path.parent == root and not special and path.suffix.lower() == ".md":
            body = str(tool_input.get("content", ""))[:800]
            missing = [f.rstrip(":") for f in ("name:", "description:", "type:") if f not in body]
            if not SOURCE_RE.search(body):
                missing.append("source (stated | observed | inferred)")
            if missing:
                print(FORMAT_HINT.format(name=path.name, missing=", ".join(missing)), file=sys.stderr)
                return 2

    # The human's unlock opens a scope, never private text, a secret or a format error.
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
