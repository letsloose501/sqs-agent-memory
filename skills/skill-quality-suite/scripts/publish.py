#!/usr/bin/env python3
"""What has to be true before a skill leaves the machine it was written on.

Everything here is invisible while the skill only ever runs at home, and obvious the
moment somebody else installs it: a path into a directory only you have, a vault note
nobody else can read, a version that disagrees with the manifest, documentation in a
language the repository is not written in.

This module is not part of `sqs.py check`. It runs when you ask for it, because half
its findings are correct-and-intended for a private skill.
"""
import fnmatch
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile

import capabilities
from core import Finding, Skill, parse_frontmatter
from model import parse_tools
from security import PERSONAL, PERSONAL_GENERIC

LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
# A path into somewhere only the author can reach. `~/.claude/skills/...` is exempt:
# that is where a skill legitimately points at its neighbours.
PRIVATE_PATH = re.compile(r"[`\"']?(~|\$env:USERPROFILE|%USERPROFILE%)[/\\]"
                          r"(?!\.claude[/\\]skills)([^\s`\"'\n]{2,80})")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
EMAIL_GENERIC = re.compile(r"@(?:example\.|test\.|localhost|domain\.|email\.)", re.I)
# Backtick, double quote, apostrophe: what a quoted path is wrapped in.
QUOTES = "`" + chr(34) + chr(39)
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
SCRIPTS = {"en": CYRILLIC}

# Component directories the official plugin layout documents beside `skills/`. `scripts/`
# is deliberately left out: a skill legitimately carries its own, so a bare mention of it
# says nothing about whether the path escapes this skill's own folder.
PACKAGE_DIRS = ("commands", "agents", "workflows", "hooks", "monitors", "bin")
SIBLING_RE = re.compile(
    r"\$\{CLAUDE_PLUGIN_ROOT\}[/\\][\w./\\-]*"
    r"|(?:\.\./)+(?:" + "|".join(PACKAGE_DIRS) + r")/[\w./-]+")


def manifest_version(skill):
    """(version, manifest path) from the nearest plugin manifest, or (None, None)."""
    here = skill.root
    for _ in range(4):
        here = os.path.dirname(here)
        if not here or here == os.path.dirname(here):
            break
        for rel in (".claude-plugin/plugin.json", "plugin.json", ".claude-plugin/marketplace.json"):
            p = os.path.join(here, rel)
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("version"):
                return str(data["version"]), p
    return None, None


def plugin_root(skill):
    """The directory holding `.claude-plugin/`, walking up from the skill, or None.

    That is where `hooks/`, `commands/`, `agents/` and the manifest live - one level
    above the skill folder itself, or more when the skill sits under `skills/<name>/`.
    A skill written for itself, with no `.claude-plugin/` above it anywhere, has no
    package context to report, and PB007-PB009 stay silent.
    """
    here = skill.root
    for _ in range(4):
        here = os.path.dirname(here)
        if not here or here == os.path.dirname(here):
            break
        if os.path.isdir(os.path.join(here, ".claude-plugin")):
            return here
    return None


