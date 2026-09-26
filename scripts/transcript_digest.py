"""Digest of the week's session transcripts for the weekly memory review.

    python transcript_digest.py                        # last 7 days, all projects, to stdout
    python transcript_digest.py --days 7 --out FILE    # also write the digest to FILE
    python transcript_digest.py --project myapp --exclude-session <id>

Why. Phase 1 of the review looks for patterns across sessions: repeated errors, the user's
corrections, tools that keep failing. Grepping the raw `.jsonl` for symptoms does not work: the
rules text (CLAUDE.md, the memory index) rides in every turn, so words like `heredoc` match every
file whether or not anything happened. In the first real run of this idea the grep gave almost
nothing but noise. Picking the week by file mtime fails too: any bulk file operation makes old
sessions look fresh.

Both steps are mechanical, so they are code; the model reads the digest and judges. Predictable
work goes to functions, reasoning to the model.

What goes in:
  * the window: a session belongs to it by the timestamp of its LAST entry, not by mtime;
  * every project under ~/.claude/projects (memory is shared across projects), except folders
    whose name contains `evals`: routing test runs write those, and their "user" turns are
    generated prompts, not the user's words;
  * the user's own messages only (origin.kind == "human"): skill bodies, task notifications and
    system reminders are dropped, pasted blocks are replaced by their size;
  * failed tool calls (tool_result is_error), grouped by a normalised signature across sessions,
    with the tool and the start of its input. The review's threshold for a repeat is two or more
    DISTINCT sessions, so the count is of sessions, not of errors;
  * tool calls the user rejected: the strongest correction signal there is.

What it cannot see: a mistake that failed no tool (a wrong answer corrected in words is only in
the user's messages, which the model reads), and subagent transcripts in subfolders. A REPEAT
group may also be one session resumed twice: identical commands in both are the tell.

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SKIP_PROJECT = re.compile(r"evals", re.I)
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
PASTED_RE = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content>", re.S)
REJECT_RE = re.compile(r"doesn't want to proceed|tool use was rejected|user rejected", re.I)
# The harness's read-before-write gate doing its job, not a pitfall. Counted, not listed.
GATE_RE = re.compile(r"File has not been read yet|File has been modified since read", re.I)


def parse_ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def signature(text: str) -> str:
    """First meaningful line with paths, numbers and quoted bits folded, so the same failure in
    two sessions gets the same key. A shell failure starts with "Exit code N" and then its output;
    that line alone would lump every failed command into one group, so the key is the exit code
    plus the last output line, where the error message usually sits."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    line = lines[0] if lines else ""
    if re.match(r"Exit code \d+$", line) and len(lines) > 1:
        line = f"{line} · {lines[-1]}"
    line = re.sub(r"<[^>]+>", "", line)
    line = re.sub(r"[A-Za-z]:[\\/][^\s'\"]*|(?:~|/)[\w.\-/]+/[\w.\-]+", "<path>", line)
    line = re.sub(r"(['\"«`]).*?\1", "<q>", line)
    line = re.sub(r"\d+", "N", line)
    return line[:110]


def clean_human(text: str, limit: int) -> str:
    text = REMINDER_RE.sub("", text)
    text = PASTED_RE.sub(lambda m: f"[pasted {len(m.group(1))} chars]", text)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…"


def tool_brief(block: dict) -> str:
    inp = block.get("input") or {}
    for key in ("command", "file_path", "url", "pattern", "skill", "query"):
        if key in inp:
            return f"{block.get('name')}: {str(inp[key])[:90]}"
    return str(block.get("name"))


