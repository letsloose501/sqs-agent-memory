"""Run browser-harness against the agent Chrome (separate profile, port 9222).

    python bh.py script.py        script from a file (anything long: heredocs break silently)
    python bh.py -c "snap()"      one or two lines
    python bh.py --status         is Chrome alive, harness version, is telemetry off
    python bh.py --stop           close the agent Chrome

Starts Chrome if it is not running and sets the environment: BU_CDP_URL to the agent Chrome
(the user's main browser is never touched), BH_TELEMETRY=0, BH_AGENT_WORKSPACE to the skill's
workspace/ (snap/act/fill live there). Exit code is the harness exit code.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("BRAUZER_PORT", "9222"))
CDP_URL = f"http://127.0.0.1:{PORT}"
PROFILE = Path.home() / ".config" / "browser-harness" / "chrome-profile"
WORKSPACE = Path(__file__).resolve().parent.parent / "workspace"
CHROMES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def version():
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=0.5) as r:
            return json.loads(r.read())
    except OSError:
        return None


def start_chrome():
    exe = next((c for c in CHROMES if Path(c).is_file()), None)
    if not exe:
        sys.exit("browser: chrome.exe / msedge.exe not found")
    PROFILE.mkdir(parents=True, exist_ok=True)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen(
        [exe, f"--remote-debugging-port={PORT}", "--remote-debugging-address=127.0.0.1",
         f"--user-data-dir={PROFILE}", "--no-first-run", "--no-default-browser-check",
         # A narrow window gets the mobile layout (hh.ru at 929 px opened search as a sheet over a modal).
         "--window-size=1440,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    for _ in range(40):
        if version():
            return
        time.sleep(0.25)
    sys.exit(f"browser: Chrome did not answer on {CDP_URL} within 10 s")


def harness():
    exe = shutil.which("browser-harness")
    if not exe:
        sys.exit("browser: browser-harness is not installed, see references/setup.md")
    return exe


def env():
    e = dict(os.environ)
    # BH_TAB_MARKER=0: otherwise the harness appends a horse emoji to the tab title and it leaks into snapshots.
    e.update(BU_CDP_URL=CDP_URL, BH_TELEMETRY="0", BH_AGENT_WORKSPACE=str(WORKSPACE), BH_TAB_MARKER="0",
             PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return e


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--status":
        v = version()
        print(f"chrome: {v['Browser'] if v else 'not running'} ({CDP_URL}, profile {PROFILE})")
        out = subprocess.run([harness(), "--version"], capture_output=True, text=True, env=env())
        print(f"browser-harness: {out.stdout.strip() or out.stderr.strip()}")
        tel = subprocess.run([harness(), "telemetry", "status"], capture_output=True, text=True, env=env())
        try:
            t = json.loads(tel.stdout)
            print(f"telemetry: {'ENABLED' if not t['disabled_by_config'] else 'disabled in config'}")
        except (ValueError, KeyError):
            print(f"telemetry: could not parse {tel.stdout!r}")
        return 0 if v else 1
    if argv[0] == "--stop":
        v = version()
        if not v:
            print("chrome: not running")
            return 0
        ws = v["webSocketDebuggerUrl"]
        # Browser.close through the harness: it already speaks the websocket.
        subprocess.run([harness()], input=b"cdp('Browser.close')", env=env())
        time.sleep(1)
        print("chrome: closed" if not version() else f"chrome: still answering ({ws})")
        return 0
    if argv[0] == "-c":
        code = " ".join(argv[1:])
    else:
        code = Path(argv[0]).read_text(encoding="utf-8")
    if not version():
        start_chrome()
    return subprocess.run([harness()], input=code.encode("utf-8"), env=env()).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
