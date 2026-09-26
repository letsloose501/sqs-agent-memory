# Mathematical content: standards

## Step 3. Mathematical Content Standards

### 3.1 Theorem-like Environments

Use `amsthm` environments throughout. Apply consistent label prefixes:
`thm:`, `lem:`, `prop:`, `cor:`, `def:`, `ass:`, `rem:`, `ex:`, `eq:`, `alg:`, `fig:`, `tab:`.

Every numbered environment must carry a `\label{}`. Every `\ref{}` and `\eqref{}` must match
an existing label. Use `\cref{}` (from `cleveref`) in preference to `\ref{}` wherever the
environment type should appear in text. Use `\qed` or rely on `amsthm`'s automatic QED
symbol at the end of proofs. If assumptions are referenced repeatedly, define them as
numbered `assumption` environments.

Example with full proof scaffold:

```latex
\begin{assumption}\label{ass:smoothness}
  The function $f \colon \R^n \to \R$ is $L$-smooth: there exists $L > 0$ such that
  \begin{equation}\label{eq:smoothness}
    \norm{\grad f(x) - \grad f(y)} \leq L\norm{x - y}
    \quad \text{for all } x, y \in \R^n.
  \end{equation}
\end{assumption}

\begin{theorem}[Convergence of gradient descent]\label{thm:gd-convergence}
  Suppose \cref{ass:smoothness} holds and $f$ is bounded below. Let $\{x_k\}_{k \geq 0}$
  be the iterates of gradient descent with constant step size $\alpha \in (0, 1/L]$.
  Then
  \begin{equation}\label{eq:gd-rate}
    \min_{0 \leq k \leq K-1} \norm{\grad f(x_k)}^2
    \leq \frac{2\bigl(f(x_0) - f^*\bigr)}{\alpha K},
  \end{equation}
  where $f^* \coloneqq \inf_{x \in \R^n} f(x)$.
\end{theorem}

\begin{proof}
  By $L$-smoothness (\cref{ass:smoothness}), the descent lemma gives
  \[
    f(x_{k+1}) \leq f(x_k) - \frac{1}{2L}\norm{\grad f(x_k)}^2.
  \]
  Summing from $k = 0$ to $K-1$ and dividing by $K$ yields \cref{eq:gd-rate}.
\end{proof}
```

If the user provides a theorem statement without a proof, insert a scaffold:

```latex
\begin{proof}
  \todo{Proof to be completed. Suggested outline: (i) establish the descent lemma;
  (ii) telescope; (iii) divide by $K$.}
\end{proof}
```

Do not fabricate a proof.

### 3.2 Equations and Alignment

| Context | Environment | Rule |
|---|---|---|
| Single numbered equation | `equation` | Always label |
| Multi-line derivation | `align` | Align at `=` or relational symbol using `&`; label each key step |
| Auxiliary steps (unnumbered) | `align*` | No label required |
| Inline expressions | `$...$` | Use only for short symbols; prefer display for anything non-trivial |

Use `\coloneqq` (from `mathtools`) for definitions. Use `\text{where}`, `\text{for all}`,
and similar inside display math. Place punctuation inside displayed equations when the
surrounding sentence requires it. Never use `\text{O}` for asymptotic notation; always use
`\bigO{\cdot}` as defined in the preamble.

### 3.3 Notation Conventions

Be consistent within every document. The conventions below apply unless the user specifies
otherwise.

| Object | Notation |
|---|---|
| Scalars | $\alpha, \beta, \lambda \in \R$ (lowercase italic) |
| Vectors | $\bx, \by \in \R^n$ (bold lowercase) |
| Matrices / linear operators | $\bA, \bJ \in \R^{m \times n}$ (bold uppercase) |
| Function spaces | $\Lp{2}(\Omega)$, $\Sob{1}{\Omega}$, $\SobZ{1}{\Omega}$ |
| Gradient | $\grad f(x)$ |
| Hessian | $\Hess f(x)$ |
| Iterates | $x_k$ (subscript) or $x^{(k)}$ (superscript); pick one and do not change it |
| Objective / loss | $f$, $\mathcal{L}$, or $F$ following the user's choice |
| Step size | $\alphak$ or $\etak$; do not mix |
| Regularisation parameter | $\lambda$ or $\mu$ (not $\alpha$ if that is the step size) |
| Frobenius norm | $\normF{\bA}$ |
| Expectation | $\E[\cdot]$ |
| Probability | $\Prob(\cdot)$ |
| Forward (observation) operator | $\Forward$ |
| Regulariser | $\Reg$ |

For EIT and inverse problems, adopt the following when not overridden by the user:

- Conductivity distribution: $\sigma \in L^\infty(\Omega)$ with $\sigma \geq \sigma_{\min} > 0$.
- Dirichlet-to-Neumann map: $\Lambda_\sigma \colon H^{1/2}(\partial\Omega) \to H^{-1/2}(\partial\Omega)$.
- Measurement data: $\mathbf{V} \in \R^{m \times n_e}$.
- Tikhonov functional: $\Tikhonov{\Forward(\sigma)}{\mathbf{V}}{\lambda}$ per the macro.