def read_session(path: Path) -> dict:
    s = {"path": path, "last": None, "human": [], "errors": [], "rejects": [], "gates": 0}
    tools: dict[str, str] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            ts = parse_ts(d.get("timestamp"))
            if ts and (s["last"] is None or ts > s["last"]):
                s["last"] = ts
            if d.get("isSidechain"):
                continue
            content = (d.get("message") or {}).get("content")
            if d.get("type") == "assistant" and isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tools[b.get("id")] = tool_brief(b)
            if d.get("type") != "user":
                continue
            if (d.get("origin") or {}).get("kind") == "human" and not d.get("isMeta"):
                if isinstance(content, str):
                    text = content
                else:
                    text = " ".join(b.get("text", "") for b in content or []
                                    if isinstance(b, dict) and b.get("type") == "text")
                if text.strip():
                    s["human"].append((ts, text))
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_result" or not b.get("is_error"):
                        continue
                    body = b.get("content")
                    if isinstance(body, list):
                        body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
                    body = str(body or "")
                    call = tools.get(b.get("tool_use_id"), "?")
                    if REJECT_RE.search(body):
                        s["rejects"].append(call)
                    elif GATE_RE.search(body):
                        s["gates"] += 1
                    else:
                        s["errors"].append((signature(body), call, body.strip()[:200]))
    return s


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude" / "projects",
                    help="folder with one subfolder of .jsonl transcripts per project")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--project", help="only project folders whose name contains this")
    ap.add_argument("--exclude-session", action="append", default=[],
                    help="session id to leave out (the review's own session)")
    ap.add_argument("--max-chars", type=int, default=240, help="cut each user message to this")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    root = args.root.expanduser()
    if not root.is_dir():
        print(f"no transcripts folder: {root}", file=sys.stderr)
        return 2
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
    sessions, skipped = [], []
    for proj in sorted(p for p in root.iterdir() if p.is_dir()):
        if args.project and args.project.lower() not in proj.name.lower():
            continue
        if SKIP_PROJECT.search(proj.name):
            skipped.append(proj.name)
            continue
        for f in proj.glob("*.jsonl"):
            if f.stem in args.exclude_session:
                continue
            s = read_session(f)
            if s["last"] and s["last"] >= since:
                s["project"] = proj.name
                sessions.append(s)
    sessions.sort(key=lambda s: s["last"])

    out: list[str] = []
    w = out.append
    w(f"# Transcript digest: {len(sessions)} sessions, last {args.days} days "
      f"(by last entry inside the file)\n")
    if skipped:
        w(f"Skipped as generated: {', '.join(skipped)}\n")

    groups: dict[str, list] = defaultdict(list)
    for s in sessions:
        for sig, call, body in s["errors"]:
            groups[sig].append((s["path"].stem[:8], call, body))
    w("## Failed tool calls, grouped (sessions = distinct sessions)\n")
    ranked = sorted(groups.items(), key=lambda kv: -len({x[0] for x in kv[1]}))
    for sig, items in ranked:
        n_sess = len({x[0] for x in items})
        w(f"- {'REPEAT ' if n_sess >= 2 else ''}{n_sess} sessions, {len(items)} errors: `{sig}`")
        for sid, call, body in items[:3]:
            w(f"    - {sid} · {call} · {body[:140]!r}")
    if not groups:
        w("- none")
    gates = sum(s["gates"] for s in sessions)
    w(f"\nRead-before-write gate fired {gates} times (a working gate, not a pitfall).\n")

    w("## Tool calls the user rejected\n")
    rej = [(s["path"].stem[:8], c) for s in sessions for c in s["rejects"]]
    w("\n".join(f"- {sid} · {c}" for sid, c in rej) if rej else "- none")

    w("\n## The user's messages, per session\n")
    for s in sessions:
        if not s["human"]:
            continue
        w(f"### {s['project']} · {s['path'].stem[:8]} · last {s['last']:%Y-%m-%d %H:%M} UTC · "
          f"{len(s['errors'])} errors, {len(s['rejects'])} rejects")
        for ts, text in s["human"]:
            stamp = f"{ts:%m-%d %H:%M}" if ts else "--"
            w(f"- {stamp} {clean_human(text, args.max_chars)}")
        w("")

    report = "\n".join(out)
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
