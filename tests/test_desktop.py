"""Tests for skills/desktop/scripts/ad.py without a desktop: agent-desktop is replaced by a fake.

    uv run --no-project tests/test_desktop.py

What must hold: a write into a field that already holds text is refused before anything is
sent; bare refs expand to the last snapshot; the change report shows what changed and only that.
Exit 0: all passed. Exit 1: something failed (listed).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILED: list[str] = []

spec = importlib.util.spec_from_file_location("ad", ROOT / "skills" / "desktop" / "scripts" / "ad.py")
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)


def expect(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if not ok and detail else ""))
    if not ok:
        FAILED.append(name)


def node(ref, role, name, value="", states=(), children=()):
    n = {"role": role, "name": name, "children": list(children)}
    if ref:
        n["ref_id"] = f"@sOLD:{ref}"
    if value:
        n["value"] = value
    if states:
        n["states"] = list(states)
    return n


def tree(display: str, editor: str = "") -> dict:
    return node(None, "window", "Calc", children=[
        node("e1", "textfield", "Editor", editor),
        node(None, "group", "", children=[node("e2", "statictext", f"Display {display}")]),
        node("e3", "button", "Seven"),
        node("e4", "button", "Seven"),  # twin: counted twice, not once
    ])


class Fake:
    """Stands in for ad.call: records commands, answers snapshots from a queue of trees."""

    def __init__(self, trees):
        self.trees, self.calls = list(trees), []

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "snapshot":
            t = self.trees.pop(0) if len(self.trees) > 1 else self.trees[0]
            return {"ok": True, "data": {"snapshot_id": f"s{len(self.calls)}", "ref_count": 4, "tree": t}}
        return {"ok": True, "data": {"disposition": {"delivery": "delivered_unverified"}}}


def run(fn, argv, fake):
    ad.call = fake
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fn(argv)
    return code, out.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["AGENT_DESKTOP_SESSION"] = "test"
        ad.tempfile.tempdir = tmp
        os.environ["AD_SETTLE_S"] = "0"

        rows = ad.rows(tree("0", "doc"))
        expect("rows keep only nodes with refs, in order", [r["ref"] for r in rows] == ["e1", "e2", "e3", "e4"])

        expect("bare ref expands to the last snapshot", ad.expand(["click", "e12"], "sX") == ["click", "@sX:e12"])
        expect("text that only starts like a ref is left alone",
               ad.expand(["e12x", "--name", "e5 x"], "sX") == ["e12x", "--name", "e5 x"])

        added, removed = ad.diff(ad.rows(tree("0")), ad.rows(tree("7")))
        expect("diff: a changed name is one line out, one line in",
               [r["name"] for r in removed] == ["Display 0"] and [r["name"] for r in added] == ["Display 7"])
        expect("diff: same tree, nothing changed", ad.diff(rows, ad.rows(tree("0", "doc"))) == ([], []))
        twin_gone = ad.rows(tree("0", "doc"))[:-1]
        expect("diff: one of two identical twins gone is reported",
               len(ad.diff(rows, twin_gone)[1]) == 1)

        fake = Fake([tree("0", "my document")])
        code, out = run(ad.cmd_snap, ["--app", "Calc"], fake)
        expect("snap adds -i and --compact", code == 0 and "-i" in fake.calls[0] and "--compact" in fake.calls[0], str(fake.calls))
        expect("snap prints the table", "e1    textfield  'Editor' ='my document'" in out, out)
        code, _ = run(ad.cmd_snap, ["--app", "Calc", "--all"], Fake([tree("0")]))
        expect("snap --all keeps static text (no -i)", "-i" not in ad.load_state()["snap_args"])

        run(ad.cmd_snap, ["--app", "Calc"], Fake([tree("0", "my document")]))
        fake = Fake([tree("0", "my document")])
        code, out = run(ad.cmd_act, ["set-value", "e1", "x"], fake)
        expect("write into a field holding text is refused", code == 2 and "REFUSED" in out, out)
        expect("refusal sends nothing", fake.calls == [], str(fake.calls))

        fake = Fake([tree("0", "x")])
        code, out = run(ad.cmd_act, ["set-value", "e1", "x", "--overwrite"], fake)
        expect("--overwrite lets the write through", code == 0 and fake.calls[0][:2] == ["set-value", "@s1:e1"], str(fake.calls))

        run(ad.cmd_snap, ["--app", "Calc"], Fake([tree("0", "")]))
        fake = Fake([tree("0", "x")])
        code, _ = run(ad.cmd_act, ["set-value", "e1", "x"], fake)
        expect("an empty field is written without --overwrite", code == 0 and fake.calls[0][0] == "set-value")

        run(ad.cmd_snap, ["--app", "Calc"], Fake([tree("0")]))
        code, out = run(ad.cmd_act, ["click", "e3"], Fake([tree("7")]))
        expect("act reports the change", "- statictext  'Display 0'" in out and "+ e2    statictext  'Display 7'" in out, out)
        code, out = run(ad.cmd_act, ["click", "e3"], Fake([tree("7")]))
        expect("act says when nothing changed", "nothing changed" in out, out)

        def closing(args):
            if args[0] == "snapshot":
                return {"ok": False, "error": {"code": "APP_NOT_FOUND", "message": "no such app"}}
            return {"ok": True, "data": {"disposition": {"delivery": "delivered_unverified"}}}
        code, out = run(ad.cmd_act, ["click", "e3"], closing)
        expect("a window gone after the action is reported, not an error", code == 0 and "window is gone" in out, out)
        def broken(args):
            if args[0] == "snapshot":
                return {"ok": False, "error": {"code": "TIMEOUT", "message": "slow"}}
            return {"ok": True, "data": {}}
        code, out = run(ad.cmd_act, ["click", "e3"], broken)
        expect("any other failed re-read is still an error", code == 1 and "could not re-read" in out, out)

        ad.call = lambda args: {"ok": False, "error": {"code": "STALE_REF", "message": "gone",
                                                       "disposition": {"delivery": "unknown", "retry": "unsafe"}}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ad.cmd_act(["click", "e3"])
        expect("an unsafe failure says it may have landed", code == 1 and "may have landed" in out.getvalue(), out.getvalue())

    print("ALL GREEN" if not FAILED else f"{len(FAILED)} FAILED: {', '.join(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
