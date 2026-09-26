"""The vault index in MemPalace: one summary card per note.

    python vault_index.py gaps --vault <vault>                  coverage by section
    python vault_index.py gaps --vault <vault> --batch 40       the next 40 notes to card
    python vault_index.py add  --vault <vault> --from-json cards.json
    python vault_index.py add  --vault <vault> --path "Section/Note.md" --summary "..."

Why cards and not `mempalace mine`. The index is a summary, not a copy: raw note text in
the index did not change the results of a single test query (measured on a 1100-note vault:
1043 raw drawers removed, identical results before and after). A card holds the name, the
path, what the note answers, its terms and links; that is what semantic search finds.

Why a script and not the `mempalace_*` MCP tools. The MCP server starts with the app; when
it is not connected, a task that depends on it hangs. The script always works. It writes
with THE PALACE'S OWN embedder: a different model means a different vector space, and a
card embedded by the wrong model silently breaks search for the whole palace.

Runs on any Python: it re-launches itself with the Python of the `mempalace` uv tool, where
chromadb and the embedder live.

Card format (a JSON list for --from-json):
    [{"path": "Programming/Git.md",
      "summary": "what question the note answers, in the words someone would ask it",
      "terms": "commit, branch, rebase",
      "links": "[[Terminal]], [[Databases]]"}]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

WING = "vault"
COLLECTION = "mempalace_drawers"
SKIP = re.compile(r"(^|[/\\])(\.obsidian|\.trash|\.git|Excalidraw|Templates|_templates)([/\\]|$)", re.I)


def mempalace_python() -> Path | None:
    """The interpreter of the `mempalace` uv tool, found through `uv tool dir`."""
    try:
        out = subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True, timeout=30)
        base = Path(out.stdout.strip()) / "mempalace"
    except (OSError, subprocess.SubprocessError):
        return None
    for cand in (base / "Scripts" / "python.exe", base / "bin" / "python", base / "bin" / "python3"):
        if cand.is_file():
            return cand
    return None


def ensure_mempalace_env() -> None:
    try:
        import chromadb  # noqa: F401
        import mempalace  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("VAULT_INDEX_REEXEC"):
        raise SystemExit("chromadb/mempalace not importable even in the mempalace tool env. "
                         "Install MemPalace: uv tool install mempalace")
    py = mempalace_python()
    if py is None:
        raise SystemExit("MemPalace is not installed as a uv tool. Install it: uv tool install mempalace")
    env = dict(os.environ, VAULT_INDEX_REEXEC="1")
    raise SystemExit(subprocess.run([str(py), __file__, *sys.argv[1:]], env=env).returncode)


def open_collection():
    import chromadb
    from mempalace.config import MempalaceConfig
    from mempalace.embedding import get_embedding_function

    cfg = MempalaceConfig()
    palace = os.path.expanduser(cfg.palace_path)
    client = chromadb.PersistentClient(path=palace)
    try:
        return client.get_collection(COLLECTION, embedding_function=get_embedding_function())
    except Exception:  # noqa: BLE001 - a fresh palace has no collection yet
        col = client.get_or_create_collection(COLLECTION, embedding_function=get_embedding_function(),
                                              metadata={"hnsw:space": "cosine"})
        # Record which embedder built the collection, as `mempalace palace set-embedder` does;
        # without it every later open warns that the identity is unknown.
        exe = Path(sys.executable).with_name("mempalace.exe" if os.name == "nt" else "mempalace")
        cmd = [str(exe)] if exe.is_file() else [sys.executable, "-m", "mempalace"]
        subprocess.run(cmd + ["--palace", palace, "palace", "set-embedder", "--model", cfg.embedding_model],
                       capture_output=True, text=True)
        return col


def has_content(p: Path, floor: int = 200) -> bool:
    """A stub (a title and empty headings) has nothing to summarise. It is neither carded nor
    counted in coverage, or the number lies both ways."""
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    t = re.sub(r"\A---.*?---", "", t, flags=re.S)
    t = re.sub(r"^#{1,6}\s.*$", "", t, flags=re.M)
    return len(re.sub(r"\s+", "", t)) >= floor


def section_of(vault: Path, p: Path) -> str:
    rel = p.relative_to(vault)
    return rel.parts[0] if len(rel.parts) > 1 else "(root)"


def indexed(col) -> tuple[set[str], list[str]]:
    """Two independent signs a note is carded: the source_file stem, or a card that starts
    with the note's file name. Either alone misses some old cards."""
    got = col.get(where={"wing": WING}, include=["documents", "metadatas"])
    stems = {Path(str((m or {}).get("source_file") or "")).stem for m in got["metadatas"]} - {""}
    return stems, [(d or "").lstrip() for d in got["documents"]]


