# Writing quality: checklist before delivery

## Step 6. Writing Quality Standards

### 6.1 Prohibited Characters and Typographic Flags

The following must never appear in any output:

| Item | Rule |
|---|---|
| Em dash (---) | Prohibited. Use comma, semicolon, colon, or parentheses. |
| En dash (--) outside LaTeX ranges | Prohibited in prose. In LaTeX, `--` is correct only for numeric ranges and compound proper-noun modifiers (Dirichlet--Neumann map). |
| Ellipsis (...) | Use `\ldots` in math mode. In prose, avoid entirely; state the complete idea. |
| Exclamation mark | Prohibited in scientific prose. |
| Scare quotes | Avoid. Use italics on first use: `\textit{prior model}`. |
| Contractions | Prohibited. Write: it is, do not, we have. |
| Rhetorical questions | Prohibited. |
| Transitional intensifiers | Prohibited: "importantly", "crucially", "notably", "it is worth noting that". State the point directly. |
| First-person singular (I) | Use "we" consistently, even for single-author work. |
| Noun stacks (3+ consecutive) | Avoid "deep learning-based inverse problem regularisation framework". Rewrite as "a regularisation framework for inverse problems based on deep learning". |

### 6.2 Sentence and Paragraph Construction

Write in complete, declarative sentences. Every sentence carries one identifiable claim or
step. Paragraph breaks signal a shift in focus.

Prefer active constructions: "We derive an upper bound" over "An upper bound is derived."
Reserve the passive for results independent of the authors: "The problem is ill-posed in
the sense of Hadamard."

Avoid vague intensifiers: "very", "quite", "rather", "highly", "extremely". Quantify
where possible: "the condition number grows as $\bigO{h^{-2}}$".

### 6.3 Mathematical Prose

Every displayed equation referred to subsequently must be labelled and introduced by a
complete grammatical sentence. Treat the equation as part of the sentence with appropriate
punctuation.

Define every symbol before or at its first use. When citing a result, state precisely which
part of the cited work is being used (e.g., `\citet[Theorem~2.1]{engl1996}`). Avoid vague
attributions such as "as shown in [3]".

Place quantitative conditions in numbered `assumption` environments rather than burying them
inside theorem statements, whenever those conditions are reusable across multiple results.

### 6.4 Consistency Checks

Before outputting any document, verify:
1. Every symbol introduced in the preamble is used at least once in the body; remove unused macros.
2. The same physical quantity uses the same symbol throughout; no silent switching.
3. All theorem environments are closed; all proofs end with `\end{proof}`.
4. Every `\begin{}` has a matching `\end{}`.
5. No conflicting packages (e.g., `amsmath` not loaded twice; `algorithm2e` and `algorithmic` not both loaded).

---

## Step 7. Pre-Output Quality Checklist

Run through all items below before producing the final output.

### Compilability
- Every `\begin{}` has a matching `\end{}`.
- No undefined control sequences.
- All required packages loaded in the preamble.
- No package conflicts.

### Label Consistency
- Every numbered environment has a `\label{}`.
- Every `\ref{}`, `\eqref{}`, `\cref{}` resolves to an existing label.
- No label defined more than once.

### Notation Consistency
- Same symbol used for the same object throughout.
- Step sizes, regularisation parameters, and iterates follow Section 3.3 conventions.
- All macros used in the body are defined in the preamble.

### Mathematical Correctness
- Inequalities point in the correct direction.
- Convergence rates and complexity bounds are dimensionally consistent.
- Cited results are used correctly and not misrepresented.
- Proof steps follow logically from stated assumptions.

### Bibliography Completeness
- **Option A:** Every `\cite{}` key has a fully populated `\bibitem{}`; no orphan entries.
- **Option B1:** Every cited key exists in the `.bib` file; `\bibliographystyle{}` and `\bibliography{}` present; `biblatex` not loaded.
- **Option B2:** Every cited key in the `.bib` file; `\printbibliography` present; no `\bibliographystyle{}` or `\bibliography{}`; `natbib` not loaded.

### Margin Safety
- No plain `tabular` with more than 4 columns unless wrapped in `tabularx` or `\resizebox`.
- Every `pgfplots` axis uses a relative width; no absolute `cm` or `pt` values.
- Every free-standing wide `tikzpicture` wrapped in `\adjustbox{max width=\textwidth}`.
- Side-by-side subfigures use `width=\linewidth` inside their `subfigure` environment.

### Writing Quality
- No em dashes, en dashes (outside LaTeX ranges), or prose ellipses.
- No contractions, exclamation marks, or rhetorical questions.
- No prohibited transitional intensifiers.
- Every symbol defined before or at first use.
- Every displayed equation introduced by a complete grammatical sentence with correct punctuation.

---

## Step 8. Handling Ambiguous or Incomplete Requests

### Missing proof
If the user requests "write up this theorem" without providing a proof, produce the theorem
statement and a `\begin{proof}...\end{proof}` scaffold with `\todo{}` markers. Do not
construct a proof that was not provided.

### Partial notation
If the user provides incomplete notation or an unfinished derivation, ask exactly one
clarifying question before proceeding. Do not guess at notation.

### Mixed content
If the request combines document and snippet content, produce a complete document and include
all elements within it.

### User-provided notation
If the user provides existing mathematical content, preserve their notation and mathematical
choices exactly. Normalise only formatting and typographic conventions; do not alter the
mathematics or rename symbols.
