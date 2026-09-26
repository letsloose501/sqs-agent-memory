---
name: latex
description: >-
  Produces compilable LaTeX for formulas, theorems, proofs, derivations, algorithms, tables,
  TikZ plots and structured academic text on any technical topic, not one narrow field. Use on
  "write the theorem and proof", "make Beamer slides / a presentation", "derive the formula",
  "typeset this", "a .tex file". Three modes: Document (a full .tex), Snippet (one formula /
  table / algorithm), Beamer (slides). For Beamer, trigger whenever the words slides,
  presentation, beamer or talk appear.
---

# LaTeX: formulas, theorems, proofs, slides

Compilable LaTeX for mathematically dense text on any subject. Open the references by mode;
do not keep everything in your head.

## Step 1. Pick the mode

Check **Beamer first**: it has the clearest signals.

**Beamer Mode**: the words slides, presentation, beamer, talk, slide deck, a request to prepare a
talk from a paper or draft, "title slide" and similar section names. Use
`references/preamble.md` (Beamer part) and `references/beamer.md`. **Do not** use the Document
Mode preamble or structure.

- A finished manuscript or paper exists: move its content onto slides exactly, without distortion.
- Only a title or theses: build the full skeleton with `\todo{}` in the empty places.
- Never invent theorems, lemmas or numerical results that were not given.

**Document Mode**: a theorem / lemma / proposition / corollary / definition (with or without a
proof), a multi-step derivation, a convergence analysis, an algorithm with justification, an
introduction or literature review, a self-contained report or preprint. Deliver a full `.tex` file.

**Snippet Mode**: one formula or system of formulas, an algorithm or pseudocode alone, a results
table, a TikZ/pgfplots plot, any fragment to paste into someone else's template. Only the body (no
`\documentclass`, no preamble), in the chat as a code block, not a file (unless a file was asked for).

Unsure which mode: one question, "the whole document, a fragment, or slides?".

## References by step

| Need | Open |
|---|---|
| Document Mode preamble (packages, theorem environments, notation macros) | `references/preamble.md` |
| Beamer preamble, theme, color scheme | `references/preamble.md` (Beamer part) |
| Slide content: sections, citation footnotes, theorems on a slide, algorithms, results tables, frame rules, the full template, the checklist | `references/beamer.md` |
| Theorems and proofs, formula style, notation, algorithms (`algorithm2e`), results tables, TikZ/pgfplots | `references/math-standards.md` |
| Document structure by type (theorem/proof, convergence analysis, derivation, literature review), bibliography (own list / BibTeX+natbib / BibLaTeX+Biber) | `references/document-structure.md` |
| Phrases to avoid, the pre-delivery checklist, what to do with an incomplete request | `references/writing-quality.md` |
| The full Document Mode template | `references/templates.md` |

## Required before delivery

- Every `\begin{}` is closed by `\end{}`; every numbered environment has a `\label{}`; every
  `\ref{}` / `\eqref{}` / `\cref{}` resolves. The detailed checklist: `references/writing-quality.md`.
- No proof given by the user: do not invent one; put `\begin{proof}` with a `\todo{}` plan instead
  of a finished argument.
- Author, institution, talk topic not given: put `\todo{}` or ask; never copy the sample data from
  the references.
- If a TeX distribution is installed, compile and read the log before delivering; if it is not,
  say the file was not compiled.
