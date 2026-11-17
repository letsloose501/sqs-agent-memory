"""Vault verification gate: an edit to a note is not finished until its links resolve.

Why a hook and not an instruction. A link checker that has to be remembered gets forgotten,
and a broken [[link]] in Obsidian does not fail or complain: it leads nowhere and looks
exactly like a live one until someone follows it.

Why a per-turn marker and not `git status`. A vault usually carries other uncommitted edits;
checking all of them would fail every turn on someone else's broken links.

Why a baseline and not "zero broken". An existing vault already has broken links, some in
files that get appended to every time. A "zero broken" gate would fail all such work and be
switched off within a day. So the gate catches REGRESSION: a broken link the baseline did
not know. The baseline is taken automatically the first time the gate runs.

Two ways a note gets marked. A Write/Edit names the file, and a shell command may carry the
path in its text. An edit through the shell with no path in the text (`python script.py`
writing notes, a sed on a variable, an mv by wildcard) is caught by a sweep: after every Bash
or PowerShell call the hook marks the notes modified since the previous hook call of any
tool, looking back at most SWEEP_WINDOW seconds. Without the sweep, a script that rewrote ten
notes from paths inside a .py file passed the gate unseen.

What this check physically cannot see:
  * an edit by another session or by Obsidian in the same interval: it joins this turn's check
    (the gate still blocks only on a NEW broken link, so little harm);
  * a shell edit running in the background that finishes after the next tool call;
  * an old broken link: it is in the baseline, and the gate stays quiet about it. "The gate
    passed" means "no new broken links were added", not "the file is intact".

Modes:
  --baseline  take the baseline over the whole vault (after a deliberate link cleanup).
  --mark      PostToolUse: remember the notes touched this turn. Checks nothing.
  --stop      Stop: quiet if no note was touched; otherwise runs the link checker on them
              and blocks the stop on NEW broken links. Old ones that got fixed are dropped
              from the baseline, so a later breakage of the same link is caught again.

Exit codes: 0 clean or nothing to check, 2 new broken links (in --stop mode the only code
the harness passes back to the model).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from _common import plugin_data, read_payload, utf8_stdio, vault_dir

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "skills" / "notes" / "scripts" / "check_links.py"
SKIP_PARTS = {".obsidian", ".trash", ".git", "Excalidraw"}
CMD_PATH_RE = re.compile(r"[^\s\"']+\.md")
SHELL_TOOLS = ("Bash", "PowerShell")
SWEEP_WINDOW = 600  # seconds: never look further back, or edits between turns get swept in

HINT = """The turn is not finished: the notes you touched now have broken links.

New broken links: {n}
{listing}
Touched this turn: {files}

A broken [[link]] in Obsidian does not fail or complain: it just leads nowhere. The gate
lets the vault's old broken links through; these appeared now.

