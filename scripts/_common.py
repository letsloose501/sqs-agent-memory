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
