"""Tests for the plugin's hook scripts: each fires where it must and stays quiet where it must not.

    uv run --no-project tests/test_hooks.py

Why. A hook is the only layer that does not persuade but refuses. It is also an ordinary
script: a typo in a regex, a renamed payload key, a broken path, and the gate stops catching
without saying so. From outside, a broken gate looks exactly like a gate with nothing to catch.
So every gate is checked both ways, on throwaway folders; nothing here touches real memory,
a real vault or a real remote.

Exit 0: all passed. Exit 1: something failed (listed).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FAILED: list[str] = []


def hook(script: str, payload: dict, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", env={**os.environ, **env})


def expect(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if not ok and detail else ""))
    if not ok:
        FAILED.append(name)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="sb_hooks_"))
    mem, vault, data = tmp / "memory", tmp / "vault", tmp / "data"
    for d in (mem, vault, data):
        d.mkdir()
    env = {
        "CLAUDE_PLUGIN_OPTION_MEMORY_DIR": str(mem),
        "CLAUDE_PLUGIN_OPTION_VAULT_DIR": str(vault),
        "CLAUDE_PLUGIN_OPTION_MEMORY_AUTOPUSH": "true",
        "CLAUDE_PLUGIN_DATA": str(data),
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }

    # -- guard_heredoc
    long_cmd = "cat > f.py <<'EOF'\n" + "\n".join(f"line {i}" for i in range(8)) + "\nEOF"
    r = hook("guard_heredoc.py", {"tool_name": "Bash", "tool_input": {"command": long_cmd}}, env)
    expect("heredoc: long body blocked", r.returncode == 2 and "heredoc" in r.stderr, r.stderr[:80])
    r = hook("guard_heredoc.py", {"tool_name": "Bash", "tool_input": {"command": "cat <<EOF\nhi\nEOF"}}, env)
    expect("heredoc: short body passes", r.returncode == 0)
    r = hook("guard_heredoc.py", {"tool_name": "Write", "tool_input": {"content": long_cmd}}, env)
    expect("heredoc: other tools ignored", r.returncode == 0)

    # -- guard_literalpath
    r = hook("guard_literalpath.py", {"tool_name": "PowerShell", "tool_input": {"command": 'Remove-Item "Notes [1].md"'}}, env)
    out = json.loads(r.stdout or "{}").get("hookSpecificOutput", {})
    expect("literalpath: bracket delete rewritten",
           r.returncode == 0 and "-LiteralPath" in out.get("updatedInput", {}).get("command", ""), r.stdout[:120])
    r = hook("guard_literalpath.py", {"tool_name": "PowerShell", "tool_input": {"command": 'Remove-Item "a [1].md"; ls'}}, env)
    expect("literalpath: compound command blocked", r.returncode == 2)
    r = hook("guard_literalpath.py", {"tool_name": "PowerShell", "tool_input": {"command": "Remove-Item *.tmp"}}, env)
    expect("literalpath: wildcard delete untouched", r.returncode == 0 and not r.stdout.strip())

    # -- guard_memory_scope
    entry = "---\nname: x\ndescription: y\nmetadata:\n  type: user\n  source: stated\n---\nbody\n"
    no_source = entry.replace("  source: stated\n", "")
    w = lambda path, content: {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": content}}
    r = hook("guard_memory_scope.py", w(mem / "x.md", entry), env)
    expect("memory: a well-formed entry passes", r.returncode == 0, r.stderr[:80])
    r = hook("guard_memory_scope.py", w(mem / "x.md", "just text"), env)
    expect("memory: entry without frontmatter blocked", r.returncode == 2)
    r = hook("guard_memory_scope.py", w(mem / "x.md", no_source), env)
    expect("memory: entry without source blocked", r.returncode == 2 and "source" in r.stderr, r.stderr[:80])
    r = hook("guard_memory_scope.py", w(mem / "x.md", entry.replace("stated", "guessed")), env)
    expect("memory: an unknown source value blocked", r.returncode == 2)
    r = hook("guard_memory_scope.py", w(mem / "mistakes" / "2026-01-01-x.md", "MISTAKE: a"), env)
    expect("memory: the journal needs no frontmatter", r.returncode == 0, r.stderr[:80])
    r = hook("guard_memory_scope.py", w(mem / "x.md", entry + "<private>my salary</private>"), env)
    expect("private: blocked in memory", r.returncode == 2 and "private" in r.stderr.lower())
    r = hook("guard_memory_scope.py", w(mem / "x.md", entry + "<private>x</private>"), {**env, "AGENT_MEMORY_UNLOCK": "1"})
    expect("private: unlock does not open it", r.returncode == 2)
    r = hook("guard_memory_scope.py", w(vault / "Note.md", "text <private>x</private>"), env)
    expect("private: blocked in the vault", r.returncode == 2)
    r = hook("guard_memory_scope.py", w(vault / "Note.md", "an ordinary note"), env)
    expect("private: an ordinary vault note passes", r.returncode == 0, r.stderr[:80])
    r = hook("guard_memory_scope.py", w(tmp / "elsewhere.md", "<private>x</private>"), env)
    expect("private: files outside memory and vault ignored", r.returncode == 0)
    r = hook("guard_memory_scope.py", w(mem / "x.md", entry + "key ghp_" + "a" * 30), env)
    expect("memory: a secret blocked", r.returncode == 2 and "secret" in r.stderr.lower())
    r = hook("guard_memory_scope.py", w(mem / "x.md", entry + "key ghp_" + "a" * 30), {**env, "AGENT_MEMORY_UNLOCK": "1"})
    expect("memory: unlock does not open a secret", r.returncode == 2)
    (mem / "README.md").write_text("# memory\n", encoding="utf-8")
    edit = {"tool_name": "Edit", "tool_input": {"file_path": str(mem / "README.md"), "old_string": "a", "new_string": "b"}}
    r = hook("guard_memory_scope.py", edit, env)
    expect("memory: constitution protected", r.returncode == 2)
    r = hook("guard_memory_scope.py", edit, {**env, "AGENT_MEMORY_UNLOCK": "1"})
    expect("memory: unlock opens the constitution", r.returncode == 0)
    r = hook("guard_memory_scope.py", w(tmp / "elsewhere.md", "ghp_" + "a" * 30), env)
    expect("memory: files outside memory ignored", r.returncode == 0)
    r = hook("guard_memory_scope.py", w(mem / "x.md", "just text"), {k: v for k, v in env.items() if "MEMORY_DIR" not in k})
    expect("memory: unconfigured plugin stays quiet", r.returncode == 0)

    # -- file_context
    (mem / "tool-pitfall.md").write_text(entry.replace("body", "Run `frobnicate.py` with --safe, it corrupts otherwise."),
                                         encoding="utf-8")
    (mem / "mistakes").mkdir(exist_ok=True)
    (mem / "mistakes" / "2026-01-02-skill.md").write_text("MISTAKE: m\nPATTERN: edit video/SKILL.md carefully\n",
                                                        encoding="utf-8")
    read = lambda p, s="s1": {"tool_name": "Read", "session_id": s, "tool_input": {"file_path": str(p)}}
    ctx = lambda r: json.loads(r.stdout or "{}").get("hookSpecificOutput", {}).get("additionalContext", "")
    r = hook("file_context.py", read(tmp / "proj" / "frobnicate.py"), env)
    expect("file-context: memory about the file is surfaced", "tool-pitfall.md" in ctx(r) and r.returncode == 0, r.stdout[:120])
    r = hook("file_context.py", read(tmp / "proj" / "frobnicate.py"), env)
    expect("file-context: the same file is served once per session", not r.stdout.strip())
    r = hook("file_context.py", read(tmp / "proj" / "frobnicate.py", "s2"), env)
    expect("file-context: a new session gets it again", "tool-pitfall.md" in ctx(r))
    r = hook("file_context.py", read(tmp / "skills" / "video" / "SKILL.md"), env)
    expect("file-context: a generic name matches by parent/name", "2026-01-02-skill.md" in ctx(r), r.stdout[:120])
    r = hook("file_context.py", read(tmp / "skills" / "notes" / "SKILL.md"), env)
    expect("file-context: a generic name alone does not match", not r.stdout.strip(), r.stdout[:120])
    r = hook("file_context.py", read(tmp / "proj" / "unrelated.py"), env)
    expect("file-context: nothing known, nothing said", not r.stdout.strip())
    r = hook("file_context.py", read(mem / "tool-pitfall.md"), env)
    expect("file-context: reading memory itself adds nothing", not r.stdout.strip())

    # -- journal_reflect
    (mem / "mistakes" / "2026-01-03-a.md").write_text(
        "MISTAKE: said verified without a check\nPATTERN: name the artifact before claiming checked\n", encoding="utf-8")
    (mem / "mistakes" / "2026-01-05-b.md").write_text(
        "ОШИБКА: заявил проверенное\nПАТТЕРН: проверил только тем, что могло показать обратное\n", encoding="utf-8")
    (mem / "mistakes" / "2026-01-06-c.md").write_text(
        "MISTAKE: tried --cookies-from-browser\nPATTERN: it fails here, use a cookies file\nKIND: dead_end\n",
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "journal_reflect.py"), "--memory", str(mem)],
                       capture_output=True, text=True, encoding="utf-8")
    verif = r.stdout.split("verification:")[1].split("##")[0] if "verification:" in r.stdout else ""
    expect("reflect: English and Russian entries land in one class",
           "2026-01-03-a.md" in verif and "2026-01-05-b.md" in verif, r.stdout[:300])
    expect("reflect: two distinct days propose a rule", "2 distinct day(s)" in r.stdout.split("verification:")[1][:80]
           if "verification:" in r.stdout else False)
    dead = r.stdout.split("Dead ends")[1] if "Dead ends" in r.stdout else ""
    expect("reflect: dead ends listed separately", "2026-01-06-c.md" in dead and "2026-01-06-c.md" not in verif)

    # -- verify_vault
    (vault / "Target.md").write_text("# Target\n\n## Part\n", encoding="utf-8")
    (vault / "Old.md").write_text("[[Nowhere old]]\n", encoding="utf-8")     # pre-existing breakage
    note = vault / "Note.md"
    note.write_text("[[Target#Part]] and [[Missing note]]\n", encoding="utf-8")
    hook("verify_vault.py", {"tool_name": "Write", "tool_input": {"file_path": str(note)}}, env, "--mark")
    r = hook("verify_vault.py", {}, env, "--stop")
    expect("vault: a new broken link blocks the stop", r.returncode == 2 and "Missing note" in r.stderr, r.stderr[:160])
    note.write_text("[[Target#Part]] only\n", encoding="utf-8")
    hook("verify_vault.py", {"tool_name": "Edit", "tool_input": {"file_path": str(note)}}, env, "--mark")
    r = hook("verify_vault.py", {}, env, "--stop")
    expect("vault: fixed note passes", r.returncode == 0, r.stderr[:160])
    (vault / "Old.md").write_text("[[Nowhere old]] plus an append\n", encoding="utf-8")
    hook("verify_vault.py", {"tool_name": "Edit", "tool_input": {"file_path": str(vault / "Old.md")}}, env, "--mark")
    r = hook("verify_vault.py", {}, env, "--stop")
    expect("vault: an old broken link does not block", r.returncode == 0, r.stderr[:160])
    r = hook("verify_vault.py", {"stop_hook_active": True}, env, "--stop")
    expect("vault: no loop when the stop was already blocked", r.returncode == 0)
    r = hook("verify_vault.py", {}, env, "--stop")
    expect("vault: nothing touched, nothing checked", r.returncode == 0 and not r.stderr.strip())

    # -- session_start
    (mem / "claude").mkdir()
    (mem / "claude" / "rules.md").write_text("# Working rules\nRULE-MARKER\n", encoding="utf-8")
    r = hook("session_start.py", {"source": "startup"}, env)
    expect("session: rules printed at start", r.returncode == 0 and "RULE-MARKER" in r.stdout, r.stdout[:120])
    r = hook("session_start.py", {"source": "compact"}, env)
    expect("session: state added after compaction", "State at compaction time" in r.stdout, r.stdout[-200:])
    r = hook("session_start.py", {"source": "startup"}, {k: v for k, v in env.items() if "MEMORY_DIR" not in k})
    expect("session: unconfigured plugin points at setup", r.returncode == 0 and "setup" in r.stdout)

    # -- memory_autocommit (with a local bare remote)
    remote = tmp / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], capture_output=True)
    git(mem, "init", "-b", "main")
    git(mem, "remote", "add", "origin", str(remote))
    r = hook("memory_autocommit.py", {}, env)
    log = git(mem, "log", "--oneline").stdout
    expect("autocommit: changes committed", r.returncode == 0 and "memory " in log, (r.stderr + log)[:160])
    git(mem, "push", "-u", "origin", "main")
    (mem / "y.md").write_text(entry, encoding="utf-8")
    hook("memory_autocommit.py", {}, env)
    expect("autocommit: pushed to the remote",
           git(mem, "rev-parse", "HEAD").stdout == git(remote, "rev-parse", "main").stdout)
    before = git(mem, "rev-parse", "HEAD").stdout
    hook("memory_autocommit.py", {}, env)
    expect("autocommit: nothing changed, no empty commit", git(mem, "rev-parse", "HEAD").stdout == before)

    # -- check_push_landed (same repo and remote)
    push = {"tool_name": "Bash", "tool_input": {"command": f'git -C "{mem}" push'}, "cwd": str(tmp)}
    r = hook("check_push_landed.py", push, env)
    expect("push: a landed push stays quiet", r.returncode == 0, r.stderr[:120])
    (mem / "z.md").write_text(entry, encoding="utf-8")
    git(mem, "add", "-A")
    git(mem, "commit", "-m", "local only")
    r = hook("check_push_landed.py", push, env)
    expect("push: a push that did not land is reported", r.returncode == 2 and "did NOT land" in r.stderr, r.stderr[:120])
    r = hook("check_push_landed.py", {"tool_name": "Bash", "tool_input": {"command": "git status"}}, env)
    expect("push: other git commands ignored", r.returncode == 0)

    print(f"\n{'ALL GREEN' if not FAILED else f'{len(FAILED)} FAILED: ' + ', '.join(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
