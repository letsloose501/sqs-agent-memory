---
name: desktop
compatibility: Needs the agent-desktop CLI (npm package agent-desktop, Node 18+) on PATH; references/setup.md. Windows, macOS, Linux.
description: >-
  Operate desktop apps through the OS accessibility tree with agent-desktop: read a window as a
  short table of controls, click, fill, toggle, pick menu items, read values, manage windows,
  without taking the mouse or the foreground. Use when a task needs a native app's GUI: "click
  in the app", "fill the dialog", "what does the window show", "press the button in X",
  "automate this program", "check the setting in the app", "close the popup"; and when an app has
  no command line or API for what is needed. Websites are `browser`. An app with its own MCP
  server or scripting API (an editor, a 3D tool) goes through that first. Pixel-only surfaces
  (games, canvases, remote screens) are the harness's screenshot computer use.
---

# desktop

Engine: [agent-desktop](https://github.com/vercel-labs/agent-desktop) (Apache-2.0, Vercel Labs), a
native CLI that reads UI Automation on Windows, AX on macOS and AT-SPI on Linux and prints one JSON
envelope per command. This skill adds `scripts/ad.py`, a stdlib wrapper: the tree as one line per
control, bare refs, a change report after every action, and a guard before overwriting text. No
agent-desktop code is copied. Install and what was checked: [references/setup.md](references/setup.md).

## Script first, the GUI is reconnaissance

A GUI run is the slow, fragile way. Before opening a window, look for the app's own route: a CLI
flag, a config file, a scripting API, an MCP server. Use the GUI for what has no other way, or to
find out how the app does something so a script can do it next time.

| Task | Tool |
|---|---|
| The app has a CLI, config file, scripting API or MCP server for it | that, not the GUI |
| A native window: buttons, dialogs, settings, forms, menus, tray | **this skill** |
| A website | `browser` |
| No accessibility tree (a game, a canvas, a remote desktop) | screenshot computer use |

## Running

```bash
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/desktop/scripts/ad.py" windows
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/desktop/scripts/ad.py" snap --app CalculatorApp.exe
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/desktop/scripts/ad.py" act click e34
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/skills/desktop/scripts/ad.py" raw get e6 --property value
```

`snap` prints `eN role 'name' =value [states]`; a bare `e34` means that ref in the last snapshot.
`act <action> eN [args]` runs any ref action (`click`, `set-value`, `clear`, `toggle`, `check`,
`select`, `expand`, `scroll-to` ...), re-reads the same scope and prints what changed: `-` lines
gone, `+` lines new with their fresh refs, or `nothing changed`. Anything else goes through `raw`
with refs expanded. Flags after the arguments reach agent-desktop unchanged (`--root e3`,
`--timeout-ms 30000`, `--window-id w-123`). Full command semantics: `agent-desktop skills get
desktop` and `agent-desktop skills get platform`, which always match the installed binary.

## Loop

1. `windows`: find the window and the app name to pass to `--app`.
2. `snap --app NAME`: the controls. A big app: `snap --app NAME --skeleton`, then
   `snap --root eN` into one region. `--all` keeps static text (labels of repeated rows).
3. `act ACTION eN`: read the change report. It is the verification: a click whose report says
   `nothing changed` did nothing visible.
4. Repeat from 2 only when the report does not show the refs you need next.

## Rules learned from runs

**The window's app name is not the name you launched.** `launch calc` answered `calc.exe`, the
window belongs to `CalculatorApp.exe`, and `list-apps` did not list Calculator at all (Windows 11,
03.11.2026). Take the name from `windows`, which reads windows, not processes.

**`close-app` knows only `list-apps` names.** It answered `APP_NOT_FOUND` for `CalculatorApp.exe`.
Close such a window you opened with its own close button (`act click` on `'Close ...'`); the
report then says `the window is gone`.

**A new window can hold the user's own document.** `launch notepad` on Windows 11 reopened every
tab of the user's previous session, and the editor field held their file. `act set-value`,
`clear` and `type` refuse a field that already holds text and print what is in it; pass
`--overwrite` only when the user named that field or document. A text field you mean to fill
starts empty: if it does not, you are in the wrong place.

**An element whose value lives in its name goes stale after it changes.** Calculator's display is
`statictext 'Display is 7'`; after a click its old ref returned `STALE_REF`, because a ref is
identified by role and name. Read the result from the change report or a fresh `snap`, not with
`get` on the old ref.

**Headless by default, and keep it.** Ref actions use accessibility calls: no cursor, no focus
steal, no keystrokes into whatever window is in front. Calculator computed 7 + 8 with the user's
foreground untouched. `--headed` (physical mouse and keys, needed for `type`, `hover`, `drag`,
double-click on Windows) only with the user's explicit yes for that run, never as a retry after a
headless failure. Synthetic keys landing in the wrong window is how one session deleted every clip
on a video timeline: select-all and Backspace went to the main window instead of a panel.

**Retry only what was not delivered.** Each result carries `delivery`; an error prints
`retry=safe` only for `not_delivered`. Anything else may have landed: read the state, then decide.
A second click can submit twice, a second `toggle` undoes the first.

**An app running as administrator cannot be driven from a normal terminal.** Windows blocks the
input (`PERM_DENIED`, `E_ACCESSDENIED`); a window title with `[Admin]` is the hint. Reading still
works. Do not elevate on your own: tell the user.

**Irreversible controls need the user's yes.** Send, delete, submit, pay, accept terms, save over
a file: name the control and what it will do, and wait for an answer in chat, as with any action on
their behalf.

**Chromium and Electron apps start nearly empty.** The first read starts the renderer's
accessibility and returns a fraction of the tree; a cold app takes 10-25 s (agent-desktop docs, not
measured here). Pass `--timeout-ms 30000` before concluding a control is missing.

## Never

- Solve a CAPTCHA, a sign-in challenge or a UAC prompt. The secure desktop is unreachable anyway;
  hand the window to the user.
- Type passwords, keys or payment details into a field.
- Close an app the user had open before the run (`close-app`), or one with unsaved work.