### 3.4 Algorithm Pseudocode

Use the `algorithm2e` package (loaded with `ruled, vlined, linesnumbered`). Number lines
whenever the proof or analysis refers to specific steps. Add inline comments with `\tcp{}`.

```latex
\begin{algorithm}[H]
\caption{Iteratively Regularised Gauss--Newton (IRGN)}\label{alg:irgn}
\KwIn{Initial guess $\sigma^{(0)}$; data $\mathbf{V}$;
      regularisation parameters $\{\lambda_k\}$; tolerance $\varepsilon > 0$}
\KwOut{Approximate solution $\sigma^{(K)}$}
Set $k \leftarrow 0$\;
\While{$\norm{\sigma^{(k+1)} - \sigma^{(k)}} > \varepsilon$}{
  Compute Jacobian $\bJ_k \leftarrow \Forward'(\sigma^{(k)})$\;
  \tcp{Solve the linearised regularised subproblem}
  $\sigma^{(k+1)} \leftarrow \arg\min_{\sigma}
    \bigl\|\bJ_k(\sigma - \sigma^{(k)}) - (\mathbf{V} - \Forward(\sigma^{(k)}))\bigr\|^2
    + \lambda_k \Reg(\sigma)$\;
  $k \leftarrow k + 1$\;
}
\Return{$\sigma^{(k)}$}\;
\end{algorithm}
```

### 3.5 Tables of Numerical Results

Rules (apply without exception):
1. Use `booktabs` (`\toprule`, `\midrule`, `\bottomrule`). Never use vertical rules in the body.
2. Bold the best entry in each column with `\textbf{}`.
3. Report uncertainties as `$\mu \pm \sigma$` using `\pm`.
4. Use `siunitx` with the `S` column type for decimal alignment when precision matters.
5. Never allow a table to exceed `\linewidth`. Choose the construction method by column count:
   - Narrow (<=4 cols): plain `tabular`
   - Wide (5-7 cols): `tabularx` with `\linewidth`
   - Very wide (8+ cols): `\resizebox{\linewidth}{!}{...}`

Prefer `tabularx` over `\resizebox` wherever possible — rescaling reduces font size relative
to surrounding text.

See Section 3.5 examples below:

```latex
% Narrow table
\begin{table}[ht]
\centering
\caption{Relative reconstruction error. Bold indicates the lowest error.}\label{tab:relerr}
\begin{tabular}{lccc}
\toprule
Method & $\delta = 0.01$ & $\delta = 0.05$ & $\delta = 0.10$ \\
\midrule
Tikhonov ($\ell^2$) & $0.142 \pm 0.008$ & $0.231 \pm 0.011$ & $0.318 \pm 0.014$ \\
TV regularisation   & $\mathbf{0.103 \pm 0.006}$ & $\mathbf{0.187 \pm 0.009}$ & $0.274 \pm 0.013$ \\
\bottomrule
\end{tabular}
\end{table}

% Wide table
\begin{table}[ht]
\centering
\caption{Performance metrics across five noise levels.}\label{tab:perf}
\begin{tabularx}{\linewidth}{l *{5}{>{\centering\arraybackslash}X}}
\toprule
Method & $\delta_1$ & $\delta_2$ & $\delta_3$ & $\delta_4$ & $\delta_5$ \\
\midrule
Method A & val & val & val & val & val \\
\bottomrule
\end{tabularx}
\end{table}
```

### 3.6 TikZ Figures and pgfplots Graphs

Every figure must include: axis labels, a legend when multiple series are plotted, a
`\caption`, and a `\label`. For convergence plots, use `ymode=log`.

**Width policy (mandatory):** Every `tikzpicture` and `pgfplots` axis must declare an
explicit width using a relative length. Never use absolute `cm` or `pt` values.

| Layout | `width` value |
|---|---|
| Single figure, full-width | `0.85\textwidth` |
| Single figure, default | `0.75\textwidth` |
| Two side-by-side subfigures | `\linewidth` inside a `0.48\textwidth` subfigure |
| Three in a row | `\linewidth` inside a `0.32\textwidth` subfigure |
| Inset or thumbnail | `0.40\textwidth` |

```latex
% Standard convergence plot
\begin{figure}[ht]
\centering
\begin{tikzpicture}
\begin{semilogyaxis}[
    xlabel={Iteration $k$},
    ylabel={$f(x_k) - f^*$},
    legend pos=north east,
    grid=major,
    width=0.75\textwidth,
    height=0.5\textwidth
]
\addplot[blue, thick] coordinates { ... };
\addlegendentry{Method A}
\addplot[red, dashed, thick] coordinates { ... };
\addlegendentry{Method B}
\end{semilogyaxis}
\end{tikzpicture}
\caption{Convergence comparison. Vertical axis in logarithmic scale.}\label{fig:convergence}
\end{figure}

% Wide diagram fallback
\begin{figure}[ht]
\centering
\adjustbox{max width=\textwidth}{%
  \begin{tikzpicture}
    % wide architecture diagram
  \end{tikzpicture}%
}
\caption{Network architecture.}\label{fig:arch}
\end{figure}
```
