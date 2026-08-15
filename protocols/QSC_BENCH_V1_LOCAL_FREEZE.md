# QSC-Bench v1.0 local confirmation freeze

Status: locally frozen before confirmation execution. This is not a public preregistration, Metriq acceptance, or third-party timestamp. No result may be pushed, submitted, or described as public without the owner's explicit approval.

Freeze date: 2026-08-14, America/Vancouver.

## Manuscript lock

The benchmark targets the resource claim in the complete `TC_SUBMIT.zip` package, not a marketing paraphrase.

| Artifact | SHA-256 |
|---|---|
| `TC_SUBMIT.zip` | `bcb0d5ddfa01ef609b74a28c5be5ca2cea2478c6beb327a7aeed39e09e64fbe9` |
| `main.pdf` | `ebb1cc354f8e9bd3b9cf781f3542043c3027edce1d00850c4a0402751f55a4db` |
| `source/main.tex` | `2e70fdca877ef7431edbb817cc10a878cbf6cba6059b69e263928420d9574764` |
| `supplementary.pdf` | `3e84af9a7b5eeefe88218bf4c57f3d06b8eedcb6fccc37331a165517b0787b54` |
| `source/supplementary.tex` | `76a29e3b9fec76d4966c0d16faeb3bedc9414add7ef5bf4916a99f782da8faaf` |

The manuscript-level controller used here is an independent implementation of

\[
\phi_{t+1}=\Pi\!\left[\phi_t+H_t(y_t-\hat p_t)+\mu(\phi_t-\phi_{t-1})\right],
\]

with the disclosed reference constants \(\eta=0.65\), \(\mu=0.15\), estimator smoothing \(\beta=0.50\), gain floor \(g_{\min}=0.15\), identification amplitude 0.150 for three retained updates, and projection to \([-3,3]\). It stores six mutable floating-point words per channel plus an immutable identification sign. It is not asserted to be bitwise equivalent to a hosted TrueLoop service.

The architecture claim is class-level. A controller qualifies only if it uses one ordinary component-resolved vector per update, retains the applied configuration, discards no separate probe configuration during cold start, stores bounded state per channel, performs at most linear work in width for fixed design constants, and actually restores the monitor and independent payload contract. Diagonal retained secant and fixed-window Anderson are allowed to qualify. Dense full Broyden is not: its retained Jacobian is \(O(n^2)\) and its direct solve is \(O(n^3)\). Commissioned PI is a strong linear comparator, but its two discarded coded probes exclude it from the strict retained cold-start class. The do-nothing arm demonstrates that low resource cost without restoration is not sufficient.

Only sequential acquisition depth is hypothesized to remain bounded. Returned information, command width, local arithmetic, total state, sensor count, actuator count, and physical energy all grow with channel count.

## Plant and access contract

The effective phase of channel \(i\) is

\[
\theta^{\mathrm{eff}}_{i,t}=\theta_i^{(0)}+s_i g_i u_{i,t}+d_{i,t},
\]

where polarity, gain, and drift are hidden. One acquisition applies one complete command, executes one finite-shot monitor, measures every channel in the same shot batch, and returns one empirical marginal vector. Controllers cannot inspect hidden drift, gains, polarities, statevectors, density matrices, analytic probabilities, Jacobians, or gradients. The oracle is unranked.

The monitor circuit is `H-RZ-RY-RZZ(ring)-H-measure`, with nominal phase in [1.30, 1.80] rad, analysis tilt 0.40 rad, and ring coupling 0.15 rad. The initial persistent shock RMS is 0.45 rad. Drift has fast sigma 0.002, reversion 0.05, slow sigma 0.0005, and no common-mode term. The evaluator publishes local sensitivity and row-diagonal-dominance diagnostics but never passes them to a controller.

Contract entry requires monitor RMSE at most 0.035 for three consecutive ordinary acquisitions and then an independent payload pass. A failed payload resets the streak. The scale campaign allows 40 monitor acquisitions. Failures are right-censored at the budget and remain failures.

## Evidential layers

### A. Full Aer quantum core

`configs/aer_core_confirmation_v1.json` executes 4- and 8-qubit density-matrix circuits with finite shots, one- and two-qubit depolarizing error, symmetric readout error, RZZ coupling, and an entangled mirror payload. This establishes that the adaptive loop acts through quantum circuit execution rather than a hidden algebraic oracle. It is not the large-width scaling estimator.

### B. Exact-marginal scale campaign

`configs/scale_confirmation_v1.json` uses a closed-form evaluation of the same ideal unitary monitor's component marginals. Symmetric readout noise is exact. Each component receives the exact binomial marginal distribution; cross-channel shot covariance is omitted. The local-mirror payload marginal is exact. The backend is validated against Aer at overlapping widths before its scale result is accepted.

