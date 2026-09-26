# Preambles

Document Mode: use it as is; do not trim or improvise.

## Step 2. Apply the Standard Preamble (Document Mode Only)

Use the preamble below verbatim. Do not improvise or abbreviate it.

```latex
\documentclass[11pt,a4paper]{article}

% ---------------------------------------------------------------
% Core mathematics packages
% ---------------------------------------------------------------
\usepackage{amsmath, amssymb, amsthm, mathtools}
\usepackage{bm}            % bold math symbols
\usepackage{dsfont}        % indicator function \mathds{1}

% ---------------------------------------------------------------
% Algorithms
% ---------------------------------------------------------------
\usepackage[ruled,vlined,linesnumbered]{algorithm2e}

% ---------------------------------------------------------------
% Graphics, figures, and plots
% ---------------------------------------------------------------
\usepackage{graphicx}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{subfigure}     % side-by-side figures
\usepackage{adjustbox}     % fallback rescaling for wide TikZ diagrams

% ---------------------------------------------------------------
% Tables
% ---------------------------------------------------------------
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{siunitx}       % decimal-aligned columns, SI units

% ---------------------------------------------------------------
% Cross-referencing and citations
% ---------------------------------------------------------------
\usepackage[numbers,sort&compress]{natbib}
\usepackage[colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue]{hyperref}
\usepackage[capitalise,noabbrev]{cleveref}

% ---------------------------------------------------------------
% Typography
% ---------------------------------------------------------------
\usepackage{microtype}
\usepackage{parskip}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}

% ---------------------------------------------------------------
% Page layout
% ---------------------------------------------------------------
\usepackage[margin=2.5cm]{geometry}

% ---------------------------------------------------------------
% Miscellaneous
% ---------------------------------------------------------------
\usepackage{xcolor}
\usepackage{todonotes}     % \todo{} markers for placeholders

% ---------------------------------------------------------------
% Theorem environments (amsthm)
% ---------------------------------------------------------------
\theoremstyle{plain}
\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{corollary}[theorem]{Corollary}

\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\newtheorem{assumption}{Assumption}
\newtheorem{example}[theorem]{Example}

\theoremstyle{remark}
\newtheorem{remark}[theorem]{Remark}

% ---------------------------------------------------------------
% Notation macros (computational and applied mathematics)
% ---------------------------------------------------------------
% Norms and inner products
\newcommand{\norm}[1]{\left\lVert #1 \right\rVert}
\newcommand{\normF}[1]{\left\lVert #1 \right\rVert_{\mathrm{F}}}
\newcommand{\ip}[2]{\left\langle #1,\, #2 \right\rangle}
\newcommand{\abs}[1]{\left\lvert #1 \right\rvert}

% Calculus and optimisation
\newcommand{\grad}{\nabla}
\newcommand{\Hess}{\nabla^2}
\newcommand{\Lapl}{\Delta}
\newcommand{\divergence}{\operatorname{div}}
\newcommand{\curl}{\operatorname{curl}}

% Function spaces
\newcommand{\Lp}[1]{L^{#1}}
\newcommand{\Sob}[2]{H^{#1}(#2)}
\newcommand{\SobZ}[2]{H^{#1}_0(#2)}

% Operators and matrices
\newcommand{\bA}{\mathbf{A}}
\newcommand{\bB}{\mathbf{B}}
\newcommand{\bJ}{\mathbf{J}}
\newcommand{\bK}{\mathbf{K}}
\newcommand{\bI}{\mathbf{I}}
\newcommand{\bx}{\mathbf{x}}
\newcommand{\by}{\mathbf{y}}
\newcommand{\bz}{\mathbf{z}}
\newcommand{\bu}{\mathbf{u}}
\newcommand{\bv}{\mathbf{v}}

% Probability and statistics
\newcommand{\E}{\mathbb{E}}
\newcommand{\Prob}{\mathbb{P}}
\newcommand{\Var}{\operatorname{Var}}
\newcommand{\Cov}{\operatorname{Cov}}
\newcommand{\indicator}{\mathbf{1}}

% Asymptotic notation
\newcommand{\bigO}[1]{\mathcal{O}\!\left(#1\right)}
\newcommand{\smallO}[1]{o\!\left(#1\right)}

% Common domains
\newcommand{\R}{\mathbb{R}}
\newcommand{\N}{\mathbb{N}}
\newcommand{\C}{\mathbb{C}}

% Regularisation (EIT / inverse problems)
\newcommand{\Reg}{\mathcal{R}}
\newcommand{\Forward}{\mathcal{F}}
\newcommand{\Tikhonov}[3]{\norm{#1 - #2}^2 + #3\,\Reg(#2)}

% Iterates and step sizes
\newcommand{\xk}{x_k}
\newcommand{\alphak}{\alpha_k}
\newcommand{\etak}{\eta_k}
```

