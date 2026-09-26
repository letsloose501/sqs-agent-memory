"""Self-test of the skill helpers on a local form. Run after updating browser-harness and after
editing workspace/. Exit code: 0 all green, 1 failures.

The form is served by a local HTTP server on a free port, not file://: Chrome does not let a
file:// page call fetch, and sniff/fetch_json could not be tested otherwise."""
import functools
import http.server
import os
import subprocess
import sys
import threading
from pathlib import Path

root = Path(__file__).resolve().parent.parent
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root / "tests"))
handler.log_message = lambda *a, **k: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    os.environ["BRAUZER_FORM_URL"] = f"http://127.0.0.1:{srv.server_address[1]}/form.html"
    code = subprocess.run([sys.executable, str(root / "scripts" / "bh.py"),
                           str(root / "tests" / "selftest_page.py")]).returncode
finally:
    srv.shutdown()
sys.exit(code)
