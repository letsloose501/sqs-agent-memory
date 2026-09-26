# Install and maintenance

## Install

`browser-harness` 0.1.13 at the **reviewed commit** `afbcc38`, not the latest release, so exactly
the code that was read runs:

```bash
uv tool install --python 3.12 "git+https://github.com/browser-use/browser-harness@afbcc381b963040c19627d788e40c7e7663171ee"
```

Then switch telemetry off in its config, `~/.config/browser-harness/telemetry.json`:

```json
{ "disabled": true }
```

`bh.py` also sets `BH_TELEMETRY=0` on every call, so the config is a second lock, not the only one.
Check with `uv run --no-project scripts/bh.py --status`, which prints a `telemetry` line.

## What it uses

- The agent Chrome profile: `~/.config/browser-harness/chrome-profile`, port 9222, listening on
  `127.0.0.1` only.
- Chrome or Edge already installed on the machine.

## Why telemetry is off

It is on by default and called "anonymous", but `run.py` passes to
`telemetry.capture_cli_event` **the whole script text** (up to 20,000 chars), the output tail
(i.e. page content), every helper's arguments (typed text, URLs) and error text. The
`_safe_properties` filter that forbids `url`, `text`, `password` only runs in `capture()`, not in
`capture_cli_event`. Destination: `eu.i.posthog.com`. Verified by reading
`telemetry.py:247-296` and `run.py:250-300` at `afbcc38`.

To confirm it is off: `uv run --no-project scripts/bh.py --status` prints a `telemetry` line.

## Updating

`browser-harness --update` pulls a new version blind. Instead:

1. `git clone --depth 1 https://github.com/browser-use/browser-harness.git` into the scratchpad.
2. `git diff` against the previous commit for `telemetry.py`, `run.py`, `auth.py`: no new
   outbound sends, the off switch (`DISABLE_ENVS`) unchanged.
3. `uv tool install --python 3.12 --force <clone>`, then `bh.py --status`.
4. `uv run --no-project scripts/selftest.py`, because `agent_helpers.py` imports
   `cdp, click_at_xy, drain_events, goto_url, js, press_key` from `browser_harness.helpers`.

## Self-test

`uv run --no-project scripts/selftest.py`: 38 checks on `tests/form.html`, served by a local HTTP server
(Chrome blocks fetch from `file://`): fields, clicks, dialogs, `links()`, `find()`, the CAPTCHA
handoff (a fake widget hidden by a timer, never solved), `cards()`, `sniff`, `api_body`, `replay`, `fetch_json` and
its 404 error, `embedded_json` over `<template>`, `json_paths`. Exit 0 means all green.

That the test can go red was checked when it was written. Each of these mutations produced a FAIL
and exit 1: `force=True` by default, the dialog flag without a visibility check, embedded
search without `template`, `captcha()` always returning `[]`, `cards()` without climbing to the
card. A real bug (`act`'s `settle` parameter shadowing the `settle()` function) produced a FAIL
on link navigation with `TypeError`.

## Remove everything

```bash
uv tool uninstall browser-harness
```

The profile and config live in `~/.config/browser-harness/`; the user deletes them if they want.
