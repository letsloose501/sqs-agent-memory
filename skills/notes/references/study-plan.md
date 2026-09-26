# Mode: Study plan

Requests like "how do I learn X", "make a plan for the topic", "where do I start". The job is to turn
the **existing** notes and cards of the topic into a route from reading to mastery. The plan does not
teach; it organises what the vault has and shows the gaps.

## First, read the topic

1. Find the topic's notes (Glob/Grep in its folder) and its cards in `Cards/<Topic>/`.
2. Work out what is covered and what is missing. A gap in the foundation (a key note does not
   exist) goes into the plan as "take notes on this first"; do not pretend the material is complete.
3. Take the user's level and goal into account if the request states them.

## Four pillars

From passive to active:

1. **Study (notes).** The reading order from simple to complex, with `[[...]]` links. Split into
   stages or weeks for a big topic.
2. **Cards.** Which decks (`#Cards/<Topic>/...`) to review, in what order, about how many a day.
   Tie reading stages to decks: read a section, add its cards to review.
3. **Practice.** Concrete tasks, exercises or small projects that apply the knowledge. For code:
   tasks or a project; for philosophy: analysing a text, an essay; for editing: a practical
   exercise. Practice is always concrete and checkable, never "practise a bit".
4. **Explaining to others (the Feynman method).** What to retell in one's own words, which
   questions to ask oneself, where the explanation breaks: that is where understanding has a gap.

## Review rhythm

- Cards: daily; the plugin serves what is due.
- Rereading notes: at growing intervals (next day, a week, a month), and always before practice on
  that section.
- Checkpoints: "after stage N: do practice P and explain the topic aloud".

## Output

A file `<Topic> - study plan.md` next to the topic (or where the user asks):

```
---
tags:
  - <Topic>
  - Study plan
---
# <Topic> - study plan

<1-2 sentences: the goal and the starting point (what exists, what is missing).>

## Stage 1. <name>
- **Study:** [[Note A]] -> [[Note B#Section]]
- **Cards:** #Cards/<Topic>/A  (about N a day)
- **Practice:** <a concrete task>
- **Explain:** <what to retell in your own words>

## Stage 2. ...

## Review rhythm
<daily cards + reread intervals + checkpoints>

## Gaps
<what the vault is missing: what to take notes on>
```

Use the real names of notes and tags from the vault: the plan must be clickable and usable, not
abstract advice.
