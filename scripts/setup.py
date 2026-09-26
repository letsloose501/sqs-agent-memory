"""Deterministic steps of /agent-memory:setup. Standard library only.

    python setup.py check                                   what is installed, what is missing
    python setup.py memory   --memory DIR                   create the memory repo from the template
    python setup.py vault    --vault DIR                    create the starter vault layout
    python setup.py settings --memory DIR                   set autoMemoryDirectory in ~/.claude/settings.json
    python setup.py mempalace [--model M] [--langs en,ru]   write MemPalace config for the index-only role

Every step is idempotent: it creates what is missing and never overwrites an existing file.
Every step prints what it did and what it left alone. Exit 0 ok, 1 something failed, 2 usage.
The skill decides WHEN to run each step and asks the user first; this script only does it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def say(tag: str, msg: str) -> None:
    print(f"  {tag:8} {msg}")


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def version(cmd: list[str]) -> str | None:
    try:
        r = run(cmd)
    except OSError:
        return None
    out = (r.stdout or r.stderr).strip().splitlines()
    return out[0] if r.returncode == 0 and out else None


def copy_tree_missing(src: Path, dst: Path) -> tuple[list[str], list[str]]:
    """Copy files from src into dst, skipping files that already exist."""
    made, kept = [], []
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        target = dst / rel
        if f.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            kept.append(str(rel))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        made.append(str(rel))
    return made, kept


def cmd_check(_: argparse.Namespace) -> int:
    print("Tools:")
    rows = [
        ("git", ["git", "--version"], "required: memory lives in a git repository"),
        ("uv", ["uv", "--version"], "required: runs every hook and script"),
        ("gh", ["gh", "--version"], "optional: creates the private GitHub repo for memory"),
        ("mempalace", ["mempalace", "--version"], "required: the vault index (uv tool install mempalace)"),
        ("mempalace-mcp", ["mempalace-mcp", "--help"], "required on PATH for the MCP server (uv tool update-shell)"),
        ("ffmpeg", ["ffmpeg", "-version"], "optional: video tier 3 and frames (video skill)"),
        ("browser-harness", ["browser-harness", "--help"], "optional: the browser skill"),
    ]
    missing_required = False
    for name, cmd, why in rows:
        v = version(cmd)
        if v:
            say("ok", f"{name}: {v[:60]}")
        else:
            say("MISSING", f"{name}: {why}")
            missing_required |= why.startswith("required")
    print("\nGitHub login:")
    if shutil.which("gh"):
        r = run(["gh", "auth", "status"])
        say("ok" if r.returncode == 0 else "no", "gh is logged in" if r.returncode == 0 else "gh is not logged in (gh auth login)")
    print("\nGit identity (commits in the memory repo need it):")
    for key in ("user.name", "user.email"):
        r = run(["git", "config", "--global", key])
        say("ok" if r.stdout.strip() else "MISSING", f"{key} = {r.stdout.strip() or '(not set)'}")
    print("\nSettings:")
    settings = Path.home() / ".claude" / "settings.json"
    try:
        amd = json.loads(settings.read_text(encoding="utf-8")).get("autoMemoryDirectory")
    except (OSError, ValueError):
        amd = None
    say("ok" if amd else "no", f"autoMemoryDirectory = {amd or '(not set)'}")
    cfg = Path.home() / ".mempalace" / "config.json"
    try:
        mp = json.loads(cfg.read_text(encoding="utf-8"))
        say("ok", f"MemPalace config: embedding_model={mp.get('embedding_model', 'minilm (default)')}, "
                  f"auto_save={mp.get('hooks', {}).get('auto_save', 'true (default)')}")
    except (OSError, ValueError):
        say("no", "MemPalace config: none yet (setup.py mempalace)")
    return 1 if missing_required else 0


def cmd_memory(a: argparse.Namespace) -> int:
    mem = Path(a.memory).expanduser()
    mem.mkdir(parents=True, exist_ok=True)
    made, kept = copy_tree_missing(TEMPLATES / "memory", mem)
    for m in made:
        say("created", m)
    for k in kept:
        say("kept", f"{k} (already there, not touched)")
    if not (mem / ".git").is_dir():
        r = run(["git", "init", "-b", "main"], cwd=mem)
        if r.returncode != 0:
            say("FAILED", "git init: " + r.stderr.strip()[:200])
            return 1
        say("created", "git repository")
    if run(["git", "status", "--porcelain"], cwd=mem).stdout.strip():
        run(["git", "add", "-A"], cwd=mem)
        r = run(["git", "commit", "-m", "memory: initial layout from agent-memory"], cwd=mem)
        if r.returncode != 0:
            say("FAILED", "first commit: " + (r.stderr or r.stdout).strip()[:300])
            say("", "usually git user.name / user.email are not set: see `setup.py check`")
            return 1
        say("created", "first commit")
    return 0


def cmd_vault(a: argparse.Namespace) -> int:
    vault = Path(a.vault).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    made, kept = copy_tree_missing(TEMPLATES / "vault", vault)
    for m in made:
        say("created", m)
    for k in kept:
        say("kept", f"{k} (already there, not touched)")
    if not made:
        say("", "nothing to create: the vault already has the starter files")
    return 0


def cmd_settings(a: argparse.Namespace) -> int:
    mem = Path(a.memory).expanduser()
    home = Path.home()
    try:
        value = "~/" + mem.resolve().relative_to(home.resolve()).as_posix()
    except ValueError:
        value = mem.resolve().as_posix()
    path = home / ".claude" / "settings.json"
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            say("FAILED", f"{path} is not valid JSON ({e}); fix it first, nothing written")
            return 1
    if data.get("autoMemoryDirectory") == value:
        say("kept", f"autoMemoryDirectory already {value}")
        return 0
    if data.get("autoMemoryDirectory"):
        say("changed", f"autoMemoryDirectory {data['autoMemoryDirectory']} -> {value}")
    else:
        say("set", f"autoMemoryDirectory = {value}")
    data["autoMemoryDirectory"] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(".json.bak-agent-memory")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
        say("backup", str(backup))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def cmd_mempalace(a: argparse.Namespace) -> int:
    cfg_path = Path.home() / ".mempalace" / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError as e:
            say("FAILED", f"{cfg_path} is not valid JSON ({e}); nothing written")
            return 1
    before = json.dumps(cfg, sort_keys=True)
    hooks = cfg.setdefault("hooks", {})
    if hooks.get("auto_save") is not False:
        hooks["auto_save"] = False
        say("set", "hooks.auto_save = false (the palace is the vault index, not a transcript dump)")
    if a.model and cfg.get("embedding_model") != a.model:
        if cfg.get("embedding_model") and (Path(cfg.get("palace_path", "~/.mempalace/palace")).expanduser() / "chroma.sqlite3").exists():
            say("WARNING", f"changing the embedder of an existing palace ({cfg['embedding_model']} -> {a.model}) "
                           "needs `mempalace repair rebuild-index`")
        cfg["embedding_model"] = a.model
        say("set", f"embedding_model = {a.model}")
    if a.langs:
        langs = [x.strip() for x in a.langs.split(",") if x.strip()]
        if cfg.get("entity_languages") != langs:
            cfg["entity_languages"] = langs
            say("set", f"entity_languages = {langs}")
    if json.dumps(cfg, sort_keys=True) == before:
        say("kept", "MemPalace config already as needed")
        return 0
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    say("wrote", str(cfg_path))
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Deterministic steps of /agent-memory:setup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("memory")
    p.add_argument("--memory", required=True)
    p = sub.add_parser("vault")
    p.add_argument("--vault", required=True)
    p = sub.add_parser("settings")
    p.add_argument("--memory", required=True)
    p = sub.add_parser("mempalace")
    p.add_argument("--model", choices=["minilm", "embeddinggemma", "openai-compat"])
    p.add_argument("--langs", help="entity languages, comma-separated: en,ru")
    a = ap.parse_args()
    return {"check": cmd_check, "memory": cmd_memory, "vault": cmd_vault,
            "settings": cmd_settings, "mempalace": cmd_mempalace}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
