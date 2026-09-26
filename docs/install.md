# Installing agent-memory

About 20 minutes the first time. Commands are given for **Windows (PowerShell)** and **macOS**;
on Linux use your package manager for git and the macOS line for uv.

What you end up with:

- **Agent memory**: a private git repository of markdown files that Claude reads at the start of
  every session and writes to as it learns how you work.
- **A knowledge vault**: an Obsidian folder of notes that Claude writes from videos, PDFs and text.
- **MemPalace**: a local search index over the vault, so notes are found by meaning.
- **Skills and hooks** that fill and guard all of the above.

## 1. Git and uv

uv runs every script and hook in the plugin and installs their dependencies by itself.

Windows (PowerShell):

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
```

macOS:

```bash
xcode-select --install
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen the terminal, then check: `git --version` and `uv --version`.

## 2. A GitHub account

Your memory is backed up to a **private** GitHub repository, so it survives a dead disk and follows
you to a new machine.

1. Create an account at https://github.com/signup (free).
2. Install the GitHub CLI and log in; it lets Claude create the private repository for you.

   Windows: `winget install --id GitHub.cli -e` · macOS: `brew install gh`

   ```bash
   gh auth login
   ```

   Pick GitHub.com, HTTPS, and log in with the browser.
3. Tell git who you are. Use the private noreply address from
   https://github.com/settings/emails (it looks like `12345678+yourname@users.noreply.github.com`),
   so your real email never lands in commit history:

   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "12345678+yourname@users.noreply.github.com"
   ```

## 3. Obsidian

Obsidian is the app you read and edit the notes in. The notes are plain markdown files; Obsidian
adds links, search and the graph.

Windows: `winget install --id Obsidian.Obsidian -e` · macOS: `brew install --cask obsidian`
(or download from https://obsidian.md).

Do not create a vault yet: step 6 creates a starter one, and you open it in Obsidian afterwards.
If you already have a vault, keep it and point the plugin at it.

Optional, for flash cards: in Obsidian, Settings > Community plugins > Browse, install
**Spaced Repetition**.

## 4. MemPalace

```bash
uv tool install mempalace
uv tool update-shell
```

Reopen the terminal, then check: `mempalace --version` and `mempalace-mcp --help`. The plugin starts
`mempalace-mcp` as an MCP server, so it has to be on PATH. The search model (about 300 MB for the
multilingual one) downloads the first time it is used.

## 5. The plugin

In Claude Code (terminal):

```text
/plugin marketplace add letsloose501/sqs-agent-memory
/plugin install agent-memory@agent-memory
```

In the desktop app: **+** next to the prompt box > **Plugins** > **Add plugin**, after adding the
marketplace the same way.

Claude Code asks for the plugin's options:

| Option | What to enter |
|---|---|
| Agent memory folder | where the memory repository will live, for example `~/agent-memory` |
| Obsidian vault folder | your vault, or an empty folder for a new one, for example `~/Vault` |
| Language of your notes | the language notes are written in, for example `English` |
| Push memory to its remote | leave on |

To change them later: `/plugin`, the **Installed** tab, the plugin, **Configure options**.

## 6. Setup

Start a new Claude Code session and run:

```text
/agent-memory:setup
```

It checks the tools, creates the memory repository and its private GitHub remote, creates the
starter vault, points Claude Code's auto memory at the repository, configures MemPalace, and asks
before every change outside the plugin. Then open the vault folder in Obsidian: "Open folder as vault".

Restart Claude Code once more so the memory folder and the MemPalace server take effect.

## Optional extras

| For | Install |
|---|---|
| Transcripts of videos without captions (video skill, tier 3) | ffmpeg (Windows `winget install --id Gyan.FFmpeg -e`, macOS `brew install ffmpeg`) and a free Groq key from https://console.groq.com/keys in the `GROQ_API_KEY` environment variable or in `~/.config/agent-memory/.env` as `GROQ_API_KEY=...` |
| The browser skill | `browser-harness`, see `skills/browser/references/setup.md` |
| Compiling LaTeX | a TeX distribution (MiKTeX or TeX Live) |

## Checking that it works

- A new session starts with your working rules printed at the top (from `claude/rules.md` in the
  memory repository).
- "Take notes on this: ..." with a paragraph of text creates a note in the vault and a card in the index.
- `uv run --no-project <plugin>/scripts/setup.py check` shows every required tool as `ok`.

## Updating and removing

- Update: `claude plugin update agent-memory@agent-memory`, or turn on auto-update for the
  marketplace in `/plugin` > Marketplaces.
- Remove: `/plugin uninstall agent-memory@agent-memory`. Your memory repository, vault and palace
  stay where they are; they are your files, not the plugin's.