Fix: check the exact spelling of the target (Glob by name; non-Latin names may be stored in
NFD), or create the target note, or drop the brackets. Then finish the turn again.
Check by hand: python "{checker}" --vault "{vault}" <file>"""


def state_files() -> tuple[Path, Path]:
    d = plugin_data()
    return d / "vault-pending.txt", d / "vault-known-broken.json"


def stamp_file() -> Path:
    return plugin_data() / "vault-last-hook.txt"  # time of the previous --mark call


def read_stamp(now: float) -> float:
    try:
        prev = float(stamp_file().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        prev = now - SWEEP_WINDOW
    return max(prev, now - SWEEP_WINDOW)


def write_stamp(now: float) -> None:
    try:
        stamp_file().write_text(f"{now:.3f}", encoding="utf-8")
    except OSError:
        pass


def swept_paths(vault: Path, since: float) -> set[str]:
    """Notes modified after `since`: a shell edit whose command text named no path."""
    found: set[str] = set()
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in SKIP_PARTS]
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            p = Path(root) / name
            try:
                if p.stat().st_mtime >= since - 1 and is_note(p, vault):
                    found.add(str(p.resolve()))
            except OSError:
                pass
    return found


def is_note(path: Path, vault: Path) -> bool:
    try:
        rel = path.resolve().relative_to(vault.resolve())
    except (OSError, ValueError):
        return False
    return path.suffix.lower() == ".md" and not (set(rel.parts) & SKIP_PARTS)


def touched_paths(payload: dict, vault: Path) -> set[str]:
    inp = payload.get("tool_input") or {}
    found: set[str] = set()
    raw = inp.get("file_path") or inp.get("notebook_path") or ""
    if raw and is_note(Path(str(raw)), vault):
        found.add(str(Path(str(raw)).resolve()))
    # An edit through the shell: no Write call, but the path is visible in the command.
    if payload.get("tool_name") in ("Bash", "PowerShell"):
        for m in CMD_PATH_RE.findall(str(inp.get("command", ""))):
            p = Path(m.strip("\"'")).expanduser()
            if p.is_absolute() and is_note(p, vault):
                found.add(str(p.resolve()))
    return found


def read_lines(p: Path) -> set[str]:
    try:
        return {ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()}
    except OSError:
        return set()


def key(entry: dict) -> str:
    """A broken link identified without its line number: lines shift on every append."""
    return "\t".join(str(entry.get(k, "")).replace("\\", "/") for k in ("file", "kind", "link"))


def run_checker(vault: Path, files: list[str]) -> tuple[list[dict], str]:
    if not CHECKER.is_file():
        return [], f"missing {CHECKER}"
    proc = subprocess.run([sys.executable, str(CHECKER), "--vault", str(vault), "--json", *files],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode not in (0, 1):
        return [], (proc.stderr or proc.stdout).strip()[:800]
    try:
        return json.loads(proc.stdout or "[]"), ""
    except ValueError as e:
        return [], f"checker output is not JSON: {e}"


def load_baseline(p: Path) -> set[str] | None:
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def save_baseline(p: Path, keys: set[str]) -> None:
    try:
        p.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError:
        pass


def rel_of(p: str, vault: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(vault.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return ""


def mode_baseline(vault: Path) -> int:
    found, err = run_checker(vault, [])
    if err:
        print(f"Baseline not taken: {err}", file=sys.stderr)
        return 1
    keys = {key(e) for e in found}
    save_baseline(state_files()[1], keys)
    print(f"Baseline taken: {len(keys)} broken links in the vault. From now on the gate "
          f"blocks only on NEW ones.")
    return 0


def mode_stop(payload: dict, vault: Path) -> int:
    if payload.get("stop_hook_active"):
        return 0  # the stop was already blocked once: do not loop
    marker, base_file = state_files()
    marked = read_lines(marker)
    try:
        marker.unlink()  # clear BEFORE checking, or a crashed run leaves the marker forever
    except OSError:
        pass
    files = [p for p in sorted(marked) if Path(p).is_file()]
    if not files:
        return 0

    found, err = run_checker(vault, files)
    if err:
        # Swallowing it would turn "checked" into "the command did not run".
        print(f"The link check did not run: {err}", file=sys.stderr)
        return 0

    touched_rel = {rel_of(p, vault) for p in files}
    baseline = load_baseline(base_file)
    if baseline is None:
        # First run: everything already broken outside this turn's files is the baseline.
        whole, err = run_checker(vault, [])
        if err:
            print(f"The link check did not run: {err}", file=sys.stderr)
            return 0
        baseline = {key(e) for e in whole if key(e).split("\t")[0] not in touched_rel}
        save_baseline(base_file, baseline)

    fresh = [e for e in found if key(e) not in baseline]
    still = {key(e) for e in found}
    shrunk = {k for k in baseline if not (k.split("\t")[0] in touched_rel and k not in still)}
    if shrunk != baseline:
        save_baseline(base_file, shrunk)
    if not fresh:
        return 0

    listing = "\n".join(f"  {e.get('file')}:{e.get('line')}  [[{e.get('link')}]]" for e in fresh[:12])
    if len(fresh) > 12:
        listing += f"\n  ... and {len(fresh) - 12} more"
    names = ", ".join(Path(f).name for f in files[:6])
    if len(files) > 6:
        names += f" and {len(files) - 6} more"
    print(HINT.format(n=len(fresh), listing=listing, files=names, checker=CHECKER, vault=vault),
          file=sys.stderr)
    return 2


def main() -> int:
    utf8_stdio()
    vault = vault_dir()
    if vault is None or not vault.is_dir():
        return 0
    if "--baseline" in sys.argv:
        return mode_baseline(vault)
    payload = read_payload()
    if "--mark" in sys.argv:
        now = time.time()
        found = touched_paths(payload, vault)
        if payload.get("tool_name") in SHELL_TOOLS:
            found |= swept_paths(vault, read_stamp(now))
        write_stamp(now)
        if found:
            marker = state_files()[0]
            try:
                marker.write_text("\n".join(sorted(read_lines(marker) | found)), encoding="utf-8")
            except OSError:
                pass
        return 0
    if "--stop" in sys.argv:
        return mode_stop(payload, vault)
    print(__doc__, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
