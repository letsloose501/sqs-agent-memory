#!/usr/bin/env python3
"""What a bundled script CAN do to the machine, described rather than forbidden.

`security` flags a pattern that is dangerous on its own - a piped download, a secret
committed in plain text. This module answers a narrower, calmer question underneath
that one: does a bundled script even have the *ability* to reach the network, spawn a
process, or read the environment - regardless of whether any one line looks dangerous.
A finding here names a capability and stops; the decision belongs to whoever is about
to install the skill, the same discipline `security`'s own docstring states for itself.

Python scripts are read with `ast`, which is exact: an import is an import, not a guess
from a regex. Every other extension falls back to the same kind of command-name regex
`security` already uses for its own patterns, since there is no stdlib parser for them -
`CB001`'s grading says so honestly, rather than claiming the AST half's confidence for
both.

`sqs.py capabilities <skill>` runs this module alone - the "one command, one question"
dispatch every other module already gets from `MODULES`. That plain findings list, read
as an answer instead of a list, is the manifest: nothing here invents a second report
format for the same underlying facts.
"""
import ast
import fnmatch
import re

from core import Finding

SCRIPT_EXT = (".py", ".sh", ".bash", ".ps1", ".js", ".ts", ".rb")

# Root package names whose entire job is talking to the network - importing the
# top-level name is itself the capability, submodule or not.
NETWORK_ROOTS = {
    "socket", "httplib", "ftplib", "smtplib", "telnetlib", "poplib", "imaplib",
    "nntplib", "requests", "httpx", "aiohttp", "urllib3", "websocket", "websockets",
    "paramiko", "grpc", "boto3", "botocore",
}
# Exact dotted paths inside a package that is otherwise network-inert. `urllib` bare, or
# `urllib.parse` (pure string parsing) or `urllib.error` (exception classes only), grant
# nothing on their own - only `urllib.request` makes a connection. Watched `urllib.parse`
# reading as "can reach the network" on this project's own installed skills before this
# split existed, which is exactly the over-broad claim this module promises not to make.
NETWORK_EXACT = {
    "urllib.request", "http.client", "http.server", "xmlrpc.client", "xmlrpc.server",
}
SUBPROCESS_MODULES = {"subprocess", "multiprocessing"}
OS_SUBPROCESS_ATTRS = {
    "system", "popen", "fork", "posix_spawn",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
}
ENV_ATTRS = {"environ", "getenv", "environb"}

# Non-Python scripts have no stdlib parser, so the network signal there is a command
# name instead of an import - the same kind of pattern `security.DANGEROUS` already
# matches on, and CB001's confidence grading reflects that this half is a guess.
NETWORK_CMD_RE = re.compile(
    r"\b(curl|wget|ncat|netcat|ssh|scp|sftp|telnet)\b"
    r"|\bnc\s+-[a-zA-Z]*l\b|\bnc\s+\S+\s+\d+\b"
    r"|\bInvoke-WebRequest\b|\bInvoke-RestMethod\b|\bNew-Object\s+Net\.\w+\b", re.I)


def _root(dotted):
    return dotted.split(".", 1)[0]


# `os` under the names it also answers to: `posix` and `nt` are the modules it re-exports.
OS_MODULES = {"os", "posix", "nt"}
# Modules where reaching an attribute by a name the reader cannot see hides a capability.
# Narrow on purpose: `getattr(args, field)` is ordinary code, `getattr(os, name)` is not.
OPAQUE_BASES = OS_MODULES | SUBPROCESS_MODULES | {"builtins", "importlib", "socket", "pty"}
# Builtins that run code. Reached through `getattr(builtins, ...)` they are the same
# call with the name taken off the page.
CODE_RUNNERS = {"exec", "eval", "__import__"}