def _load_json(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def hook_findings(root):
    """PB007 - hooks the package wires beside this skill, whether or not it fires.

    `hooks/hooks.json` nests events under a top-level `hooks` key. A hook runs on its
    event regardless of whether the model ever routed to this skill, so a clean verdict
    printed next to an unread `hooks/` directory is the misleading half of the report.
    """
    data = _load_json(os.path.join(root, "hooks", "hooks.json"))
    events = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(events, dict):
        return []
    fired, total = [], 0
    for event, entries in events.items():
        if not isinstance(entries, list):
            continue
        n = sum(1 for entry in entries if isinstance(entry, dict)
                for h in entry.get("hooks", [])
                if isinstance(h, dict) and h.get("type") == "command")
        if n:
            fired.append(event)
            total += n
    if not total:
        return []
    return [Finding("PB007",
                    f"package also wires {total} hook command(s) on {', '.join(sorted(fired))} "
                    f"(hooks/hooks.json) - they run on the event whether or not this skill is "
                    f"ever invoked")]


def sibling_findings(skill):
    """PB008 - the skill points at a package component outside its own folder.

    The structure rules only resolve a pointer that stays inside the skill, so a link
    through `${CLAUDE_PLUGIN_ROOT}` or a `../` into a sibling component directory is
    invisible to them today - and breaks in silence the moment the skill is copied out
    of the plugin, which is exactly what installing it standalone does.
    """
    out = []
    for rel, text in skill.texts():
        for n, line in enumerate(text.split("\n"), 1):
            m = SIBLING_RE.search(line)
            if m:
                out.append(Finding("PB008",
                    f"`{m.group(0)}` points at a package sibling, not at this skill",
                    where=rel, line=n))
    return out


def origin_finding(root, plugin_name):
    """PB009 - the marketplace's declared source for this plugin, printed as a fact.

    A local `\"./...\"` source is a checkout of the same repository and is not reported:
    the interesting case is a remote source - `github`, `url`, `git-subdir`, `npm`,
    `archive`, `command` - where the files under review may be a checkout nobody has
    looked at.
    """
    data = _load_json(os.path.join(root, ".claude-plugin", "marketplace.json"))
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        return []
    entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == plugin_name),
                 None)
    if entry is None and len(plugins) == 1 and isinstance(plugins[0], dict):
        entry = plugins[0]
    source = entry.get("source") if entry else None
    if not isinstance(source, dict):
        return []
    kind = source.get("source", "?")
    where = source.get("repo") or source.get("url") or source.get("package") or "?"
    detail = source.get("path") or source.get("ref") or ""
    return [Finding("PB009", f"installed from {kind}: {where}"
                             + (f" ({detail})" if detail else ""))]


# ---- the version as a claim about the content ---------------------------------------

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
# `version` is not one of the specification's frontmatter fields - it belongs under
# `metadata:`, which `compat.py` already records. The frontmatter parser is flat by
# design, so a nested block arrives as one string under its parent key and the nested
# spelling has to be read back out of it. Without this, half the skills in the wild
# declare a version this module cannot see.
META_VERSION_RE = re.compile(r"\bversion:\s*['\"]?([^\s'\",}]+)")
# Frontmatter fields that decide how a skill is called, rather than what it says. A
# change to one of these is a change a caller can trip over, which is the line the
# specification's own "breaking change" wording draws.
SURFACE_FIELDS = ("name", "disable-model-invocation", "allowed-tools")
# Capabilities that take something off the machine or run something else on it - the two
# a reader has to re-decide on when an update gains them.
REACH_CODES = ("CB001", "CB002")


def declared_version(fm):
    """The version a skill claims - top level or under `metadata:` - or None."""
    own = (fm.get("version") or "").strip().strip("'\"")
    if own:
        return own
    m = META_VERSION_RE.search(fm.get("metadata") or "")
    return m.group(1) if m else None


def _git(root, *args):
    """(ok, stdout) for a git command run inside the skill's own directory.

    `-C` puts git's idea of "here" on the skill, which is what makes `--relative` and
    `<ref>:./<path>` resolve against the skill rather than against the repository root.
    """
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except OSError:
        return False, ""
    return r.returncode == 0, r.stdout


def resolve_since(since, root):
    """(comparison spec, note) for `--since`, or (None, why not).

    `--since` names the earlier state the version number is a claim against, and it
    takes two spellings because the two questions people actually ask are different.
    A git ref answers *did I bump it since the last release*. A directory answers
    *the copy I installed and the copy I edit disagree - which one is 1.2.0*, which
    is the case a version number exists for and the one git cannot see at all.

    A relative directory is looked for beside the skills directory first, so the flag
    can be written in a config or a fixture without an absolute path. Ambiguity is
    resolved towards the directory and said out loud in the note, because a ref and a
    folder sharing a name is rare and silence about which one won would not be.
    """
    if not since:
        return None, ""
    for cand in (since, os.path.join(root, since)):
        if os.path.isdir(cand):
            return ({"kind": "tree", "root": os.path.abspath(cand)},
                    f"--since: comparing against the copy in {os.path.abspath(cand)}")
    ok, _ = _git(root, "rev-parse", "--verify", since + "^{commit}")
    if not ok:
        return None, (f"--since {since!r} is neither a directory nor a commit this "
                      f"checkout knows - the version rules (PB010-PB013) did not run")
    return {"kind": "git", "ref": since}, f"--since: comparing against git {since}"


