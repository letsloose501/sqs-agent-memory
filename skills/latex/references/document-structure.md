# Document structure and bibliography

## Step 4. Document Structure

### 4.1 Theorem or Proof Document

```
\section{Problem Setup}        % domain, objective, algorithm
\section{Assumptions}          % numbered assumption environments
\section{Main Result}          % preliminary lemmas, then main theorem with proof
\section{Discussion}           % implications, special cases, connections (optional)
```

### 4.2 Convergence Analysis

```
\section{Problem Formulation}       % objective, domain, algorithm statement
\section{Assumptions}               % numbered assumption environments
\section{Main Convergence Theorem}  % theorem + proof
\section{Complexity Analysis}       % oracle and iteration complexity (when applicable)
\section{Numerical Experiments}     % tables and figures
```

### 4.3 Derivation Document

```
\section{Setup}       % define all objects, notation, spaces
\section{Derivation}  % step-by-step with align environments
\section{Result}      % \boxed{} final expression
```

Highlight a key final result with:

```latex
\begin{equation}\label{eq:main}
\boxed{ x_{k+1} = x_k - \alphak \grad f(x_k) }
\end{equation}
```

### 4.4 Literature Review or Introduction

Structure:
1. Motivate the problem with context and practical relevance.
2. Survey related work using `\citet{}` and `\citep{}`.
3. Identify the gap or limitation addressed by the present work.
4. State contributions precisely (numbered or itemised list).
5. Outline the remainder of the document.

Example:

```latex
Early work by \citet{calderon1980} established the theoretical basis for EIT.
Regularisation strategies were studied by \citet{engl1996} and \citet{vogel2002}.
Data-driven approaches have recently gained attention~\citep{hamilton2018, adler2017}.
```

---

## Step 5. Reference Section (Document Mode)

### 5.0 Choose a Bibliography Workflow

**Ask the user which workflow they use before writing the reference section.** If no
preference is stated, default to Option A. The options are architecturally incompatible:
do not mix commands or packages from both in the same document.

| | Option A — Self-contained | Option B — External `.bib` |
|---|---|---|
| **Backend** | Inline `thebibliography`; no auxiliary files | BibTeX (`natbib`) or BibLaTeX (Biber) |
| **When to use** | Quick notes, isolated proofs, single-file submissions | Ongoing projects with a shared `.bib`; BibLaTeX users |

---

### Option A — Self-Contained (`thebibliography`)

Place immediately before `\end{document}`. Set the argument to the widest label expected
(e.g., `{99}`). Do not include `\bibliographystyle{}` or `\bibliography{}`.

#### `\bibitem` Format by Source Type

```latex
% Journal article
\bibitem{citekey}
A.~Surname and B.~Surname,
``Title,''
\textit{Journal Name},
vol.~X, no.~Y, pp.~NNN--NNN, Year.

% Conference paper
\bibitem{citekey}
A.~Surname and B.~Surname,
``Title,''
in \textit{Proceedings of the Conference (ACRONYM)},
City, Country, Year, pp.~NNN--NNN.

% Book
\bibitem{citekey}
A.~Surname,
\textit{Title of the Book},
Publisher, City, Year.

% PhD / MSc thesis
\bibitem{citekey}
A.~Surname,
``Title of the thesis,''
Ph.D.\ dissertation, Department, University, City, Country, Year.

% Technical report
\bibitem{citekey}
A.~Surname,
``Title,''
Tech.\ Rep.\ TR-XXXX, Institution, Year.

% arXiv preprint
\bibitem{citekey}
A.~Surname and B.~Surname,
``Title,''
\textit{arXiv preprint} arXiv:XXXX.XXXXX, Year.
```

If the user cites a key without providing bibliographic details, populate from knowledge of
the standard literature. For well-known works, supply complete and accurate entries. If
genuinely ambiguous, insert:

```latex
\bibitem{citekey}
\todo{Fill in full bibliographic details for \texttt{citekey}.}
```

Do not omit the `\bibitem`; a missing entry causes a compilation error.

---

### Option B1 — BibTeX with `natbib`

Replace the natbib preamble line with:

```latex
\usepackage[numbers,sort&compress]{natbib}
```

End-of-document block:

```latex
\bibliographystyle{plainnat}   % or: unsrtnat, ieeetr, siam, plain
\bibliography{refs}
```

Compilation: `pdflatex` → `bibtex` → `pdflatex` × 2.

Common `.bst` files: `plainnat` (author-year), `plain` (numbered), `ieeetr` (IEEE),
`siam` (SIAM), `amsplain` (AMS), `unsrt` (citation order).

---

### Option B2 — BibLaTeX with Biber

Remove `\usepackage{natbib}` entirely. Replace with:

```latex
\usepackage[
  backend=biber,
  style=authoryear,
  sorting=nyt,
  maxbibnames=99,
  giveninits=true,
  doi=false,
  url=false,
  eprint=true
]{biblatex}
\addbibresource{refs.bib}
```

End-of-document: `\printbibliography`. Do not use `\bibliographystyle{}` or `\bibliography{}`.

Compilation: `pdflatex` (or `lualatex`) → `biber` → `pdflatex` × 2.

Citation commands: `\parencite{}` (parenthetical), `\textcite{}` (textual),
`\citeyear{}` (year only), `\citeauthor{}` (author only).

Sample `.bib` entry:

```bibtex
@article{nesterov1983,
  author  = {Nesterov, Yurii},
  title   = {A method for solving the convex programming problem with convergence
             rate {$\mathcal{O}(1/k^2)$}},
  journal = {Doklady Akademii Nauk SSSR},
  volume  = {269},
  number  = {3},
  pages   = {543--547},
  year    = {1983}
}
```

If the user cites a key without a `.bib` entry, supply the correct entry from knowledge of
the standard literature. If genuinely ambiguous, insert:

```bibtex
@misc{citekey,
  note = {TODO: Fill in full bibliographic details.}
}
```
