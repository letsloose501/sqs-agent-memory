#!/usr/bin/env python3
"""The compatibility engine: features in, per-harness verdicts out.

It knows nothing about any particular harness. It walks the normalized model, asks
each selected adapter what it makes of each feature, collects the adapter's own hard
rules, and aggregates. Adding a harness therefore changes nothing here - which is the
only test that tells you the split was real.

The headline for a harness is the most actionable thing found, not the worst-sounding:

    ✗ Incompatible          something the harness documents as invalid
    ⚠ Adaptation required   a mechanical change, or a feature that only lives elsewhere
    ? Unknown               the documentation does not say, and nothing else was found
    ✓ Compatible            every feature is documented as read

`UNKNOWN` never becomes `Incompatible`. A gap in somebody's documentation is a gap in
the documentation, and printing it as an incompatibility would be inventing one.
"""
from core import Finding
from harnesses.base import (ADAPTABLE, HARNESS_SPECIFIC, INVALID, PORTABLE, UNKNOWN)

COMPATIBLE = "Compatible"
ADAPTATION = "Adaptation required"
INCOMPATIBLE = "Incompatible"
UNRESOLVED = "Unknown"

MARK = {COMPATIBLE: "✓", ADAPTATION: "⚠", UNRESOLVED: "?", INCOMPATIBLE: "✗"}
CODE = {INVALID: "CP008", HARNESS_SPECIFIC: "CP006", ADAPTABLE: "CP006", UNKNOWN: "CP007"}
SEVERITY = {INVALID: "error", HARNESS_SPECIFIC: "warning", ADAPTABLE: "info",
            UNKNOWN: "info"}


class HarnessResult:
    __slots__ = ("adapter", "rows", "checks", "verdict")

    def __init__(self, adapter, rows, checks):
        self.adapter = adapter
        self.rows = rows            # [(Feature, Verdict)]
        self.checks = checks        # [(status, message, recommendation)]
        self.verdict = self._verdict()

    def _verdict(self):
        seen = {v.status for _, v in self.rows} | {s for s, _, _ in self.checks}
        if INVALID in seen:
            return INCOMPATIBLE
        if seen & {ADAPTABLE, HARNESS_SPECIFIC}:
            return ADAPTATION
        if UNKNOWN in seen:
            return UNRESOLVED
        return COMPATIBLE

    def problems(self, skip_supported=False):
        """What to print under the verdict, worst first, deduplicated by reason."""
        out, seen = [], set()
        for status, msg, rec in self.checks:
            if msg not in seen:
                seen.add(msg)
                out.append((status, msg, rec))
        rank = {INVALID: 0, HARNESS_SPECIFIC: 1, ADAPTABLE: 2, UNKNOWN: 3}
        rows = sorted((r for r in self.rows
                       if r[1].status != PORTABLE and not (skip_supported and r[1].supported)),
                      key=lambda r: rank.get(r[1].status, 9))
        for feature, v in rows:
            msg = f"{feature.label()} - {v.reason}"
            if msg in seen:
                continue
            seen.add(msg)
            out.append((v.status, msg, v.recommendation))
        return out


def analyse(model, adapters, world):
    """One HarnessResult per adapter."""
    features = model.unique()
    out = []
    for adapter in adapters:
        rows = [(f, adapter.classify(f, world)) for f in features]
        out.append(HarnessResult(adapter, rows, adapter.validate_skill(model)))
    return out


def shares(results):
    """How the judgements fall across the five statuses, as fractions.

    The adapters' own rule checks are counted alongside the per-feature verdicts. Left
    out, a skill that one harness refuses outright still reported "100% portable",
    because refusing a missing `name` is not a verdict about any feature.
    """
    counts = {}
    total = 0
    for r in results:
        for status in [v.status for _, v in r.rows] + [s for s, _, _ in r.checks]:
            counts[status] = counts.get(status, 0) + 1
            total += 1
    return {k: v / total for k, v in counts.items()} if total else {}


def findings(model, adapters, world):
    """The engine's output as ordinary findings, so `check --strict` can fail on it.

    With a single target, a feature that harness supports on its own terms is not a
    problem: there is nowhere for it to fail to travel to. The report view still shows
    it, because there the question being asked is different.
    """
    out = []
    single = len(adapters) == 1
    for r in analyse(model, adapters, world):
        for status, msg, rec in r.problems(skip_supported=single):
            code = CODE.get(status)
            if not code:
                continue
            text = f"{r.adapter.title}: {msg}"
            if rec:
                text += f" -> {rec}"
            out.append(Finding(code, text, severity=SEVERITY[status], where="SKILL.md"))
    return out


# ---- reporting ------------------------------------------------------------

LABEL = {PORTABLE: "Portable", ADAPTABLE: "Adaptable",
         HARNESS_SPECIFIC: "Harness-specific", INVALID: "Invalid", UNKNOWN: "Unknown"}
SHARE_ORDER = [PORTABLE, ADAPTABLE, HARNESS_SPECIFIC, UNKNOWN, INVALID]


def report_text(model, results, verbose=True):
    lines = ["AI Skill Compatibility", "", f"Skill: {model.folder}", ""]
    width = max((len(r.adapter.title) for r in results), default=10) + 2
    for r in results:
        lines.append(f"  {r.adapter.title:<{width}}{MARK[r.verdict]} {r.verdict}")

    issues = sum(1 for r in results for s, _, _ in r.problems() if s == INVALID)
    warns = sum(1 for r in results for s, _, _ in r.problems()
                if s in (HARNESS_SPECIFIC, ADAPTABLE))
    unknowns = sum(1 for r in results for s, _, _ in r.problems() if s == UNKNOWN)
    lines += ["", f"  Issues:   {issues}", f"  Warnings: {warns}", f"  Unknown:  {unknowns}"]

    sh = shares(results)
    if sh:
        lines += ["", "  Portability:"]
        for status in SHARE_ORDER:
            if sh.get(status):
                lines.append(f"    {LABEL[status] + ':':<19}{sh[status]:.0%}")

    if verbose:
        for r in results:
            problems = r.problems()
            if not problems:
                continue
            seen = f", checked {r.adapter.checked}" if r.adapter.checked else ", never checked"
            lines += ["", f"{MARK[r.verdict]} {r.adapter.title}  ({r.adapter.docs}{seen})"]
            for status, msg, rec in problems:
                lines.append(f"    [{LABEL[status]}] {msg}")
                if rec:
                    lines.append(f"        -> {rec}")
    return "\n".join(lines)


def report_json(model, results):
    return {
        "skill": model.folder,
        "harnesses": [
            {
                "name": r.adapter.name,
                "title": r.adapter.title,
                "verdict": r.verdict,
                "docs": r.adapter.docs,
                "checked": r.adapter.checked,
                "problems": [{"status": s, "reason": m, "recommendation": rec}
                             for s, m, rec in r.problems()],
            }
            for r in results
        ],
        "portability": {LABEL[k]: round(v, 4) for k, v in shares(results).items()},
    }