def _previous_from_git(skill, ref):
    """(changed paths, previous frontmatter) for a skill as of a commit, or None."""
    ok, text = _git(skill.root, "show", f"{ref}:./SKILL.md")
    if not ok:
        return None                      # the skill did not exist then: nothing to bump
    changed = set()
    for cmd in (("diff", "--name-only", "--relative", ref, "--", "."),
                ("diff", "--name-only", "--relative", "--cached", ref, "--", "."),
                ("ls-files", "--others", "--exclude-standard", "--", ".")):
        ok, out = _git(skill.root, *cmd)
        if not ok:
            return None
        changed |= {ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()}
    _, fm, _ = parse_frontmatter(text)
    return sorted(p for p in changed if not skill.ignored(p)), fm


def _previous_from_tree(skill, tree):
    """(changed paths, previous frontmatter) for a skill as an earlier copy, or None."""
    for cand in (os.path.join(tree, skill.folder), tree):
        if os.path.isfile(os.path.join(cand, "SKILL.md")):
            old = Skill(cand)
            break
    else:
        return None
    def payload(s):
        return {rel: os.path.join(s.root, rel.replace("/", os.sep))
                for rel, _, _ in s.walk()}
    before, after = payload(old), payload(skill)
    changed = set(before) ^ set(after)
    for rel in set(before) & set(after):
        if _bytes(before[rel]) != _bytes(after[rel]):
            changed.add(rel)
    return sorted(changed), old.fm


def _bytes(path):
    """File contents with line endings flattened.

    Two checkouts of the same file on Windows differ by `\\r` alone whenever
    `core.autocrlf` is on, and a rule that reported that as an improvement would fire
    on every skill on half the machines that run it.
    """
    try:
        with open(path, "rb") as f:
            return f.read().replace(b"\r\n", b"\n")
    except OSError:
        return None