def _const_str(node):
    """The string an expression always evaluates to, or None when it depends on data.

    Folds what indirection is usually written with - `'sys' + 'tem'`, an f-string of
    literals, `''.join(['sub', 'process'])`. Anything else is computed at run time, which
    is what `CB005` is about.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _const_str(node.left), _const_str(node.right)
        return a + b if a is not None and b is not None else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            s = _const_str(v.value if isinstance(v, ast.FormattedValue) else v)
            if s is None or (isinstance(v, ast.FormattedValue) and v.format_spec):
                return None
            parts.append(s)
        return "".join(parts)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join" and len(node.args) == 1 and not node.keywords
            and isinstance(node.args[0], (ast.List, ast.Tuple))):
        sep = _const_str(node.func.value)
        items = [_const_str(e) for e in node.args[0].elts]
        if sep is not None and all(i is not None for i in items):
            return sep.join(items)
    return None


def _import_caps(dotted, how):
    """(code, message) for importing `dotted`; `how` says how the import was written."""
    out, root = [], _root(dotted)
    if root in NETWORK_ROOTS or dotted in NETWORK_EXACT:
        out.append(("CB001", f"imports `{dotted}`{how} - can reach the network"))
    if root in SUBPROCESS_MODULES:
        out.append(("CB002", f"imports `{dotted}`{how} - can spawn a process"))
    return out


def _attr_caps(module, attr, how):
    """(code, message) for `module.attr` reached some way other than plain `module.attr`."""
    name = f"{module}.{attr}"
    if _root(module) in OS_MODULES and attr in OS_SUBPROCESS_ATTRS:
        return [("CB002", f"calls `{name}`{how} - can spawn a process")]
    if _root(module) in OS_MODULES and attr in ENV_ATTRS:
        return [("CB003", f"reads `{name}`{how} - can read whatever the environment "
                          f"carries, commonly including API keys and tokens")]
    if module == "builtins" and attr in CODE_RUNNERS:
        return [("CB005", f"reaches `{attr}`{how} - runs code the script builds, so what "
                          f"it can do cannot be read off the file")]
    return _import_caps(module, how) if (_root(module) in SUBPROCESS_MODULES
                                        or _root(module) in NETWORK_ROOTS) else []


def _py_capabilities(text):
    """(code, message, line) from the exact syntax tree - imports and calls, not a guess.

    A script that fails to parse (a newer syntax feature, or a `.py` file that is
    actually something else) is skipped rather than reported on: a capability claim
    from a tree that was never really built would be a guess wearing `ast`'s confidence.

    Indirection is followed as far as the file itself decides it: `__import__('os')`,
    `importlib.import_module(...)`, `getattr(os, 'sys' + 'tem')`, `vars(os)['system']`
    and `exec('import subprocess')` all name their target in constants, so they are read
    as the plain import or call they spell. Where the name or the code is computed at run
    time the capability is unknowable from the file, and that is `CB005` - a finding of
    its own, because an empty manifest would otherwise read as "can do nothing".
    """
    out = []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return out
    # local name -> the module it is bound to, and the names that import by string
    modules, importers = {}, {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    modules[a.asname] = a.name
                else:
                    modules[_root(a.name)] = _root(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            importers |= {a.asname or a.name for a in node.names
                          if a.name in ("import_module", "__import__")}

    def dynamic_import(call):
        if not isinstance(call, ast.Call) or not call.args:
            return False
        f = call.func
        return (((isinstance(f, ast.Name) and f.id in importers)
                     or (isinstance(f, ast.Attribute)
                         and f.attr in ("import_module", "__import__"))))

    def module_of(node):
        """The module an expression is, when the file says which."""
        if isinstance(node, ast.Name):
            return modules.get(node.id) or (node.id if node.id in OS_MODULES else None)
        if dynamic_import(node):
            name = _const_str(node.args[0])
            if name is None:
                return None
            # `__import__('a.b')` hands back the package `a`; `import_module` hands back `a.b`
            spelled = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            return _root(name) if spelled == "__import__" else name
        return None

    def reach(base, key, line, how):
        """`base.<key>` reached by `getattr`, `vars(...)[...]` or `.__dict__[...]`."""
        module = module_of(base)
        if module is None:
            return
        name = _const_str(key)
        if name is not None:
            out.extend((c, m, line) for c, m in _attr_caps(module, name, how))
        elif _root(module) in OPAQUE_BASES:
            out.append(("CB005", f"reaches into `{module}` by a name computed at run time "
                                 f"- what it calls cannot be read off the file", line))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.extend((c, m, node.lineno) for c, m in _import_caps(alias.name, ""))
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = _root(node.module)
            # `from urllib import request` names the network-capable submodule as one
            # of the imported names rather than in `module` - build the same dotted
            # path `import urllib.request` would produce, for each name, before
            # checking it against `NETWORK_EXACT`.
            dotted = {f"{node.module}.{a.name}" for a in node.names}
            if root in NETWORK_ROOTS or node.module in NETWORK_EXACT or dotted & NETWORK_EXACT:
                out.append(("CB001", f"imports from `{node.module}` - can reach the network",
                           node.lineno))
            if root in SUBPROCESS_MODULES:
                out.append(("CB002", f"imports from `{node.module}` - can spawn a process",
                           node.lineno))
            # `from os import system` is `os.system` without the `os.` a reader looks for
            if root in OS_MODULES:
                for a in node.names:
                    out.extend((c, m, node.lineno)
                               for c, m in _attr_caps(node.module, a.name, " by name"))
        elif isinstance(node, ast.Attribute):
            module = module_of(node.value)
            if module is None:
                continue
            if isinstance(node.value, ast.Call):             # __import__('os').system
                out.extend((c, m, node.lineno)
                           for c, m in _attr_caps(module, node.attr, " at run time"))
            elif _root(module) in OS_MODULES:
                if node.attr in OS_SUBPROCESS_ATTRS:
                    out.append(("CB002", f"calls `os.{node.attr}` - can spawn a process",
                               node.lineno))
                elif node.attr in ENV_ATTRS:
                    out.append(("CB003", f"reads `os.{node.attr}` - can read whatever the "
                                         f"environment carries, commonly including API "
                                         f"keys and tokens", node.lineno))
        elif isinstance(node, ast.Subscript):
            v, key = node.value, node.slice
            if isinstance(key, getattr(ast, "Index", ())):            # Python 3.8
                key = key.value
            if (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                    and v.func.id == "vars" and len(v.args) == 1):
                reach(v.args[0], key, node.lineno, " through `vars()`")
            elif isinstance(v, ast.Attribute) and v.attr == "__dict__":
                reach(v.value, key, node.lineno, " through `__dict__`")
        elif isinstance(node, ast.Call):
            f = node.func
            if dynamic_import(node):
                name = _const_str(node.args[0])
                if name is None:
                    out.append(("CB005", "imports a module whose name is computed at run "
                                         "time - what it can do cannot be read off the "
                                         "file", node.lineno))
                else:
                    out.extend((c, m, node.lineno)
                               for c, m in _import_caps(name, " at run time"))
            elif (isinstance(f, ast.Name) and f.id == "getattr" and len(node.args) >= 2):
                reach(node.args[0], node.args[1], node.lineno, " through `getattr`")
            elif isinstance(f, ast.Name) and f.id in ("exec", "eval") and node.args:
                code = _const_str(node.args[0])
                if code is None:
                    out.append(("CB005", f"`{f.id}` runs code assembled at run time - "
                                         f"what it can do cannot be read off the file",
                               node.lineno))
                else:
                    out.extend((c, m, node.lineno) for c, m, _ in _py_capabilities(code))
    return out


def _other_capabilities(text):
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        m = NETWORK_CMD_RE.search(line)
        if m:
            out.append(("CB001", f"runs `{m.group(0).strip()}` - can reach the network", n))
    return out


# The import name and the name it is installed under, where the two differ - a skill that
# says "pip install pymupdf" has declared what `import fitz` needs.
PIP_NAMES = {
    "PIL": "pillow", "fitz": "pymupdf", "yaml": "pyyaml", "docx": "python-docx",
    "pptx": "python-pptx", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "dotenv": "python-dotenv",
    "win32api": "pywin32", "win32com": "pywin32", "win32con": "pywin32",
    "Crypto": "pycryptodome", "jwt": "pyjwt", "serial": "pyserial",
    "magic": "python-magic", "OpenSSL": "pyopenssl", "attr": "attrs",
}
PEP723_RE = re.compile(r"^# /// script\s*$(.*?)^# ///\s*$", re.M | re.S)
_IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _catches_import_error(handler):
    t = handler.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    return any(isinstance(n, ast.Name) and n.id in _IMPORT_ERRORS for n in names)


def _required_imports(tree):
    """{root name: first line} - absolute imports the script cannot run without.

    An import inside `try:` whose handler catches `ImportError` is optional by the script's
    own say-so, and one under `if TYPE_CHECKING:` never runs; neither is a requirement.
    """
    found = {}

    def visit(node, optional):
        if isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
            guarded = optional or any(_catches_import_error(h) for h in node.handlers)
            for child in node.body:
                visit(child, guarded)
            for child in node.handlers + node.orelse + node.finalbody:
                visit(child, optional)
            return
        if isinstance(node, ast.If):
            t = node.test
            if ((isinstance(t, ast.Name) and t.id == "TYPE_CHECKING")
                    or (isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING")):
                for child in node.orelse:
                    visit(child, optional)
                return
        if not optional:
            if isinstance(node, ast.Import):
                for a in node.names:
                    found.setdefault(_root(a.name), node.lineno)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.setdefault(_root(node.module), node.lineno)
        for child in ast.iter_child_nodes(node):
            visit(child, optional)

    visit(tree, False)
    return found


# Files whose whole job is to list what a project needs: every name in them is a
# declaration. Matched on the file name, not the extension - a `.yaml` trigger set or a
# `.txt` note is prose.
MANIFEST_RE = re.compile(r"(?:^|/)(?:requirements[\w.-]*\.(?:txt|in)|constraints[\w.-]*\.txt"
                         r"|pyproject\.toml|setup\.cfg|Pipfile|environment\.ya?ml)$", re.I)
PROSE_EXT = (".md", ".markdown", ".txt", ".rst")
# Directories that hold an installation, not the skill's own code.
ENV_DIRS = {"site-packages", "dist-packages", "node_modules", "__pycache__", "venv", "env"}
# A line that says how to get a package, or shows it being imported.
REQUIREMENT_LINE_RE = re.compile(
    r"\b(?:pip3?|pipx|uv\s+pip|python3?\s+-m\s+pip|poetry|conda|mamba)\s+(?:install|add)\b"
    r"|\buv\s+add\b|--with(?:-requirements)?\b|^\s*(?:import|from)\s+[A-Za-z_]", re.M)


def _requirement_lines(text):
    """The lines of a prose file that tell the reader a package is needed.

    In prose a package name is a word like any other, and the words collide: `yaml` is also
    the format of every frontmatter, `docx` of every Word file, `requests` of every English
    sentence about asking. Measured on the real skills here, all three were read as
    declarations and none was one - `yaml` even inside a code block, where it labelled a
    directory tree. The collision is in the word, not in where it sits, so only a line that
    installs the package or imports it counts: `pip install pymupdf` does, "counted by
    SymPy" does not.
    """
    return "\n".join(line for line in text.split("\n") if REQUIREMENT_LINE_RE.search(line))


def _undeclared(skill, scripts):
    """CB006 - a package a bundled script cannot run without, named nowhere in the skill.

    Named means: anywhere in a manifest (`requirements.txt`, `pyproject.toml` and kin), in
    the frontmatter's `compatibility` - the specification's own place for environment
    requirements - or in the script's inline PEP 723 block; and in prose only on a line
    that installs or imports it. Under its import name or the name it installs as. The
    finding is for the skill that never says, where the agent meets the missing package
    as a traceback halfway through the task.

    What is local is read off the disk, not off `skill.walk()`: a module `.sqsignore`
    hides from the checks is still a file the import finds. An environment is not local,
    though - a `.venv` inside the skill folder with the package installed is how it works
    on the author's machine and exactly what the next machine does not have (watched: a
    real skill's own `.venv` held `sympy`, and the finding went silent).
    """
    import os                                                      # noqa: PLC0415
    from stdlib_modules import STDLIB                              # noqa: PLC0415
    local, declared = set(), [str(skill.fm.get("compatibility", ""))]
    for dirpath, dirnames, files in os.walk(skill.root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in ENV_DIRS
                       and not os.path.isfile(os.path.join(dirpath, d, "pyvenv.cfg"))]
        local |= set(dirnames)
        local |= {f[:-3] for f in files if f.endswith(".py")}
    for rel, size, _ in skill.walk():
        rel = rel.replace("\\", "/")
        if rel.endswith(".py"):
            continue
        manifest = MANIFEST_RE.search(rel)
        if size > 2_000_000 or not (manifest or rel.lower().endswith(PROSE_EXT)):
            continue
        try:
            with open(f"{skill.root}/{rel}", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        declared.append(text if manifest else _requirement_lines(text))
    prose = "\n".join(declared).lower()
    out = []
    for rel, text in scripts:
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        own = "\n".join(m.group(1) for m in PEP723_RE.finditer(text)).lower()
        missing = []
        for name, line in sorted(_required_imports(tree).items(), key=lambda kv: kv[1]):
            if name in STDLIB or name in local or name == "__future__":
                continue
            spelled = {name.lower(), PIP_NAMES.get(name, name).lower()}
            if any(re.search(r"(?<![\w.-])" + re.escape(s) + r"(?![\w-])", prose + own)
                   for s in spelled):
                continue
            missing.append((name, line))
        if missing:
            names = ", ".join(f"`{n}`" + (f" ({PIP_NAMES[n]})" if n in PIP_NAMES else "")
                              for n, _ in missing)
            out.append(Finding("CB006", f"imports {names} - nothing in the skill names "
                                        f"{'it' if len(missing) == 1 else 'them'}, so the "
                                        f"script fails wherever "
                                        f"{'it is' if len(missing) == 1 else 'they are'} "
                                        f"not installed", where=rel, line=missing[0][1]))
    return out


def check(skill, cfg=None):
    out = []
    if not skill.ok:
        return out
    python = []
    for rel, size, _ in sorted(skill.walk()):
        if not rel.lower().endswith(SCRIPT_EXT) or size > 2_000_000:
            continue
        try:
            with open(f"{skill.root}/{rel}", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if rel.lower().endswith(".py"):
            python.append((rel, text))
        found = (_py_capabilities(text) if rel.lower().endswith(".py")
                else _other_capabilities(text))
        seen = set()
        for code, msg, line in found:
            # One line of each distinct capability per file: a script that imports
            # `requests` in three places has one capability, not three findings.
            if (code, msg) in seen:
                continue
            seen.add((code, msg))
            out.append(Finding(code, msg, where=rel, line=line))   # registry default
    out += _undeclared(skill, python)
    out += load_time_commands(skill)
    return out


# Claude Code runs `!`command`` in a skill's body, and every line of a block opened with
# ```!, before the model is sent the skill - the output replaces the placeholder, and the
# command never prompts: a permission rule or the skill's own `allowed-tools` lets it
# through, or the invocation aborts. Documented on the Claude Code skills page, which
# also states the inline form counts only at a line start or after whitespace.
INJECT_INLINE_RE = re.compile(r"(?:^|(?<=\s))!`([^`\n]+)`")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(!?)")


def _injections(skill):
    """[(line number, command, inside an ordinary code block)] from SKILL.md's body.

    An ordinary fence does not stop an injection. The documentation does not say either
    way, so it was watched: a probe skill with `!`echo RAN_FENCED`` inside a plain code
    block came back to the model as `RAN_FENCED` (Claude Code 2.1.280, 23.09.2026). The
    fence is still recorded, because a command that sits in a code block reads as an
    example to the author who put it there - which is exactly how a guide to the syntax
    ends up running its own examples on load.
    """
    lines = skill.text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    out, fence, runs = [], None, False
    for i in range(start, len(lines)):
        line = lines[i]
        m = FENCE_RE.match(line)
        if m and fence is None:
            fence, runs = m.group(1)[0], bool(m.group(2))
            continue
        if m and fence is not None and m.group(1)[0] == fence and not m.group(2):
            fence, runs = None, False
            continue
        if runs:
            if line.strip():
                out.append((i + 1, line.strip(), False))
            continue
        for mm in INJECT_INLINE_RE.finditer(line):
            out.append((i + 1, mm.group(1).strip(), fence is not None))
    return out


def _preapproved(command, raw_tools):
    """Whether the skill's own `allowed-tools` lets this command through unasked."""
    from model import parse_tools                     # local: model is heavier than this
    scopes = parse_tools(raw_tools).get("Bash")
    if scopes is None:
        return False
    if not scopes:
        return True                                   # bare `Bash`: every command
    return any(fnmatch.fnmatchcase(command, s) for s in scopes)


def load_time_commands(skill):
    """CB004 - commands the skill runs on the machine the moment it loads.

    One finding per skill, not per command: a skill that documents the syntax carries
    dozens of examples, and a list of them is the report `CB001` once was per import site.
    The count that matters most is the one the skill pre-approved for itself - those run
    silently on every load, before anything has been read.
    """
    found = _injections(skill)
    if not found:
        return []
    raw = skill.fm.get("allowed-tools") or ""
    fenced = sum(1 for f in found if f[2])
    approved = sum(1 for _, c, _ in found if _preapproved(c, raw))
    line, cmd, _ = found[0]
    parts = [f"{len(found)} command(s) run when the skill loads, before the model reads "
             f"it, without asking - first `{cmd[:60]}`"]
    if fenced:
        parts.append(f"{fenced} of them sit in ordinary code blocks, which read as examples "
                     f"and run anyway")
    if approved:
        parts.append(f"{approved} pre-approved by its own `allowed-tools`, so nothing stops "
                     f"them")
    if approved < len(found):
        parts.append(f"{len(found) - approved} not pre-approved: unless your own permission "
                     f"rules allow them, loading the skill aborts outside auto mode")
    return [Finding("CB004", "; ".join(parts), severity="info", where="SKILL.md", line=line)]