---

## Beamer preamble (Beamer Mode only)

Do not mix it with the Document Mode preamble: they are mutually exclusive.

## Step 2B. Beamer Preamble (Beamer Mode Only)

Use the preamble below for ALL Beamer presentations. Do NOT mix with the article preamble
in Step 2. The two preambles are mutually exclusive.

**Theme selection:** The default theme is `Madrid`. If the user specifies a different
standard theme (e.g., `Berlin`, `AnnArbor`, `Warsaw`, `Copenhagen`, `Frankfurt`,
`Singapore`, `Boadilla`, `CambridgeUS`), substitute it in `\usetheme{}`. Never invent
custom themes; use only named Beamer built-in themes.

**Color theme:** Default is `default` (matching the chosen outer theme's palette). If the
user requests a specific color theme (e.g., `dolphin`, `beaver`, `crane`, `orchid`,
`rose`, `seagull`, `seahorse`, `whale`, `wolverine`), apply it with `\usecolortheme{}`.

```latex
\documentclass[aspectratio=169,10pt]{beamer}
% aspectratio=169 gives 16:9 widescreen; use 43 for 4:3 if user requests it.

% ---------------------------------------------------------------
% Theme — change \usetheme{} to any standard Beamer theme name
% ---------------------------------------------------------------
\usetheme{Madrid}
% \usecolortheme{dolphin}   % Uncomment and change to apply a colour theme

% ---------------------------------------------------------------
% Core mathematics
% ---------------------------------------------------------------
\usepackage{amsmath, amssymb, amsthm, mathtools}
\usepackage{bm}

% ---------------------------------------------------------------
% Algorithms — use ONE of the two options below; comment out the other
% ---------------------------------------------------------------
% OPTION A: algorithm2e (recommended for pseudocode with line numbers)
\usepackage[ruled,vlined,linesnumbered]{algorithm2e}

% OPTION B: algorithmicx + algpseudocode (uncomment if preferred)
% \usepackage{algorithmic}
% \usepackage{algorithmicx}
% \usepackage{algpseudocode}

% ---------------------------------------------------------------
% Graphics and plots
% ---------------------------------------------------------------
\usepackage{graphicx}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{subfigure}

% ---------------------------------------------------------------
% Tables
% ---------------------------------------------------------------
\usepackage{booktabs}
\usepackage{tabularx}

% ---------------------------------------------------------------
% Theorem-like blocks — configurable style
% ---------------------------------------------------------------
% Beamer provides: theorem, lemma, corollary, proof, definition,
% example, block, alertblock, exampleblock — all built-in.
%
% For coloured framed boxes (tcolorbox style), uncomment below:
% \usepackage{tcolorbox}
% \tcbuselibrary{theorems,skins}
% Then define custom tcolorbox environments as needed (see references/beamer.md).

% ---------------------------------------------------------------
% Footnote citation control
% ---------------------------------------------------------------
\usepackage{perpage}   % resets footnote counter on each slide
\MakePerPage{footnote}

% ---------------------------------------------------------------
% Miscellaneous
% ---------------------------------------------------------------
\usepackage{xcolor}
\usepackage{multicol}  % for two-column slides

% ---------------------------------------------------------------
% Notation macros (shared with article mode for consistency)
% ---------------------------------------------------------------
\newcommand{\norm}[1]{\left\lVert #1 \right\rVert}
\newcommand{\ip}[2]{\left\langle #1,\, #2 \right\rangle}
\newcommand{\abs}[1]{\left\lvert #1 \right\rvert}
\newcommand{\grad}{\nabla}
\newcommand{\R}{\mathbb{R}}
\newcommand{\N}{\mathbb{N}}
\newcommand{\E}{\mathbb{E}}
\newcommand{\bigO}[1]{\mathcal{O}\!\left(#1\right)}
\newcommand{\xk}{x_k}
\newcommand{\alphak}{\alpha_k}
\newcommand{\etak}{\eta_k}
\newcommand{\bx}{\mathbf{x}}
\newcommand{\bg}{\mathbf{g}}
\newcommand{\bA}{\mathbf{A}}
\newcommand{\bJ}{\mathbf{J}}

% ---------------------------------------------------------------
% Presentation metadata — fill in before \begin{document}
% ---------------------------------------------------------------
\title[Short Title]{Full Title of the Presentation}
\subtitle{Subtitle or Paper Title (if applicable)}
\author[Surname]{Name Surname}  % ask the user
\institute[]{%  % ask the user (university, department, city)
  \todo{Department / university / city}
}
\date{\today}
```