def previous_copy(skill, spec, workdir):
    """A directory holding this skill as it was at `--since`, or None.

    The tree form of `--since` already is one. The git form is materialised here with
    `git archive` read as a tar stream through the standard library, because a caller
    that wants to know what the skill's *scripts* used to do needs a tree to walk, and
    `git show` one file at a time cannot hand it one. No `tar` binary is involved: this
    has to work on a Windows box where nothing was installed.
    """
    if spec["kind"] == "tree":
        for cand in (os.path.join(spec["root"], skill.folder), spec["root"]):
            if os.path.isfile(os.path.join(cand, "SKILL.md")):
                return cand
        return None
    try:
        r = subprocess.run(["git", "-C", skill.root, "archive", "--format=tar",
                            spec["ref"], "--", "."], capture_output=True)
    except OSError:
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    target = os.path.join(workdir, skill.folder)
    os.makedirs(target, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
            for member in tf.getmembers():
                # A tar out of git cannot climb out of the tree, but a tar reader that
                # trusts its member names is how every other one has been exploited.
                dest = os.path.normpath(os.path.join(target, member.name))
                if not dest.startswith(os.path.normpath(target) + os.sep):
                    continue
                # `filter=` landed mid-3.9; the suite claims 3.9 and up, so the path
                # check above is the guard that has to hold on its own, and the filter
                # is the belt on top of it where the interpreter has one.
                try:
                    tf.extract(member, target, filter="data")
                except TypeError:
                    tf.extract(member, target)
    except (tarfile.TarError, OSError):
        return None
    return target if os.path.isfile(os.path.join(target, "SKILL.md")) else None


def surface_changes(old_fm, new_fm):
    """Plain-language names for the ways the skill is now called differently."""
    out = []
    for field in SURFACE_FIELDS:
        before = (old_fm.get(field) or "").strip()
        after = (new_fm.get(field) or "").strip()
        if before == after:
            continue
        if field == "allowed-tools":
            # Gaining a tool widens what the skill may do and breaks no caller -
            # that half is PB012's; losing one is the half that breaks a caller.
            _, lost = tool_delta(before, after)
            if lost:
                out.append(f"`allowed-tools` no longer carries {_spell(lost)}")
            continue
        out.append(f"`{field}` changed from `{before or '(absent)'}` to "
                   f"`{after or '(absent)'}`")
    return out


def _entries(raw):
    """`allowed-tools` as (tool, scope) pairs; an empty scope is the whole tool."""
    return {(name, s) for name, scopes in parse_tools(raw).items() for s in scopes or [""]}


def _covered(entry, by):
    """Whether the entries in `by` already permit everything `entry` does.

    An unscoped tool covers every scope of itself, and a scope covers a narrower one that
    matches it as a glob: `Bash(git *)` already allows `Bash(git log *)`. Anything else
    counts as new, including a rewrite that only looks narrower. Calling a narrowing new
    costs a reader one glance; calling a widening old is the miss PB012 exists to prevent.
    """
    name, scope = entry
    return any(n == name and (not s or s == scope
                              or (scope and fnmatch.fnmatchcase(scope, s)))
               for n, s in by)


def tool_delta(old_raw, new_raw):
    """(gained, lost) between two `allowed-tools` values, each a set of (tool, scope)."""
    before, after = _entries(old_raw), _entries(new_raw)
    return ({e for e in after if not _covered(e, before)},
            {e for e in before if not _covered(e, after)})


def _spell(entries):
    return ", ".join(f"{n}({s})" if s else n for n, s in sorted(entries))


def rollback_finding(old_fm, new_fm):
    """PB013 - the version this skill claims is older than the one it replaced.

    PB010 declines to read a version moving backwards, because inventing a meaning for
    it would be a guess. Replacing a patched release with an older one that is still
    correctly published is a named move, though - a rollback - and once the move has a
    name the reading is no longer invented. Both numbers have to parse: `1.2` against
    `1.10` is a string comparison nobody asked for, and no opinion beats a wrong one.
    """
    old, new = declared_version(old_fm), declared_version(new_fm)
    a, b = SEMVER_RE.match(old or ""), SEMVER_RE.match(new or "")
    if not a or not b:
        return []
    if tuple(map(int, b.group(1, 2, 3))) >= tuple(map(int, a.group(1, 2, 3))):
        return []
    return [Finding("PB013", f"`version: {old}` at --since, `{new}` now - the number "
                             f"went backwards")]


def reach_findings(skill, spec, changed, old_fm):
    """PB012 - this update can do something the version before it could not.

    A skill keeps the trust it earned when somebody read and installed it, while its
    content moves underneath. The reach grows two ways and they are one finding, because
    they are one claim - *this update goes further than the one you read* - made from two
    kinds of evidence: what the skill is now permitted to run without asking, and what its
    bundled scripts can now do.

    Only network (`CB001`) and process spawning (`CB002`) count as reach. Reading the
    environment (`CB003`) is already reported by `capabilities` on every run, and on its
    own it goes nowhere: getting a secret off the machine takes one of the other two.
    """
    grew = []
    gained, _ = tool_delta(old_fm.get("allowed-tools") or "",
                           skill.fm.get("allowed-tools") or "")
    if gained:
        grew.append(f"`allowed-tools` now also permits {_spell(gained)}")
    # Materialising the earlier tree costs a subprocess and an extraction, and a skill
    # whose scripts did not change cannot have gained an import.
    if any(p.lower().endswith(capabilities.SCRIPT_EXT) for p in changed):
        grew += _gained_reach(skill, spec)
    if not grew:
        return []
    return [Finding("PB012", "this update reaches further than the copy at --since: "
                             + "; ".join(grew))]


def _gained_reach(skill, spec):
    """One line per reach capability present now and absent from every earlier script."""
    with tempfile.TemporaryDirectory() as tmp:
        root = previous_copy(skill, spec, tmp)
        if root is None:
            return []
        had = {f.code for f in capabilities.check(Skill(root))}
    out = []
    for code in REACH_CODES:
        hits = [f for f in capabilities.check(skill) if f.code == code]
        if hits and code not in had:
            more = f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""
            out.append(f"{hits[0].where} {hits[0].msg}{more}")
    return out


def version_findings(skill, spec):
    """PB010 - PB013 - what moved between `--since` and now, and what the number said.

    `PB005` catches a manifest and a skill disagreeing with each other; PB010/PB011 catch
    a version that agrees with everything and describes nothing, which is the failure
    nobody notices because no two files contradict. PB012/PB013 read the same diff as a
    reader deciding whether to take the update rather than as its author. None of them
    rewrites anything: the number is the author's claim about their own work, and a tool
    that bumps it on their behalf has made the claim for them.
    """
    prev = (_previous_from_git(skill, spec["ref"]) if spec["kind"] == "git"
            else _previous_from_tree(skill, spec["root"]))
    if prev is None:
        return []
    changed, old_fm = prev
    # Asked apart from PB010/PB011: their early returns turn on whether the number moved
    # at all, and PB013 is about which way it moved.
    out =rollback_finding(old_fm, skill.fm) + reach_findings(skill, spec, changed, old_fm)
    return out + _version_claim(skill, changed, old_fm)


def _version_claim(skill, changed, old_fm):
    """PB010 / PB011 - the content moved, and what the version number did about it."""
    if not changed:
        return []
    old, new = declared_version(old_fm), declared_version(skill.fm)
    if not old and not new:
        return []                        # nothing claims a version; nothing went stale
    surface = surface_changes(old_fm, skill.fm)
    shown = ", ".join(changed[:3]) + (f" and {len(changed) - 3} more" if len(changed) > 3
                                      else "")

    if old and not new:
        return [Finding("PB010", f"{len(changed)} file(s) changed ({shown}) and the "
                                 f"`version: {old}` that was here is gone")]
    if not old:
        return []                        # a version appeared where there was none: a bump
    if old == new:
        tail = (" - and " + "; ".join(surface) + ", which is more than a patch"
                if surface else "")
        return [Finding("PB010", f"{len(changed)} file(s) changed ({shown}) and "
                                 f"`version: {old}` did not move{tail}")]

    # The version moved. The only thing left to judge is whether it moved far enough,
    # and that is only answerable when both numbers parse and the call surface moved.
    if not surface:
        return []
    a, b = SEMVER_RE.match(old), SEMVER_RE.match(new)
    if not a or not b:
        return []                        # unparseable: no opinion rather than a guess
    if a.group(1, 2) == b.group(1, 2):
        return [Finding("PB011", f"`{old}` -> `{new}` is a patch, but " + "; ".join(surface))]
    return []


# ---- the README as payload: what a stranger is told to type -------------------------

# `owner/repo` out of a remote URL in any of the spellings git prints: https, scp-style
# `git@github.com:o/r`, and `ssh://...ssh.github.com:443/o/r` for a remote on port 443.
REMOTE_REPO_RE = re.compile(r"github\.com(?::\d+)?[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
# Unnamed on purpose: the pair repeats once per spelling, and a group name cannot. The
# owner may not start with a dot, which keeps `./local-path` out of it.
_OR = r"([\w-][\w.-]*)/([\w.-]+)"
INSTALL_REPO_RE = re.compile(
    r"npx\s+(?:-y\s+)?skills(?:@\S+)?\s+add\s+(?:https?://github\.com/)?" + _OR
    + r"|/plugin\s+marketplace\s+add\s+(?:https?://github\.com/)?" + _OR
    + r"|git\s+clone\s+(?:-\S+\s+)*(?:https?://github\.com/|git@github\.com:)" + _OR
    + r"|raw\.githubusercontent\.com/" + _OR)
PLUGIN_INSTALL_RE = re.compile(r"/plugin\s+install\s+(?P<plugin>[\w.-]+)@(?P<market>[\w.-]+)")


def enclosing_marketplace(skill):
    """(marketplace name, its plugin entries) for the catalogue this skill ships in.

    Walked up from the skill rather than read beside it: a marketplace lists plugins
    under `plugins/<name>/`, so the catalogue sits two or three levels above the skill.
    """
    here = skill.root
    for _ in range(5):
        data = _load_json(os.path.join(here, ".claude-plugin", "marketplace.json"))
        if isinstance(data, dict) and isinstance(data.get("plugins"), list):
            return data.get("name"), [p for p in data["plugins"] if isinstance(p, dict)]
        up = os.path.dirname(here)
        if up == here:
            break
        here = up
    return None, []


def known_repos(skill, entries):
    """{repo name: {owners}} this skill is known to live under, lowercased.

    Every remote counts, not only `origin`: a fork with an `upstream` remote telling
    people to install from upstream is doing the right thing. Marketplace entries count
    too, because a README pointing at a sibling plugin under its old owner is the same
    defect one entry over.
    """
    urls = []
    ok, out = _git(skill.root, "remote", "-v")
    if ok:
        urls += [ln.split()[1] for ln in out.splitlines() if len(ln.split()) > 1]
    for entry in entries:
        src = entry.get("source")
        if isinstance(src, dict):
            if src.get("repo"):
                urls.append("github.com/" + str(src["repo"]))
            elif src.get("url"):
                urls.append(str(src["url"]))
    known = {}
    for url in urls:
        m = REMOTE_REPO_RE.search(url.strip())
        if m:
            known.setdefault(m.group(2).lower(), set()).add(m.group(1).lower())
    return known


# What a repository carries for its maintainers and not for the agent. Beside a SKILL.md at
# the repository root, all of it is inside the skill's folder, and that folder is what an
# installer copies.
NOT_PAYLOAD = ("tests", "test", "fixtures", "docs", "examples", "benchmarks", ".github")


def payload_findings(skill):
    """PB015 - SKILL.md at the root of its repository, beside the repository's own material.

    `npx skills add` copies a skill's folder, and when that folder is the repository root
    it copies the test corpus, the documentation site and CI with it (the installer's own
    README: a SKILL.md at the root shadows anything nested below it). Watched on this
    project: two marketplace scanners failed it on a fixture of a malicious skill and on
    the assembly of a fake token in its test runner - material the agent never loads and
    a user never needed. `.sqsignore` hides such a directory from this suite, not from
    anybody else's scanner, so it does not silence this.
    """
    ok, top = _git(skill.root, "rev-parse", "--show-toplevel")
    if not ok or not top.strip():
        return []
    try:
        if not os.path.samefile(top.strip(), skill.root):
            return []
    except OSError:
        return []
    carried = [d for d in NOT_PAYLOAD if os.path.isdir(os.path.join(skill.root, d))]
    if not carried:
        return []
    name = skill.name or skill.folder
    return [Finding("PB015", f"SKILL.md is at the repository root beside "
                             f"{', '.join(d + '/' for d in carried)} - an installer copies "
                             f"the whole folder, so these land in every user's skills "
                             f"directory and in every marketplace scanner's view; move the "
                             f"skill into `skills/{name}/`", severity="warning")]


def install_findings(skill):
    """PB014 - an install command whose target disagrees with where this ships from.

    The README is read as payload here rather than checked for existence: it is the file
    that tells a human what to type, and a project that moved while its instructions did
    not sends every new user to an account that is no longer the author's. Whoever takes
    that name next receives the installs.

    Only a disagreement about *this* project counts. A repository name that matches one
    this checkout is known to live under, with a different owner, is a move the README
    missed; a README that installs somebody else's repository is a catalogue doing its
    job, and says nothing either way. The same for a plugin: `/plugin install <this
    plugin>@<marketplace>` naming a marketplace other than the one listing it.
    """
    market, entries = enclosing_marketplace(skill)
    known = known_repos(skill, entries)
    this_plugin = None
    root = plugin_root(skill)
    if root:
        manifest = _load_json(os.path.join(root, ".claude-plugin", "plugin.json"))
        this_plugin = manifest.get("name") if isinstance(manifest, dict) else None
    listed = {e.get("name") for e in entries}

    # A README above the skill's own folder is shared by every skill beside it, and a
    # plugin with eight skills would print the same line eight times. It is reported on
    # the first of them by folder name - deterministic, and it needs no state kept
    # between skills.
    parent = os.path.dirname(skill.root)
    first = min((e for e in os.listdir(parent)
                 if os.path.isfile(os.path.join(parent, e, "SKILL.md"))), default=None)
    readmes = []
    for d in (skill.root, parent, root):
        p = os.path.join(d, "README.md") if d else None
        if not p or not os.path.isfile(p) or os.path.realpath(p) in readmes:
            continue
        if d != skill.root and first is not None and first != skill.folder:
            continue
        readmes.append(os.path.realpath(p))

    out = []
    for path in readmes:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().split("\n")
        except OSError:
            continue
        shown = os.path.relpath(path, os.path.dirname(skill.root)).replace(os.sep, "/")
        for n, line in enumerate(lines, 1):
            for m in INSTALL_REPO_RE.finditer(line):
                owner, repo = next((m.group(i), m.group(i + 1))
                                   for i in range(1, len(m.groups()), 2) if m.group(i))
                repo = repo[:-4] if repo.lower().endswith(".git") else repo
                owners = known.get(repo.lower())
                if owners and owner.lower() not in owners:
                    homes = ", ".join(f"`{o}/{repo}`" for o in sorted(owners))
                    out.append(Finding("PB014", f"{shown}:{n} installs `{owner}/{repo}`, but "
                                                f"the remotes and marketplace here know it "
                                                f"as {homes}"))
            for m in PLUGIN_INSTALL_RE.finditer(line):
                plugin, named = m.group("plugin"), m.group("market")
                if market and plugin == this_plugin and plugin in listed and named != market:
                    out.append(Finding("PB014", f"{shown}:{n} installs `{plugin}@{named}`, but "
                                                f"`{plugin}` is listed in the `{market}` "
                                                f"marketplace"))
    return out


def check(skill, cfg=None):
    cfg = cfg or {}
    lang = cfg.get("lang")
    out = []
    if not skill.ok:
        return out
    parent = os.path.dirname(skill.root)

    # PB001 / PB002 - what a stranger needs before they can use or reuse the skill
    has_license = bool(skill.fm.get("license")) or any(
        os.path.isfile(os.path.join(d, n))
        for d in (skill.root, parent) for n in LICENSE_NAMES)
    if not has_license:
        out.append(Finding("PB001", "no `license:` field and no LICENSE file beside the skill"))
    if not any(os.path.isfile(os.path.join(d, "README.md")) for d in (skill.root, parent)):
        out.append(Finding("PB002", "no README.md - SKILL.md talks to the agent, nothing here "
                                    "talks to the human deciding whether to install"))

    # PB005 - the manifest and the skill disagree about which version this is
    version, mpath = manifest_version(skill)
    own = declared_version(skill.fm)
    if version and own and version != own:
        out.append(Finding("PB005", f"`version: {own}` in SKILL.md, `{version}` in "
                                    f"{os.path.relpath(mpath, parent)}"))

    for rel, text in skill.texts():
        for n, line in enumerate(text.split("\n"), 1):
            # PB003 - the path only resolves on one machine, and names whose
            for m in PERSONAL.finditer(line):
                if m.group(1).lower() not in PERSONAL_GENERIC:
                    out.append(Finding("PB003", f"`{m.group(0)}` - absolute path naming an "
                                                f"account", where=rel, line=n))
                    break
            # PB006 - a pointer into material the reader has no copy of
            m = PRIVATE_PATH.search(line)
            if m:
                # The quotes are stripped through a module-level constant rather than
                # inline: a backslash inside an f-string expression is only legal from
                # Python 3.12, and this file has to parse on the oldest version the
                # suite claims to run on.
                out.append(Finding("PB006", f"`{m.group(0).strip(QUOTES)}` points into "
                                            f"the author's own files", where=rel, line=n))
            m = EMAIL.search(line)
            if m and not EMAIL_GENERIC.search(m.group(0)):
                out.append(Finding("PB006", f"email address `{m.group(0)}`", where=rel, line=n))

        # PB004 - documented in a language the repository is not written in
        rx = SCRIPTS.get(lang)
        if rx:
            hits = rx.findall(text)
            if len(hits) > 20:
                out.append(Finding("PB004", f"{len(hits)} characters outside `{lang}`",
                                   where=rel))

    # PB007 / PB008 / PB009 - the skill arrived inside a plugin: what else is in the
    # package, what it assumes the package provides, and where the package came from
    root = plugin_root(skill)
    if root:
        out += hook_findings(root)
        out += sibling_findings(skill)
        manifest = _load_json(os.path.join(root, ".claude-plugin", "plugin.json"))
        plugin_name = manifest.get("name") if isinstance(manifest, dict) else None
        out += origin_finding(root, plugin_name or skill.name or skill.folder)

    # PB014 - the README tells a stranger to install from somewhere this does not live
    out += install_findings(skill)

    # PB015 - the repository is the skill, so everything in it ships
    out += payload_findings(skill)

    # PB010 - PB013 - opt-in, because a comparison needs a stated "before". `--since`
    # resolves to one in `sqs.py`, which is also where the note about a `--since` that
    # resolved to nothing gets printed: a rule that quietly did not run is the one
    # failure mode a gate cannot afford.
    since = cfg.get("since")
    if since:
        out += version_findings(skill, since)
    return out
