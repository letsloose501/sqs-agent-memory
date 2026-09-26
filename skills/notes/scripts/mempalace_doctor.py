#!/usr/bin/env python3
"""
MemPalace: diagnosis and repair.

    python mempalace_doctor.py              # diagnose
    python mempalace_doctor.py --fix        # diagnose and, if needed, repair
    python mempalace_doctor.py --archives   # which rebuild archives piled up, are they intact

WHY. `MCP error -32000: Connection closed` arrives for four different failures, fixed in
different ways. The costliest mistake is one way round: running `repair` on a healthy palace is
a long rebuild and hundreds of MB of archive for nothing. The script tells the cases apart by
numbers, not by the symptom:

  TYPE 1 "phantom nodes"   total_elements_added != id_to_label (difference > 1)
        HNSW is internally inconsistent; walking the graph segfaults.
  TYPE 2 "HNSW lags"       total == id_to_label, but clearly below the sqlite count.
        Signature in `mempalace_reconnect`: "Failed to apply logs to the hnsw segment writer".
  HEALTHY                  the numbers agree AND a live read passes.
        The stdio process itself dies. No `repair`: restart the client.
  BUSY                     live processes hold the index files.
        Stop them before any repair, or it fails on locked files.

The package's own `repair-status` cannot be trusted AS A VERDICT: it reported OK on a dead
palace with a gap of 412 ("within flush-lag tolerance"). A fixed threshold lies the other way:
chroma flushes HNSW in batches, and right after a rebuild a legal lag is up to a whole batch.
So `repair-status` may CANCEL a "type 2" verdict but may not declare "healthy": after a cancel
a live read still runs, and it is the only ground for "healthy".

Numbers alone cannot be trusted either. The compactor can get STUCK with a lag INSIDE the
threshold (sqlite 25075 vs HNSW 24923): the numbers said "no repair needed" while `search`
failed. What matters is that the lag does not shrink. So "healthy" is declared only after a
LIVE READ (probe_read, about 2 s): `status` reads sqlite only and passes on a dead palace,
`search` touches the index and fails.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

FLUSH_LAG = 200      # HNSW lagging sqlite within this is normal: flushing is not immediate
PHANTOM_LAG = 1      # total vs id_to_label off by 1 is normal; more means phantom nodes
STUCK_SIG = "hnsw segment writer"
ERROR_LINE = re.compile(r"^\s*(error|traceback|exception|\w*error:|\w*exception:)", re.I)


def mempalace_cmd() -> list[str]:
    """How to call mempalace. It is installed as a uv tool, not into the global Python, so
    `python -m mempalace` fails; the entry point lives where uv puts executables."""
    found = shutil.which("mempalace")
    if found:
        return [found]
    exe = Path.home() / ".local" / "bin" / ("mempalace.exe" if os.name == "nt" else "mempalace")
    if exe.exists():
        return [str(exe)]
    return [sys.executable, "-m", "mempalace"]


def config() -> dict:
    try:
        return json.loads((Path.home() / ".mempalace" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def default_palace() -> Path:
    raw = os.environ.get("MEMPALACE_PATH") or config().get("palace_path") or "~/.mempalace/palace"
    return Path(os.path.expanduser(raw))


def configured_model() -> str:
    """The configured embedder. Hardcoding a model breaks the palace: vectors of different
    models live in different spaces, and recording the wrong identity declares healthy a
    palace that silently lies in search."""
    return os.environ.get("MEMPALACE_EMBEDDING_MODEL") or config().get("embedding_model", "minilm")


def sqlite_counts(palace: Path) -> dict[str, dict]:
    """Per collection: rows in sqlite and the folder of its HNSW (read-only).

    The trap: `embeddings.segment_id` points at the METADATA segment (sqlite), while the index
    pickle lives in the VECTOR segment's folder. Count by the first, read the index from the
    second; mix them up and you get sqlite: 0 and a false "all fine".
    """
    db = palace / "chroma.sqlite3"
    if not db.exists():
        raise SystemExit(f"no {db}: wrong palace path")
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        out: dict[str, dict] = {}
        by_collection: dict[str, str] = {}
        for cid, name in con.execute("SELECT id, name FROM collections"):
            out[name] = {"collection": cid, "sqlite": 0, "segment": None}
            by_collection[cid] = name
        for sid, coll, scope in con.execute("SELECT id, collection, scope FROM segments"):
            name = by_collection.get(coll)
            if name is None:
                continue
            if scope == "VECTOR":
                out[name]["segment"] = sid
            elif scope == "METADATA":
                out[name]["sqlite"] = con.execute(
                    "SELECT COUNT(*) FROM embeddings WHERE segment_id = ?", (sid,)).fetchone()[0]
        return out
    finally:
        con.close()


def hnsw_counts(palace: Path, segment: str | None) -> tuple[int | None, int | None]:
    """(total_elements_added, len(id_to_label)) from the segment's index_metadata.pickle."""
    if not segment:
        return None, None
    meta = palace / segment / "index_metadata.pickle"
    if not meta.exists():
        return None, None
    with open(meta, "rb") as f:
        data = pickle.load(f)  # noqa: S301 - the palace's own local file, read-only
    return data.get("total_elements_added"), len(data.get("id_to_label") or {})


