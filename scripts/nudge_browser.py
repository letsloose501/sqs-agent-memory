"""PostToolUse / PostToolUseFailure hook: a failed page fetch leads to the `browser` skill.

Why a hook. "WebFetch could not open the page: use the browser skill" is easy to write into a
rule file and easy to forget at the moment it matters, because the rule is passive. Two ways it
gets forgotten in practice: a browser extension disconnects and the agent says "can't", although
a separate scripted browser is available; WebFetch returns an empty JavaScript shell and the
agent falls back to a web search summary instead of the page itself.

What it does. It blocks nothing (the tool already ran). It puts a reminder right next to the
result, where the agent is looking at that moment:
  * WebFetch failed (403, 521, certificate, timeout)                      -> always remind;
  * WebFetch "succeeded" but returned an empty page, a Cloudflare stub, a
    CAPTCHA, "enable JavaScript", a refusal to reproduce text verbatim    -> remind;
  * a call of Claude in Chrome or of the built-in browser failed           -> name the browser
    skill as another route.

What it physically cannot see: a page that opened but is the wrong one (a redirect to the home
page, a regional version); a refusal worded in a way SIGNALS does not match. Every firing is
logged to browser-nudge.tsv in the plugin's data folder, so a nudge that was not needed can be
found and the pattern tightened. NUDGE_BROWSER_NOLOG=1 turns the log off (tests).

Input: the hook JSON on stdin. Output: exit 0 and a JSON with additionalContext, or nothing.
"""
from __future__ import annotations

import json
import os
import re
import time

from _common import plugin_data, read_payload, utf8_stdio

# Signs that the page did not arrive, matched against WebFetch's answer.
SIGNALS = [
    (r"content (you provided |of the page )?(is|was|appears to be) empty", "empty page"),
    (r"page (is|was|appears) (empty|blank)|no (readable |visible )?content", "empty page"),
    (r"enable javascript|javascript is (required|disabled)|requires javascript", "JavaScript shell"),
    (r"just a moment|checking your browser|cf-chl|attention required", "Cloudflare stub"),
    (r"captcha|are you a robot|not a robot|verify you are human", "CAPTCHA"),
    (r"\b403\b|forbidden|access denied", "403 / access denied"),
    (r"\b(429|451|521|522|523|525|526)\b", "HTTP error"),
    (r"certificate|ssl error|\btls\b", "certificate error"),
    (r"(can(no|')t|unable to|couldn'?t) (access|fetch|retrieve|load|reach)", "did not load"),
    (r"(can(no|')t|unable to|won'?t) (provide|reproduce|share).{0,40}(verbatim|word.for.word|full text|lyrics)",
     "verbatim refusal"),
]
# A long, substantive answer about 403s or CAPTCHAs (an article on them) must not fire:
# signals count only in a short answer, except plain emptiness.
SHORT = 2500
ALWAYS = {"empty page", "JavaScript shell", "Cloudflare stub"}

BROWSER_TOOL = re.compile(r"^mcp__(claude-in-chrome|Claude_Browser)__")

FETCH_HINT = """WebFetch did not get the page ({why}): {url}

Do not drop the source and do not replace it with a web search summary. Invoke the `browser`
skill now and read this page there (its own Chrome profile; it gets past many 403s and renders
JavaScript). Only if the browser also fails: say "did not get the page" and name what was read
instead."""

BROWSER_HINT = """A browser call failed ({tool}): {err}

That is one route, not "impossible". The `browser` skill runs a separate Chrome with its own
profile and does not depend on the browser extension or the app's browser pane. Before saying
"can't", try it (Skill `browser`)."""


def log(kind: str, why: str, target: str) -> None:
    if os.environ.get("NUDGE_BROWSER_NOLOG"):
        return
    try:
        with (plugin_data() / "browser-nudge.tsv").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{kind}\t{why}\t{target[:200]}\n")
    except OSError:
        pass


def emit(event: str, text: str) -> int:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
    return 0


def signal_in(text: str) -> str | None:
    low = text.lower()
    for pattern, why in SIGNALS:
        if re.search(pattern, low) and (why in ALWAYS or len(text) <= SHORT):
            return why
    return None


def main() -> int:
    utf8_stdio()
    p = read_payload()
    event = p.get("hook_event_name", "PostToolUse")
    tool = p.get("tool_name", "")
    inp = p.get("tool_input") or {}

    if tool == "WebFetch":
        url = str(inp.get("url", ""))
        if event == "PostToolUseFailure":
            err = str(p.get("error", ""))
            # localhost and redirects are not the browser's case: another tool or another URL.
            if re.search(r"localhost|hostname without a dot|redirect", err, re.I):
                return 0
            why = signal_in(err) or "fetch error"
        else:
            resp = p.get("tool_response", "")
            text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
            why = signal_in(text)
            if not why:
                return 0
        log("fetch", why, url)
        return emit(event, FETCH_HINT.format(why=why, url=url))

    if BROWSER_TOOL.match(tool) and event == "PostToolUseFailure":
        err = str(p.get("error", ""))[:300]
        log("browser", tool, err)
        return emit(event, BROWSER_HINT.format(tool=tool, err=err))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
