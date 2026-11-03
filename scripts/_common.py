"""Shared helpers for the plugin's hook scripts. Standard library only.

Paths come from the plugin's user configuration. Claude Code exports every option to
hook processes as CLAUDE_PLUGIN_OPTION_<KEY>; outside a hook (tests, a manual run) the
same values can be passed through the environment by hand.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def option(key: str, default: str = "") -> str:
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{key.upper()}", default).strip()


def flag(key: str, default: bool = False) -> bool:
    raw = option(key)
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _dir(key: str) -> Path | None:
    raw = option(key)
    if not raw:
        return None
    return Path(os.path.expandvars(raw)).expanduser()


def memory_dir() -> Path | None:
    """The agent memory repository, or None when the plugin is not configured yet."""
    return _dir("memory_dir")


def vault_dir() -> Path | None:
    """The Obsidian vault, or None when the plugin is not configured yet."""
    return _dir("vault_dir")


def mempalace_config_dir() -> Path:
    """Where MemPalace keeps config.json, resolved the way MemPalace 3.10+ resolves it.

    New installs since 3.10 go to ~/.config/mempalace (or $XDG_CONFIG_HOME/mempalace); an
    existing ~/.mempalace keeps working, but only if it is a real install (a config.json,
    people_map.json or palace/chroma.sqlite3 in it), not an empty folder. Copied from
    `mempalace.config._default_config_dir` in 3.11.0; a hardcoded ~/.mempalace wrote the
    config where a fresh 3.11 never reads it.
    """
    env_dir = os.environ.get("MEMPALACE_CONFIG_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser()
    legacy = Path.home() / ".mempalace"
    if legacy.is_dir() and (any((legacy / m).is_file() for m in ("config.json", "people_map.json"))
                            or (legacy / "palace" / "chroma.sqlite3").is_file()):
        return legacy
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg and Path(xdg).expanduser().is_absolute():
        return Path(xdg).expanduser() / "mempalace"
    return Path.home() / ".config" / "mempalace"


def mempalace_palace(cfg: dict) -> Path:
    """The palace folder: the environment, then config.json, then `palace` next to the config."""
    raw = (os.environ.get("MEMPALACE_PALACE_PATH") or os.environ.get("MEMPALACE_PALACE")
           or os.environ.get("MEMPAL_PALACE_PATH") or cfg.get("palace_path"))
    return Path(os.path.expanduser(raw)) if raw else mempalace_config_dir() / "palace"


def plugin_data() -> Path:
    """Per-plugin state that survives plugin updates (markers, baselines)."""
    raw = os.environ.get("CLAUDE_PLUGIN_DATA")
    base = Path(raw) if raw else Path.home() / ".claude" / "plugins" / "data" / "agent-memory"
    base.mkdir(parents=True, exist_ok=True)
    return base


def read_payload() -> dict:
    """The hook's JSON input. An unreadable payload is an empty dict: a hook must never
    break the session because of its own input."""
    try:
        data = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def utf8_stdio() -> None:
    """Windows consoles default to a legacy code page; hook messages are UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
