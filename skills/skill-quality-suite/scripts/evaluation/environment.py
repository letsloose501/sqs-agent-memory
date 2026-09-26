#!/usr/bin/env python3
"""Where a skill's evaluation runs, kept apart from what it runs.

`evals/evals.json` and the trigger set say *what* to run. Until this file there was
nowhere to say *where* - which engine, which model, how many runs - so every setting
lived on the command line, and a second engine would have had no place to be declared.
That split has to exist before a second provider does, or the provider arrives with its
settings threaded through flags forever.

    evals/environment.json
    {"environments": {
        "default": {"provider": "claude", "model": "claude-sonnet-5", "runs": 3},
        "cheap":   {"provider": "claude", "model": "claude-haiku-4-5-20251001", "runs": 1}}}

`--env NAME` picks one; without it, `default` is used when the file has one. A flag given
on the command line wins over the file, and the file over the built-in defaults, so a
one-off `--runs 1` does not need an environment of its own. Every run records which
environment measured it, and comparing two runs from different environments says so -
a regression between two models is not a regression in the skill.

The file is read strictly: a key this module does not know is refused by name. A
tolerant reader would turn `"modle": "..."` into a run on the default model that looks
exactly like a run on the one intended.
"""
import json
import os

ENV_FILE = os.path.join("evals", "environment.json")
KEYS = {"provider": str, "model": str, "runs": int}
DEFAULTS = {"provider": "claude", "model": None, "runs": 3}


def load(skill_root, name=None):
    """(environment dict with "name", problem). No file and no `name` is not a problem."""
    path = os.path.join(skill_root, ENV_FILE)
    if not os.path.isfile(path):
        if name:
            return None, f"--env {name}: no {ENV_FILE} beside the skill"
        return {"name": None}, ""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"{ENV_FILE} does not parse: {e}"
    envs = data.get("environments") if isinstance(data, dict) else None
    if not isinstance(envs, dict):
        return None, f"{ENV_FILE} has no `environments` map"
    picked = name or ("default" if "default" in envs else None)
    if picked is None:
        return {"name": None}, ""
    env = envs.get(picked)
    if not isinstance(env, dict):
        known = ", ".join(sorted(envs)) or "none"
        return None, f"no environment `{picked}` in {ENV_FILE} - it has: {known}"
    for key, value in env.items():
        if key not in KEYS:
            return None, (f"{ENV_FILE}: environment `{picked}` has `{key}`, which is not "
                          f"one of {', '.join(sorted(KEYS))}")
        if not isinstance(value, KEYS[key]) or (key == "runs" and value < 1):
            return None, f"{ENV_FILE}: `{picked}.{key}` is {value!r}"
    return dict(env, name=picked), ""


def resolve(env, provider=None, model=None, runs=None):
    """The settings a run uses: the command line, then the environment, then defaults."""
    out = {"name": env.get("name")}
    for key, flag in (("provider", provider), ("model", model), ("runs", runs)):
        out[key] = flag if flag is not None else env.get(key, DEFAULTS[key])
    return out
