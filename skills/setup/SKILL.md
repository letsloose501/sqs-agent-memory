---
name: setup
description: >-
  First-time setup and repair of agent-memory: checks the tools (git, uv, MemPalace, gh),
  creates the agent memory repository and its private GitHub remote, creates a starter Obsidian
  vault, points Claude Code's auto memory at the repository, configures MemPalace as the vault
  index (embedding model, languages), and verifies everything. Use right after installing the
  plugin, on "set up agent memory", "install the memory system", "connect my vault", "memory is
  not loading", "move my memory folder", or when the SessionStart hook says the plugin is not
  configured.
---

<!-- sqs-allow-file: ST011 - this file describes paths in the user's home that exist only after installation (config files, profiles); they are absent on a fresh machine or in CI. -->

# Set up agent-memory

Walk the user through it in their language, one stage at a time. Every stage checks first, then
asks before changing anything outside the plugin, then verifies. Nothing here is done silently.

- Memory folder: `${user_config.memory_dir}`
- Vault folder: `${user_config.vault_dir}`
- Notes language: `${user_config.notes_language}`
- Script: `${CLAUDE_PLUGIN_ROOT}/scripts/setup.py` (written `setup.py` below; run it with
  `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/setup.py" <step>`)

If the two folders above are empty, the plugin options were never filled: ask the user to set them
(each option is a row in `/config` once the plugin is enabled; Claude Code also asks for them when the plugin is enabled), then start again.

## Stage 0: what is there

Run `setup.py check`. It lists the tools, the GitHub login, the git identity, and the current
settings. Tell the user what is missing, grouped:

- **Required**: `git`, `uv`, `mempalace` + `mempalace-mcp` on PATH. Install commands are in the
  plugin's `docs/install.md`; give them in the user's shell dialect (PowerShell on Windows).
  MemPalace: `uv tool install mempalace`, then `uv tool update-shell` and restart the terminal and
  the app so `mempalace-mcp` is on PATH.
- **Git identity** (`user.name`, `user.email`): memory commits need it. Ask for the values; for
  GitHub, the privacy-safe email is the `<id>+<login>@users.noreply.github.com` address shown in
  GitHub's email settings.
- **Optional**: `gh` (to create the private repo), `ffmpeg` and a Groq key (video tier 3),
  `browser-harness` (the browser skill). Mention them; install only what the user wants.

Do not install anything yourself without a yes: installing software changes the machine.

## Stage 1: the memory repository

1. `setup.py memory --memory "${user_config.memory_dir}"`: copies the template (README, SCOPES,
   MEMORY index, `claude/rules.md`, `mistakes/`), runs `git init` and the first commit. Existing
   files are never overwritten.
2. **A private remote** so memory survives a dead disk. Ask first: it creates something on the
   user's GitHub account. With `gh` logged in:
   `gh repo create <name> --private --source "${user_config.memory_dir}" --push`.
   Without `gh`: the user creates an **empty private** repository on github.com, then
   `git -C "${user_config.memory_dir}" remote add origin <url>` and `git push -u origin main`.
   It must be private: memory holds personal facts. Check with `gh repo view <name> --json visibility`.
3. `memory_autopush` (a plugin option, on by default) pushes after every turn once a remote exists.

## Stage 2: point Claude Code's auto memory at the repository

Claude Code keeps auto memory per project unless `autoMemoryDirectory` is set; with it, every
project reads and writes the same memory. A plugin cannot set it (plugin settings only carry
`agent` and `subagentStatusLine`), so it goes into the user's `~/.claude/settings.json`.

Ask, then `setup.py settings --memory "${user_config.memory_dir}"`. It backs up the file once
(`settings.json.bak-agent-memory`) and changes only that key. The new value takes effect in the next
session.

The rules (`claude/rules.md` in the memory repo) need no setting: the plugin's SessionStart hook
prints them into every session. The user edits that file to change them.

## Stage 3: the Obsidian vault

1. If the vault folder is empty or new: `setup.py vault --vault "${user_config.vault_dir}"` creates
   the starter layout (`Vault map.md`, `Inbox.md`, topic folders, the video and PDF registries).
   An existing vault: do not run it blindly; show what it would add (it only adds missing files)
   and ask. For an existing vault, write its real top-level folders into `Vault map.md` instead.
2. The user opens the folder in Obsidian: "Open folder as vault". Obsidian itself is installed from
   obsidian.md (`docs/install.md`).
3. Recommend the community plugin **Spaced Repetition** if they want cards (the `notes` skill writes
   decks in its format).

## Stage 4: MemPalace as the vault index

MemPalace has two models inside, and both are the user's choice:

- **The embedder** (search). `minilm` is English-only; `embeddinggemma` is multilingual (100+
  languages, about 300 MB downloaded on first use); `openai-compat` uses a local server such as
  Ollama or LM Studio. Recommend `embeddinggemma` whenever the notes language is not English.
  Switching later on a filled palace needs `mempalace repair rebuild-index`.
- **Entity languages**: the languages of the notes, for entity detection.

Then `setup.py mempalace --model <model> --langs <codes>`. It also sets `hooks.auto_save: false`:
here the palace is only the vault index. Session snapshots measured on one real palace were 96 % of
its volume and answered nothing; the mistakes journal lives in the memory repository.

`mempalace init` has an optional LLM step for entity refinement (Ollama by default; OpenAI-compatible
or Anthropic on request). It is not needed for the index; skip it unless the user wants it, and if an
external provider is chosen, say that note content leaves the machine.

The MCP server comes with the plugin (`.mcp.json` runs `mempalace-mcp`); it appears after the app
restarts. A vault that already has notes: run the `vault-index` skill in batches to card them.

## Stage 5: verify

1. `setup.py check` again: everything required shows `ok`.
2. In a **new** session: the SessionStart output contains the rules; the auto-memory section of the
   system prompt names the memory folder; `ToolSearch("mempalace")` returns the
   `mempalace_*` tools.
3. `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/memory_eval.py" --memory "${user_config.memory_dir}" --dry`
   prints the index size.

Report what was set up, what was skipped and why, and the one thing left for the user to do, if any.
Do not claim a stage works that you could not check (a new-session check cannot be run from this
session: say it is pending).

## Moving things later

- Another memory folder: change the plugin option, move the folder (it is a git repository, moving
  keeps history), rerun Stage 2.
- Another vault: change the option; the MemPalace cards store paths relative to the vault, so they
  stay valid if the folder structure inside is the same.
