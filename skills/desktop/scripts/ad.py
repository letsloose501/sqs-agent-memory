"""Thin wrapper over the agent-desktop CLI: a short table instead of the JSON tree, bare refs,
a change report after every action, and a guard before overwriting text.

    python ad.py windows                        every window: app name, id, title, focused
    python ad.py snap --app CalculatorApp.exe   interactive tree as `eN role 'name' =value [states]`
    python ad.py snap --app X --root e3 --all   drill into one region, static text included
    python ad.py act click e12                  act, re-read the same scope, print what changed
    python ad.py act set-value e1 "text"        refused if e1 already holds text; --overwrite to allow
    python ad.py raw get e6 --property value    any other command, bare refs expanded

Bare refs (`e12`) expand to the last snapshot (`@<id>:e12`), so PowerShell never sees an `@`
it would read as splatting. Extra flags after the arguments go to agent-desktop unchanged.
Exit 0: done. 1: agent-desktop returned an error (code, disposition and suggestion printed).
2: refused by the wrapper or bad usage.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

WRITE_ACTIONS = {"set-value", "clear", "type"}
GONE = {"APP_NOT_FOUND", "WINDOW_NOT_FOUND"}  # re-read after an action: the window closed
REF = re.compile(r"^e\d+$")
SHOW = 20  # lines of each kind in a change report


def state_file() -> Path:
    session = os.environ.get("AGENT_DESKTOP_SESSION", "global")
    return Path(tempfile.gettempdir()) / f"agent-desktop-ad-{re.sub(r'[^A-Za-z0-9_-]', '_', session)}.json"


def load_state() -> dict:
    try:
        return json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    state_file().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def call(args: list[str]) -> dict:
    exe = shutil.which("agent-desktop")
    if not exe:
        sys.exit("desktop: agent-desktop is not on PATH (npm install -g agent-desktop, see references/setup.md)")
    p = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"ok": False, "error": {"code": "NO_JSON", "message": (p.stderr or p.stdout).strip()[:500]}}


def expand(args: list[str], snapshot_id: str | None) -> list[str]:
    out = []
    for a in args:
        if REF.match(a):
            if not snapshot_id:
                sys.exit("desktop: bare ref without a snapshot; run `snap` first")
            a = f"@{snapshot_id}:{a}"
        out.append(a)
    return out


def rows(node: dict, out: list[dict] | None = None) -> list[dict]:
    """Flatten the tree to the nodes that carry a ref, in reading order."""
    out = [] if out is None else out
    if node.get("ref_id"):
        out.append({"ref": node["ref_id"].rsplit(":", 1)[-1], "role": node.get("role", ""),
                    "name": node.get("name", ""), "value": node.get("value", ""),
                    "states": node.get("states", [])})
    for child in node.get("children", []):
        rows(child, out)
    return out


def line(r: dict, with_ref: bool = True) -> str:
    s = f"{r['role']}  {r['name']!r}"
    if r["value"]:
        s += f" ={r['value'][:120]!r}"
    if r["states"]:
        s += f" [{','.join(r['states'])}]"
    return f"{r['ref']:5} {s}" if with_ref else s


def diff(before: list[dict], after: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rows that appeared and rows that went away, compared without refs (refs change per snapshot)."""
    b = Counter(line(r, False) for r in before)
    a = Counter(line(r, False) for r in after)
    gone, new = b - a, a - b
    added, removed = [], []
    for r in after:
        k = line(r, False)
        if new[k] > 0:
            added.append(r)
            new[k] -= 1
    for r in before:
        k = line(r, False)
        if gone[k] > 0:
            removed.append(r)
            gone[k] -= 1
    return added, removed


def fail(env: dict) -> int:
    e = env.get("error", {})
    d = e.get("disposition", {})
    print(f"ERROR {e.get('code')}: {e.get('message')}")
    if d:
        print(f"  delivery={d.get('delivery')} retry={d.get('retry')}"
              + ("  (may have landed: read the state before repeating)" if d.get("retry") != "safe" else ""))
    if e.get("suggestion"):
        print(f"  suggestion: {e['suggestion']}")
    return 1