def cmd_gaps(vault: Path, batch: int | None, section: str | None) -> int:
    notes = [p for p in vault.rglob("*.md")
             if not SKIP.search(str(p.relative_to(vault))) and has_content(p)]
    if not notes:
        print("no notes with content in the vault yet")
        return 0
    stems, docs = indexed(open_collection())
    missing = [p for p in notes if p.stem not in stems and not any(d.startswith(p.name) for d in docs)]
    if section:
        missing = [p for p in missing if section_of(vault, p) == section]
    if batch:
        missing.sort(key=lambda p: str(p))
        print(f"# next {min(batch, len(missing))} of {len(missing)}")
        for p in missing[:batch]:
            print(p.relative_to(vault).as_posix())
        return 0
    done = len(notes) - len(missing)
    print(f"notes: {len(notes)}   carded: {done}   missing: {len(missing)}   "
          f"coverage: {done / len(notes) * 100:.0f}%")
    for sec, n in Counter(section_of(vault, p) for p in missing).most_common():
        print(f"  {n:>4}  {sec}")
    return 0


def make_card(rel: str, summary: str, terms: str, links: str) -> str:
    parts = [f"{Path(rel).name} - {summary}", f"Path: {rel}"]
    if terms:
        parts.append(f"Terms: {terms}")
    if links:
        parts.append(f"Links: {links}")
    return "\n".join(parts)


def cmd_add(vault: Path, items: list[dict], agent: str) -> int:
    col = open_collection()
    stems, docs = indexed(col)
    added = skipped = 0
    for it in items:
        rel = str(it["path"]).replace("\\", "/")
        if not (vault / rel).exists():
            print(f"  NO SUCH FILE, skipped: {rel}", file=sys.stderr)
            skipped += 1
            continue
        if Path(rel).stem in stems or any(d.startswith(Path(rel).name) for d in docs):
            print(f"  already carded, skipped: {rel}")
            skipped += 1
            continue
        room = rel.split("/")[0] if "/" in rel else "root"
        drawer_id = f"drawer_{WING}_{re.sub(r'[^A-Za-z0-9]+', '-', room)}_{uuid.uuid4().hex[:24]}"
        col.add(ids=[drawer_id],
                documents=[make_card(rel, it["summary"], it.get("terms", ""), it.get("links", ""))],
                metadatas=[{"wing": WING, "room": room, "added_by": agent, "source_file": rel,
                            "filed_at": dt.datetime.now().isoformat(), "chunk_index": 0}])
        added += 1
        print(f"  + {rel}")
    print(f"\nadded: {added}, skipped: {skipped}, drawers in palace: {col.count()}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gaps")
    g.add_argument("--vault", type=Path, required=True)
    g.add_argument("--batch", type=int)
    g.add_argument("--section")
    a = sub.add_parser("add")
    a.add_argument("--vault", type=Path, required=True)
    a.add_argument("--path")
    a.add_argument("--summary")
    a.add_argument("--terms", default="")
    a.add_argument("--links", default="")
    a.add_argument("--agent", default="notes")
    a.add_argument("--from-json", type=Path)
    args = ap.parse_args()
    vault = args.vault.expanduser()
    if not vault.is_dir():
        raise SystemExit(f"no vault at {vault}")
    ensure_mempalace_env()
    if args.cmd == "gaps":
        return cmd_gaps(vault, args.batch, args.section)
    if args.from_json:
        items = json.loads(args.from_json.read_text(encoding="utf-8"))
    elif args.path and args.summary:
        items = [{"path": args.path, "summary": args.summary, "terms": args.terms, "links": args.links}]
    else:
        ap.error("add needs --from-json, or --path with --summary")
    return cmd_add(vault, items, args.agent)


if __name__ == "__main__":
    raise SystemExit(main())
