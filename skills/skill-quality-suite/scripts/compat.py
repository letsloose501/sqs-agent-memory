#!/usr/bin/env python3
"""Frontmatter against the specification, and the skill against the harnesses.

Two jobs that used to be one table:

- **Spec drift** (CP001, CP002) is harness-independent. The Agent Skills specification
  names a small set of top-level fields and the strict reference validator refuses
  everything else, while real clients warn and load anyway. That split is why a skill
  carrying an extra field works everywhere you would notice and fails at publication.
- **Portability** (CP006, CP007, CP008) is the harness question, and it is answered by
  `portability.py` over the adapters in `harnesses/`. Nothing about any particular
  harness lives in this file any more.
"""
from core import Finding
from harnesses import registry
from model import SkillModel
from portability import findings as portability_findings

# The Agent Skills specification: the only fields a strict validator accepts at the top
# level. Everything else belongs under `metadata:`, the spec's own escape hatch.
SPEC_REQUIRED = {"name", "description"}
# Exactly the specification's frontmatter table. `version` is NOT in it - it belongs
# under `metadata:`, and having it here made CP002 miss a field `skills-ref validate`
# rejects.
SPEC_OPTIONAL = {"license", "compatibility", "metadata", "allowed-tools"}
SPEC_FIELDS = SPEC_REQUIRED | SPEC_OPTIONAL

# Values a field accepts. A field absent here has its value unchecked.
VALUES = {
    "disable-model-invocation": {"true", "false"},
    "user-invocable": {"true", "false"},
    "alwaysApply": {"true", "false"},
}


def harness_names(cfg):
    """The runtimes the skill targets: `harnesses`, or the older `agents` key."""
    return list(cfg.get("harnesses") or cfg.get("agents") or [])


def check(skill, cfg=None, world=None):
    """`cfg['harnesses']` names the environments the skill is meant to run in.

    With none configured only the spec-drift rules run. Claiming a skill fails on Cursor
    when Cursor was never a target would be inventing a problem.
    """
    cfg = cfg or {}
    world = world or registry()
    out = []
    if not skill.ok or skill.fm_raw is None:
        return out

    for key, value in skill.fm.items():
        if key not in SPEC_FIELDS:
            owners = world.owners_of_field(key)
            if owners:
                # A live extension of a real harness. Telling the author to nest it under
                # `metadata:` would switch the behaviour off, so this states the cost and
                # leaves the decision where it belongs.
                out.append(Finding("CP002", f"`{key}:` is outside the spec; read by "
                                            f"{', '.join(owners)} and refused by "
                                            f"`skills-ref validate`",
                                   severity="info", where="SKILL.md"))
            else:
                out.append(Finding("CP002", f"`{key}:` is outside the spec and no harness in "
                                            f"the registry documents it - nest it under "
                                            f"`metadata:` to keep it", where="SKILL.md"))
        allowed = VALUES.get(key)
        if allowed and value and value.strip().lower() not in allowed:
            out.append(Finding("CP001", f"`{key}: {value}` - the accepted values are "
                                        f"{', '.join(sorted(allowed))}", where="SKILL.md"))

    names = harness_names(cfg)
    if names:
        adapters, missing = world.select(names)
        for m in missing:
            out.append(Finding("CP009", f"no adapter for `{m}` - known harnesses are "
                                        f"{', '.join(world.names())}", severity="warning"))
        if adapters:
            out += portability_findings(SkillModel(skill, world), adapters, world)
    return out
