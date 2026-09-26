"""Self-check for the headless-Chrome SVG render pipeline (extract_svg.py, vendored AntV).

The idea follows OmniScientist's selfcheck_tools.py: run a known reference through exactly the
same pipeline and check it came out as it must, BEFORE trusting real renders in this session.
Looking at each finished picture catches a wrong PICTURE; this catches a broken TOOL: Chrome not
found or the wrong version, --dump-dom taking the page before the render finished, the vendored
library not loading, extract_svg.py broken. A silently degraded pipeline otherwise passes as
"all fine", the same class of error as a blank browser tab taken for an empty page.

Two levels:
  local   render a local SVG with no external dependencies (checks Chrome itself).
  vendor  render a minimal DSL infographic with the vendored
          vendor/antv-infographic/infographic.min.js (MIT, inside this skill: no network).

Run once at the start of a session before a batch of diagrams, not before each picture; each
picture still has to be looked at.

The file vendor/antv-infographic/infographic.min.js must start with a UTF-8 BOM
(`\\xef\\xbb\\xbf`). Without it Chrome on a non-Latin locale sometimes decodes the local .js
with the wrong encoding (the bundle contains Chinese text) and hits a syntax error out of
nowhere. The BOM forces UTF-8 regardless of locale and of HTTP headers, which file:// lacks anyway.

Example:
    python chrome_selfcheck.py                      # Chrome/Edge found automatically
    python chrome_selfcheck.py --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe"
    python chrome_selfcheck.py --skip-vendor        # only the local level
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_svg import extract_svg  # noqa: E402

VENDOR_LIB = Path(__file__).parent.parent / "vendor" / "antv-infographic" / "infographic.min.js"

LOCAL_MARKER = f"selfcheck-local-{uuid.uuid4().hex[:8]}"
VENDOR_MARKER = f"selfcheck-vendor-{uuid.uuid4().hex[:8]}"


def find_chrome() -> str | None:
    """Chrome or Edge on this machine: PATH first, then the usual install locations."""
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    for cand in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ):
        if Path(cand).is_file():
            return cand
    return None


def render_dump(chrome: str, html_path: Path, dump_path: Path, budget_ms: int) -> None:
    result = subprocess.run(
        [
            chrome, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            f"--virtual-time-budget={budget_ms}",
            "--user-data-dir=" + str(html_path.parent / "chrome-profile"),
            "--dump-dom", html_path.as_uri(),
        ],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"chrome exited with {result.returncode}: {result.stderr[:500]}")
    dump_path.write_text(result.stdout, encoding="utf-8")


def check_local(chrome: str, tmp: Path) -> tuple[bool, str]:
    html = tmp / "local.html"
    html.write_text(
        f'<div id="container"><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        f'<text id="{LOCAL_MARKER}">{LOCAL_MARKER}</text></svg></div>',
        encoding="utf-8",
    )
    dump = tmp / "local_dump.html"
    render_dump(chrome, html, dump, budget_ms=1000)
    try:
        svg = extract_svg(dump.read_text(encoding="utf-8"))
    except ValueError as e:
        return False, f"extract_svg found no <svg>: {e}"
    if LOCAL_MARKER not in svg:
        return False, "marker not found in the extracted SVG: dump-dom returned something other than the render"
    return True, f"ok, {len(svg)} bytes"


def check_vendor(chrome: str, tmp: Path) -> tuple[bool, str]:
    if not VENDOR_LIB.exists():
        return False, f"vendored file not found: {VENDOR_LIB}"
    lib_dir = tmp / "vendor" / "antv-infographic"
    lib_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(VENDOR_LIB, lib_dir / "infographic.min.js")

    html = tmp / "vendor.html"
    dsl = f"infographic list-row-simple-horizontal-arrow\ndata\n  lists\n    - label {VENDOR_MARKER}"
    html.write_text(
        '<div id="container"></div>\n'
        '<script src="vendor/antv-infographic/infographic.min.js"></script>\n'
        "<script>\n"
        "  const ig = new AntVInfographic.Infographic({ container: '#container', width: 400, height: 300 });\n"
        f"  ig.render(`{dsl}`);\n"
        "</script>",
        encoding="utf-8",
    )
    dump = tmp / "vendor_dump.html"
    render_dump(chrome, html, dump, budget_ms=4000)
    text = dump.read_text(encoding="utf-8")
    # Look for the marker ONLY inside the extracted <svg>, not in the raw dump: dump-dom
    # serialises the whole DOM, including the <script> source where the DSL with the marker
    # sits literally, whether or not the script ever ran.
    try:
        svg = extract_svg(text)
    except ValueError:
        return False, "no <svg> in the container: the vendored library did not run (check the BOM in infographic.min.js, see the docstring)"
    if VENDOR_MARKER not in svg:
        return False, "an svg exists but the marker text is not in it: probably a silently degraded template or icons"
    return True, f"ok, {len(svg)} bytes"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chrome", default=None, help="path to Chrome or Edge (default: found automatically)")
    ap.add_argument("--skip-vendor", action="store_true", help="do not check the vendored AntV Infographic")
    args = ap.parse_args()
    args.chrome = args.chrome or find_chrome()
    if not args.chrome:
        print("FAIL: no Chrome or Edge found; pass --chrome", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="chrome_selfcheck_") as tmp_str:
        tmp = Path(tmp_str)
        try:
            ok_local, msg_local = check_local(args.chrome, tmp)
        except (RuntimeError, OSError) as e:
            ok_local, msg_local = False, str(e)
        print(f"{'OK ' if ok_local else 'FAIL'} local:  {msg_local}")

        ok_vendor, msg_vendor = True, "skipped (--skip-vendor)"
        if not args.skip_vendor:
            try:
                ok_vendor, msg_vendor = check_vendor(args.chrome, tmp)
            except (RuntimeError, OSError) as e:
                ok_vendor, msg_vendor = False, str(e)
        print(f"{'OK ' if ok_vendor else 'FAIL'} vendor: {msg_vendor}")

    if not (ok_local and ok_vendor):
        print("\nThe pipeline is broken: do not trust this session's renders until it is fixed.", file=sys.stderr)
        sys.exit(1)
    print("\nThe pipeline is healthy.")


if __name__ == "__main__":
    main()