def live_processes() -> list[tuple[int, str]]:
    """Live MemPalace processes: they hold the index files and break a repair.

    Matched by the word `mempalace` in the command line, so the doctor must exclude itself:
    its own command line contains `mempalace_doctor.py`, and without the filter `--fix` kills
    its own process first.
    """
    rows: list[tuple[int, str, str]] = []
    if os.name == "nt":
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*mempalace*' } | "
              "ForEach-Object { \"$($_.ProcessId)`t$($_.Name)`t$($_.CommandLine)\" }")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        for line in (r.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].strip().isdigit():
                rows.append((int(parts[0]), parts[1].strip(), parts[2] if len(parts) > 2 else ""))
    else:
        r = subprocess.run(["ps", "-eo", "pid=,comm=,args="], capture_output=True, text=True)
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) >= 2 and parts[0].isdigit() and "mempalace" in line:
                rows.append((int(parts[0]), parts[1], parts[2] if len(parts) > 2 else ""))
    myself = Path(__file__).name.casefold()
    # The PowerShell query itself carries '*mempalace*' in its command line: not a palace process.
    return [(pid, name) for pid, name, cmd in rows
            if pid != os.getpid() and myself not in cmd.casefold() and "Get-CimInstance" not in cmd]


def stop_process(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"])
    else:
        subprocess.run(["kill", str(pid)])


def probe_read(palace: Path) -> tuple[bool, str]:
    """A live read: `search` touches HNSW and fails where the numbers still agree."""
    try:
        r = subprocess.run(mempalace_cmd() + ["--palace", palace.as_posix(), "search", "doctor live read probe"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    except subprocess.TimeoutExpired:
        return False, "search hung (>180 s)"
    out = (r.stdout or "") + (r.stderr or "")
    # Look for the signature in error lines only, never in the search results: a stored drawer
    # can quote the very error text (a journal entry about this doctor did), and a probe query
    # that happens to retrieve it would declare a healthy palace stuck.
    errors = (r.stderr or "").splitlines() + [
        ln for ln in (r.stdout or "").splitlines() if ERROR_LINE.match(ln)]
    if any(STUCK_SIG in ln for ln in errors):
        return False, "the compactor is stuck: cannot apply logs to HNSW"
    if r.returncode != 0:
        return False, f"search failed (code {r.returncode}): {' '.join(out.split())[-160:]}"
    return True, "search passed"


def package_says_ok(palace: Path) -> bool | None:
    """The package's own view of the gap: True all OK, False some DIVERGED, None unknown."""
    try:
        r = subprocess.run(mempalace_cmd() + ["--palace", palace.as_posix(), "repair-status"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    statuses = re.findall(r"status:\s+(\w+)", r.stdout or "") if r.returncode == 0 else []
    if not statuses:
        return None
    if "DIVERGED" in statuses:
        return False
    return all(s in ("OK", "UNKNOWN") for s in statuses)


def diagnose(palace: Path) -> tuple[str, list[str]]:
    """Verdict from numbers: ('healthy' | 'type1' | 'type2' | 'unknown' | 'empty', report lines)."""
    lines, verdict = [], "healthy"
    for name, rec in sorted(sqlite_counts(palace).items()):
        total, labels = hnsw_counts(palace, rec["segment"])
        n = rec["sqlite"]
        if n == 0:
            # 0 == 0 is formally "agreeing numbers" and therefore dangerous: a palace in the
            # middle of a rebuild and a wiped palace look exactly like this.
            lines.append(f"  {name:22} sqlite: {n:>6}   EMPTY: no data at all")
            lines.append("     a rebuild in progress? look at ~/.mempalace/palace.pre-rebuild-* and wait for it")
            verdict = "empty"
            continue
        if total is None:
            lines.append(f"  {name:22} sqlite: {n:>6}   HNSW: not flushed to disk yet")
            verdict = "unknown" if verdict == "healthy" else verdict
            continue
        phantom = abs((total or 0) - labels)
        lag = n - labels
        mark = "OK"
        if phantom > PHANTOM_LAG:
            mark, verdict = f"TYPE 1: {phantom} phantom nodes", "type1"
        elif lag > FLUSH_LAG:
            mark, verdict = f"TYPE 2: HNSW lags by {lag}", "type2"
        lines.append(f"  {name:22} sqlite: {n:>6}   HNSW: {labels:>6} (added {total})   lag {lag:>4}   -> {mark}")
    return verdict, lines


def archives(palace: Path) -> list[tuple[Path, float, int | None, str]]:
    out = []
    for d in sorted(palace.parent.glob(f"{palace.name}.pre-rebuild-*")):
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1024 / 1024
        docs, check = None, "-"
        db = d / "chroma.sqlite3"
        if db.exists():
            try:
                con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
                docs = con.execute("SELECT COUNT(*) FROM embedding_metadata WHERE key='chroma:document'").fetchone()[0]
                check = con.execute("PRAGMA quick_check").fetchone()[0]
                con.close()
            except sqlite3.Error as e:
                check = f"read error: {type(e).__name__}"
        out.append((d, size, docs, check))
    return out


def repair(palace: Path, procs: list[tuple[int, str]]) -> int:
    """Stop the processes, rebuild from sqlite, restore the embedder identity."""
    if procs:
        print("Stopping processes that hold the index:")
        for pid, name in procs:
            print(f"  {pid} {name}")
            stop_process(pid)
    free = shutil.disk_usage(palace).free / 1024 ** 3
    need = sum(f.stat().st_size for f in palace.rglob("*") if f.is_file()) / 1024 ** 3
    print(f"Free: {free:.1f} GB, the archive takes about {need:.1f} GB more.")
    if free < need * 2:
        print("Not enough space for the archive: clean old ones first (--archives)")
        return 1
    print("Rebuilding the index from sqlite (can take many minutes, do not interrupt)...")
    cmd = mempalace_cmd() + ["--palace", palace.as_posix(), "repair", "--mode", "from-sqlite",
                             "--archive-existing", "--yes"]
    if subprocess.run(cmd).returncode != 0:
        print("repair failed: see the output above")
        return 1
    subprocess.run(mempalace_cmd() + ["--palace", palace.as_posix(), "palace", "set-embedder",
                                      "--model", configured_model()])
    verdict, lines = diagnose(palace)
    print("\nAfter the repair:")
    print("\n".join(lines))
    ok, why = probe_read(palace)           # numbers after a repair are not trusted either
    print(f"Live read: {why}")
    print("\nWhile the repair ran the server may have come back by itself: do not write into the "
          "palace until the rebuild has finished.")
    return 0 if (verdict == "healthy" and ok) else 1


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Diagnose and repair a MemPalace palace")
    ap.add_argument("--palace", type=Path, default=default_palace(), help="palace path (default from ~/.mempalace/config.json)")
    ap.add_argument("--fix", action="store_true", help="repair if the diagnosis calls for it")
    ap.add_argument("--archives", action="store_true", help="list pre-rebuild archives")
    args = ap.parse_args()
    palace = args.palace.expanduser()

    if args.archives:
        rows = archives(palace)
        if not rows:
            print("no archives")
            return 0
        print("Archives of past repairs:\n")
        for d, size, docs, check in rows:
            print(f"  {d.name}   {size:6.1f} MB   documents: {docs}   quick_check: {check}")
        stale = rows[:-1]                   # keep the newest as a rollback point
        if stale:
            freed = sum(size for _, size, _, _ in stale)
            print(f"\nExtra archives: {len(stale)}, {freed:.0f} MB. Keep only the newest ({rows[-1][0].name}). "
                  "Deleting is the user's decision:")
            for d, _, _, _ in stale:
                print(f'  {d}')
        return 0

    procs = live_processes()
    verdict, lines = diagnose(palace)
    print(f"Palace: {palace}\n")
    print("\n".join(lines))
    print(f"\nLive MemPalace processes: {len(procs)}"
          + (f" ({', '.join(f'{p} {n}' for p, n in procs)})" if procs else ""))

    if verdict == "unknown":
        # "Not flushed to disk" is a WRITE state, not a failure: exactly how a palace looks
        # right after a successful rebuild. The numbers are blind here; ask by reading.
        print("\nThe index is not flushed yet; numbers mean nothing in this state. Live read (~2 s)...")
        ok, why = probe_read(palace)
        if ok:
            print("\nThe palace reads and searches: NO rebuild needed. The HNSW flush will happen by itself.")
            return 0
        print(f"\nThe read failed: {why}")
        verdict = "type2"

    if verdict == "type2" and package_says_ok(palace):
        print("\nThe numbers differ, but the package's `repair-status` says OK (within flush lag). "
              "No rebuild; checking with a live read.")
        verdict = "healthy"

    if verdict == "healthy":
        print("\nThe numbers agree. Live read (~2 s)...")
        ok, why = probe_read(palace)
        if ok:
            print("\nData and index are fine: NO repair needed.")
            print("If `mempalace_*` tools still fail with Connection closed, the stdio server itself")
            print("dies. Restart the client; it cannot be revived from inside the session.")
            return 0
        print(f"\nTHE NUMBERS LIE: {why}")
        print("The lag is within the threshold, but the compactor is stuck: the palace does not read.")
        verdict = "type2"

    if verdict == "empty":
        print("\nTHE PALACE IS EMPTY: not a single drawer. repair cannot help: restore from a snapshot,")
        print("or, if a rebuild is running, wait for it and run the doctor again.")
        return 1

    diag = {"type1": "TYPE 1: phantom nodes in HNSW (segfault on read)",
            "type2": "TYPE 2: HNSW lags behind sqlite"}[verdict]
    print(f"\n{diag}")
    print("   Fix: repair --mode from-sqlite --archive-existing --yes")
    if procs:
        print(f"   First stop {len(procs)} process(es), or the files stay locked.")
    if not args.fix:
        print("\n   Run with --fix to repair.")
        return 1
    return repair(palace, procs)


if __name__ == "__main__":
    sys.exit(main())
