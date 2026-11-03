# Setup

## Install

```bash
npm install -g agent-desktop        # Node 18+; carries native binaries for Windows, macOS, Linux
agent-desktop version               # confirm the command resolves
agent-desktop status                # permissions and supported surfaces
```

`status` on Windows should report `accessibility: granted`; Windows has no permission dialog for UI
Automation. macOS needs the Accessibility grant: `agent-desktop permissions --guide`. Linux needs
the graphical session's AT-SPI bus; an empty `supported_surfaces` means it did not answer.

## The slow launcher

The package's install script links the native binary in place of a Node launcher. When npm does
not run it, every call starts Node first and the CLI prints a notice on stderr. On npm 11.13 the
flag the notice suggests, `--allow-scripts=agent-desktop`, was rejected as `Unknown cli config`
and the script did not run (03.11.2026). Running the package's own script once fixed it:

```bash
node "$(npm root -g)/agent-desktop/scripts/postinstall.js"
```

PowerShell:

```powershell
node "$(npm root -g)\agent-desktop\scripts\postinstall.js"
```

After it the npm shim calls the `.exe` directly: `agent-desktop version` took 0.35 s including the
shell, with no notice.

## What was checked

On agent-desktop 1.1.0 (repository commit `93ae89e`, 02.11.2026):

- **No telemetry found.** `Cargo.lock` has no HTTP client (`reqwest`, `ureq`, `hyper`, `curl`,
  `isahc`, `sentry`); the word `telemetry` in the sources is local error bookkeeping. The npm
  install script downloads nothing on a normal install: the binaries ship in the package, and it
  only fetches from GitHub Releases when one is missing or does not match its recorded digest,
  checking the SHA-256 of the download.
- **State** lives in `~/.agent-desktop` (snapshots, refmaps, sessions). `AGENT_DESKTOP_HOME`
  moves it; an elevated and a normal run cannot share one.
- **Live run** on Windows 11: Calculator 7 + 8 = 15 through headless clicks with the change report;
  the overwrite guard refused a write into a restored Notepad document.

## Upgrade

Read the release's changelog and the diff of `Cargo.toml` (new network dependencies) before
`npm install -g agent-desktop@<version>`, then rerun `tests/test_desktop.py` and one live `snap`.
The bundled guides (`agent-desktop skills get desktop`) update with the binary; this skill's rules
do not, so check them against the new guides.
