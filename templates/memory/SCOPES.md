# Scopes

With a single writer, access rules look like overkill. They are set up before they are needed
because the second writer appears unnoticed: a scheduled review task already writes here next
to the live session, and any other agent becomes a third.

The danger is not that someone deletes a file. The danger is that **one session draws a
conclusion from a chance occasion, writes it down as a fact, and tomorrow every session works
from it**, including those that have no way to know better.

## Four scopes

| Scope | What is in it | Who writes |
|---|---|---|
| **Constitution** | `README.md`, `SCOPES.md`: rules about the rules | only the human, at a direct request |
| **Shared memory** | the `*.md` entries in the root | the agent writes; editing someone else's entry needs a reason |
| **Draft** | `mistakes/` | the agent writes freely; emptied by the weekly review |
| **Session** | the current conversation | saved nowhere by itself |

The higher the scope, the costlier a mistake and the slower it is written to. The reverse,
editing the constitution "along the way", is exactly the accident this exists to prevent.

## How protection works

A file is protected if it is named in the constitution above **or** carries in its header:

```yaml
metadata:
  protected: true
```

A write to such a file is intercepted by the `guard_memory_scope.py` hook (PreToolUse on
Write and Edit) and refused. To lift it for one run, the human sets the environment variable
`AGENT_MEMORY_UNLOCK=1`; it is never set automatically.

## What is never stored

Not "stored carefully": **not stored**.

- passwords, tokens, API keys, private keys;
- payment details, card and account numbers;
- other people's personal data.

Git history is irreversible: a secret that reached a commit is compromised even if the next
commit removes it. Such a secret is **revoked**, not deleted.

## Lifetime

| Bucket | Examples | Lifetime |
|---|---|---|
| **Long-term** | preferences, working style, who they are | no expiry, revisited on contradiction |
| **With a TTL** | current project, a window of dates, temporary decisions | until the event ends, then retired |
| **Not stored** | secrets, one-off context, anything derivable from the vault or git | none |

A TTL entry is not deleted on a timer: it is marked **from which date it no longer holds**.