The primary widths are 16, 64, 256, 1,024, 4,096, 16,384, and 65,536 channels, with 30 paired seeds per cell. This is a bounded-coupling marginal model, not a 65,536-qubit globally entangled state simulation and not physical QPU evidence.

### C. Dense-baseline campaign

`configs/strong_baselines_confirmation_v1.json` uses widths 4, 8, 16, 32, 64, and 128 and a 180-acquisition budget. It directly executes full Broyden and dense finite difference where their dense state and solve fit safely. Larger widths are represented by exact structural state, work, and acquisition counts rather than allocating a dense matrix. Both dense implementations are hard-limited to 512 channels.

## Controllers and frozen constants

Controller source and constants are frozen with this protocol. Development runs used only seeds in the 310000, 320000, 330000, and 340000 ranges. No controller is retuned after a local-confirmation outcome is generated.

Scale arms: do nothing, retained residual, diagonal retained secant, fixed-window Anderson residual (window 5), commissioned PI, SPSA, and unranked oracle.

Dense-baseline arms: retained residual, fixed-window Anderson residual, full Broyden, dense finite difference, and unranked oracle.

The full Broyden and dense finite-difference arms are not weakened controls. They receive the same finite-shot component vectors. Dense finite difference receives and is charged for a base frame plus one coordinate probe per channel. Full Broyden retains every ordinary frame but pays for a dense model and regularized direct solve. SPSA receives exactly the two scalar losses its estimator uses, and both discarded probe acquisitions are charged.

## Seed derivation

Phrase: `QSC-Bench-v1.0-local-confirmation-2026-08-14`

Phrase SHA-256: `0b6c7322443d8b3e63250117a316349c9c4eb200fa2ff783373493b470b9501d`

For counter 0, 1, 2, ...:

1. hash UTF-8 `phrase + ":" + decimal(counter)` with SHA-256;
2. interpret the first eight digest bytes as an unsigned big-endian integer;
3. reduce modulo \(2^{31}-1\);
4. skip zero and duplicates;
5. accept the first 30 values.

The executable derivation is `scripts/derive_confirmation_seeds.py`. The same seeds are paired across controllers and widths.

## Primary hypotheses and decisions

The analysis uses 10,000 paired bootstrap draws and bootstrap seed 20260814. It reports medians, IQRs, percentile intervals, Wilson success intervals, failures, Kaplan-Meier median where estimable, restricted mean time to the censoring budget, and paired-seed scaling fits.

For each candidate controller, fit

\[
\log A(n)=\log c+\alpha\log n
\]

to width medians from seeds that succeed at every declared width. Exclusions remain explicit.

The finite-range class result is PASS if at least one structurally qualifying controller satisfies all of the following in the primary scale campaign:

1. candidate resource metadata is true and independently state-audited;
2. at least four declared widths execute;
3. the minimum 95% Wilson lower bound on contract success is at least 0.85;
4. at least 20 seeds succeed at every width;
5. the upper endpoint of the bootstrap 95% interval for \(\alpha\) is at most 0.05; and
6. the independent payload is valid at every accepted contract entry.

With 30 trials, the Wilson rule requires 30/30 successes at every width: 29/30 has a lower bound below 0.85. The exponent margin permits at most a factor \(4096^{0.05}\approx1.52\) increase over the full 16-to-65,536 range at its upper confidence boundary. This is finite-range evidence, not an asymptotic proof.

The architecture-level conclusion additionally requires:

1. zero execution errors;
2. analytic/Aer expectation differences below 1e-12 for monitor and payload, Jacobian difference below 2e-5, closed-loop success-rate difference at most 0.25, and median acquisition difference at most six on the frozen overlap;
3. dense finite difference to expose its charged \(n+1\) commissioning sequence and \(O(n^2)\) retained Jacobian;
4. full Broyden to expose its \(O(n^2)\) state and \(O(n^3)\) direct solve, irrespective of whether its acquisition count is good; and
5. all physical-time claims to report acquisition-only time, measured local host time, and explicit interface-bandwidth scenarios separately.

A strong baseline may beat a qualifying controller in acquisitions or residual. That does not falsify the resource-class result if it pays a declared superlinear state/work cost. Conversely, bounded acquisition depth alone cannot establish the architecture if the method re-imports a dense model.

## Claim boundary

If the primary decision passes, the allowed conclusion is:

> Over the tested finite range, at least one retained component-resolved controller preserved verified payload usability with no statistically resolved acquisition-depth growth beyond the predeclared equivalence margin, while explicit comparator procedures exposed their predicted acquisition or dense host-resource ceilings.

It is not permissible to call this a universal constant-time algorithm, quantum advantage, physical-QPU result, globally entangled 65,536-qubit simulation, or measured millisecond performance at unbuilt scale. Time projections must be labeled projections and must retain the linear interface and local-processing terms.

All failures and negative results are retained. Confirmation output is written to an ignored directory so the source tree remains clean during execution; final artifacts may be force-added only after the complete campaign and hashes are generated.