def snapshot(snap_args: list[str], state: dict, after_action: bool = False) -> tuple[dict, list[dict]] | str | None:
    env = call(["snapshot", *snap_args])
    if not env.get("ok"):
        code = env.get("error", {}).get("code")
        if after_action and code in GONE:
            return code
        fail(env)
        return None
    d = env["data"]
    table = rows(d["tree"])
    state.update(snapshot_id=d["snapshot_id"], snap_args=snap_args, rows=table)
    save_state(state)
    return d, table


def cmd_snap(argv: list[str]) -> int:
    state = load_state()
    full = "--all" in argv
    argv = [a for a in argv if a != "--all"]
    snap_args = expand(argv, state.get("snapshot_id"))
    snap_args += [f for f in (["--compact"] + ([] if full else ["-i"])) if f not in snap_args]
    got = snapshot(snap_args, state)
    if not got:
        return 1
    d, table = got
    print(f"snapshot {d['snapshot_id']}  {d.get('app', '')}  refs={d['ref_count']}"
          + ("" if d.get("complete", True) else "  INCOMPLETE: retake with a larger --timeout-ms"))
    for r in table:
        print(line(r))
    return 0


def cmd_windows(_: list[str]) -> int:
    env = call(["list-windows"])
    if not env.get("ok"):
        return fail(env)
    for w in env["data"]:
        flags = [f for f, on in (("focused", w.get("is_focused")), ("minimized", w.get("minimized"))) if on]
        print(f"{w['app_name']:24} {w['id']:12} {w.get('title', '')!r}" + (f" [{','.join(flags)}]" if flags else ""))
    return 0


def cmd_act(argv: list[str]) -> int:
    overwrite = "--overwrite" in argv
    argv = [a for a in argv if a != "--overwrite"]
    if len(argv) < 2:
        sys.exit("usage: ad.py act <action> eN [args...]")
    action, target = argv[0], argv[1]
    state = load_state()
    before = state.get("rows", [])
    if action in WRITE_ACTIONS and not overwrite:
        held = next((r for r in before if r["ref"] == target), None)
        if held and held["value"]:
            print(f"REFUSED: {target} ({held['role']} {held['name']!r}) already holds text: {held['value'][:80]!r}.\n"
                  "An app can restore the user's own document into a new window (Notepad reopens every tab).\n"
                  "Write here only if the user named this field or document; then repeat with --overwrite.")
            return 2
    env = call([action, *expand(argv[1:], state.get("snapshot_id"))])
    if not env.get("ok"):
        return fail(env)
    d = env.get("data", {})
    disp = d.get("disposition", {})
    print(f"{action} {target}: delivery={disp.get('delivery')}")
    for s in d.get("surfaces", []) or []:
        print(f"  opened surface: {json.dumps(s, ensure_ascii=False)[:200]}")
    if not state.get("snap_args"):
        return 0
    time.sleep(float(os.environ.get("AD_SETTLE_S", "0.3")))
    got = snapshot(state["snap_args"], state, after_action=True)
    if isinstance(got, str):
        print(f"  the window is gone ({got}): closed by this action or by the app")
        return 0
    if not got:
        print("  could not re-read the window: check the state yourself before going on")
        return 1
    after_d, after = got
    added, removed = diff(before, after)
    if not added and not removed:
        print("  nothing changed in the snapshot scope")
    for r in removed[:SHOW]:
        print(f"  - {line(r, False)}")
    for r in added[:SHOW]:
        print(f"  + {line(r)}")
    hidden = max(0, len(added) - SHOW) + max(0, len(removed) - SHOW)
    if hidden:
        print(f"  ... {hidden} more lines")
    print(f"  refs now from snapshot {after_d['snapshot_id']}")
    return 0


def cmd_raw(argv: list[str]) -> int:
    env = call(expand(argv, load_state().get("snapshot_id")))
    print(json.dumps(env.get("data") if env.get("ok") else env.get("error"), ensure_ascii=False, indent=1)[:4000])
    return 0 if env.get("ok") else 1


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    commands = {"snap": cmd_snap, "windows": cmd_windows, "act": cmd_act, "raw": cmd_raw}
    if not argv or argv[0] not in commands:
        print(__doc__)
        return 2
    return commands[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
