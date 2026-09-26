#!/usr/bin/env python3
"""The adapter registry.

Every `*.py` in this folder that defines a `HarnessAdapter` subclass is a harness.
Nothing lists them: adding one is dropping a file in here, which is the requirement
the whole split exists to satisfy.
"""
import importlib
import os
import pkgutil

from .base import HarnessAdapter

_CACHE = None


def _load():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    found = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for mod in pkgutil.iter_modules([here]):
        if mod.name.startswith("_") or mod.name == "base":
            continue
        # the names come from this package's own directory, not from data
        module = importlib.import_module(f".{mod.name}", __name__)  # sqs-allow: CB005
        for obj in vars(module).values():
            if (isinstance(obj, type) and issubclass(obj, HarnessAdapter)
                    and obj is not HarnessAdapter and obj.name):
                found[obj.name] = obj()
    _CACHE = found
    return found


class World:
    """Every adapter at once, plus the cross-adapter questions one of them may ask.

    An adapter cannot answer "is this somebody else's field" on its own, and it must
    not carry a copy of the others' tables to try. It asks the world instead.
    """

    def __init__(self, adapters=None):
        self.adapters = adapters if adapters is not None else _load()

    def __iter__(self):
        return iter(sorted(self.adapters.values(), key=lambda a: a.title.lower()))

    def __len__(self):
        return len(self.adapters)

    def get(self, name):
        return self.adapters.get(name)

    def names(self):
        return sorted(self.adapters)

    def select(self, names):
        """The named adapters, plus the names that matched nothing."""
        if not names or "all" in names:
            return list(self), []
        picked, missing = [], []
        for n in names:
            a = self.adapters.get(n)
            (picked.append(a) if a else missing.append(n))
        return picked, missing

    def owners_of_field(self, field):
        """Which harnesses document this frontmatter field, whatever the role."""
        return sorted(a.name for a in self if field in a.fields)

    def owners_of_syntax(self, key):
        """Which harnesses document rewriting this piece of body syntax."""
        return sorted(a.name for a in self if key in a.body_syntax)

    def location_fragments(self):
        """The distinctive head of every documented location, e.g. `.claude/skills`.

        The normalized model searches skill text for these, so a hard-coded path into
        somebody's skill tree is detected from the registry rather than from a list
        maintained by hand next to it.
        """
        out = set()
        for a in self:
            for loc in a.locations:
                head = loc.replace("\\", "/").split("/<")[0].lstrip("~").lstrip("/")
                if head and not head.startswith("<"):
                    out.add(head)
        return out

    def owners_of_location(self, fragment):
        """Which harnesses load skills from a path containing this fragment."""
        frag = fragment.strip("/")
        return sorted(a.name for a in self
                      if any(frag in loc.replace("\\", "/") for loc in a.locations))

    def detect(self, root):
        """The harnesses whose own layout is visible at `root`."""
        return [a for a in self if a.detect(root)]


def registry():
    return World()
