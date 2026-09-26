# Full document template (Document Mode)

## Step 10. Complete Document Template

Replace all placeholder text with actual content.

```latex
\documentclass[11pt,a4paper]{article}

% [Insert the whole preamble from references/preamble.md]

\title{Title of the Document}
\author{Author Name\\
  Department, Institution, City, Country\\
  \texttt{email@example.com}}
\date{\today}

\begin{document}

\maketitle

\begin{abstract}
  A concise summary (150--250 words) of the problem, main results, methods used, and
  significance. Written in the third person; past tense for results, present tense for
  conclusions.
\end{abstract}

\section{Introduction}\label{sec:intro}

\section{Problem Formulation}\label{sec:problem}

\section{Assumptions}\label{sec:assumptions}

\begin{assumption}\label{ass:main}
  [State the assumption precisely.]
\end{assumption}

\section{Main Results}\label{sec:results}

\begin{theorem}[Descriptive title]\label{thm:main}
  Under \cref{ass:main}, \ldots
\end{theorem}

\begin{proof}
  [Proof.]
\end{proof}

\section{Numerical Experiments}\label{sec:experiments}

\section{Conclusion}\label{sec:conclusion}

% --- CHOOSE ONE ending below; delete the other two ---

% OPTION A: Self-contained
\begin{thebibliography}{99}
% [Fill \bibitem by references/document-structure.md, option A]
\end{thebibliography}

% OPTION B1: BibTeX + natbib
% \bibliographystyle{plainnat}
% \bibliography{refs}

% OPTION B2: BibLaTeX + Biber
% \printbibliography

\end{document}
```
