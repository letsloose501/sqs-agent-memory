"""The layer that runs an agent instead of reading text.

Four modules, one question each:

    providers   which agent, and what one run of it comes back as
    tasks       the task set, and how a run of one is graded
    runtime     the same task with the skill and without it
    triggers    whether the agent reaches for the skill on the right wordings
    regression  whether the last change made any of that worse

Everything here is opt-in: it costs money, takes minutes and needs an agent installed.
The static half of the suite stays offline, deterministic and dependency-free, and
nothing in this package is imported until a command asks for it.
"""
