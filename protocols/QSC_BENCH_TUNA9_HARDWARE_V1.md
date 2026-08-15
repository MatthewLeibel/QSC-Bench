# QSC-Bench Tuna-9 hardware-transfer protocol

Status: development protocol frozen before the first Tuna-9 control outcome. The earlier QX-emulator job IDs 1283722 and 1283724 were transport tests. Job 1283722 exposed and job 1283724 verified correction of the provider bit-layout parser. Neither is physical-QPU evidence. Nothing in this protocol or its results may be pushed, submitted to Metriq, or described as public without the owner's approval.

Freeze date: 2026-08-14, America/Vancouver.

## Claim boundary

This experiment tests a user-level hardware-in-the-loop transfer of the stability-contract architecture. A hidden benchmark disturbance is inserted into commanded single-qubit phase angles. A controller sees only finite-shot component responses and issues the next phase-compensation vector. Native Tuna-9 gate error, readout error, queue-time drift, and execution-time drift remain uncontrolled physical effects.

The experiment does **not** access or control Quantum Inspire's private pulse-level calibration registers. It is not evidence that TrueLoop has maintained a commercial QPU's internal calibration state. It is evidence about an adaptive component-observable maintenance loop executed through a real QPU, if the declared contract is restored.

## Backend and circuit

The target backend is Quantum Inspire Tuna-9, backend type 6. It exposes nine transmons and native one-qubit rotations plus CZ gates. Q8 is excluded because the provider currently warns that it is affected by a spurious two-level system.

Four logical monitor channels use physical qubits Q2, Q4, Q5, and Q7. Four disjoint payload qubits use Q0, Q1, Q3, and Q6, with the native CZ path Q0--Q1--Q3--Q6. Every acquisition executes both blocks and measures all eight used qubits in parallel.

For monitor channel \(i\),

\[
|0\rangle\xrightarrow{H}R_z\!\left(\frac{\pi}{2}+e_i\right)\xrightarrow{H}\text{measure},
\qquad
e_i=d_i+s_i g_i u_i.
\]

The disturbance \(d_i\), actuator polarity \(s_i\), and gain \(g_i\) are hidden from ranked controllers. The disjoint payload is an entangled mirror circuit. It applies fixed local rotations and three native CZ gates, inserts \(1.25e_i\), then applies the inverse circuit. Its ideal zero-error output is \(|0000\rangle\). The workload therefore tests whether monitor restoration transfers to a separate useful circuit, not merely whether a reported residual is small.

Quantum Inspire returns physical-qubit bitstrings. Both local and provider artifacts use the explicit convention Q\(i\) to B\(i\). The parser was verified on the QX emulator before any Tuna-9 control job.

## Published target and contract

Before control jobs, one no-disturbance Tuna-9 reference circuit is executed with 8,192 requested shots. Its four monitor marginals define \(y\). Let \(q_{\rm ref}\) be its payload bitwise-zero fraction. This target is then immutable for the campaign.

Contract entry requires two consecutive **ordinary** full-vector acquisitions satisfying both

\[
\sqrt{\frac{1}{4}\sum_i(\hat p_i-y_i)^2}\le 0.08
\]

and

\[
q_{\rm payload}\ge \max(0.70,q_{\rm ref}-0.10).
\]

Probe frames used only for commissioning are charged but cannot satisfy the consecutive-ordinary rule. Requested and completed shots are both retained; provider-enforced truncation is never silently relabeled.

## Deadline and controllers

The fixed deadline is five sequential circuit acquisitions, matching Tuna-9's current maximum number of circuit executions in one adaptive hybrid job. Every acquisition returns all four monitor channels and the payload in parallel.

- **Retained residual.** One retained identification move, then direct-residual updates with \(\eta=0.65\), momentum 0.15, estimator smoothing 0.50, gain floor 0.15, and identification amplitude 0.150 rad. The one-identification hardware profile is deliberately distinguished from the manuscript's three-identification reference profile.
- **Diagonal secant.** Strong in-class comparator: one retained full-vector identification move and bounded diagonal state.
- **Commissioned PI.** Strong linear comparator given two charged coded \(\pm0.150\)-rad commissioning frames, followed by ordinary PI updates.
- **Dense finite difference.** Out-of-class comparator requiring one base plus four coordinate probes before its dense correction is available. Two ordinary confirmation frames give a structural lower bound of seven acquisitions, so it cannot validate within the five-acquisition provider deadline.
- **Do nothing.** Resource-cheap negative control that cannot discharge restoration.

The architecture-level comparison is not “TrueLoop versus every controller.” Retained residual and diagonal secant are both candidate members of the minimal-sufficient resource class. A strong in-class comparator may win an individual accuracy or acquisition cell without weakening the class claim.

## Seeds and stopping rule

Development seed: 2026081499.

Confirmation seed phrase: `QSC-Bench-Tuna9-v1-hardware-confirmation-2026-08-14`.

Phrase SHA-256: `e250433b0d3587aecdab8a9703588588a71b3e0162ac0abac4ab4dad750e18a3`.

The first three derived nonzero values modulo \(2^{31}-1\) are 1411640080, 492734311, and 1568158650. Seeds 582662097 and 1606952049 are reserves and may be used only for a provider failure unrelated to the scientific result. A failed scientific outcome is not replaced.

All five arms passed source tests. Across 50 noisy Aer development seeds, retained residual, diagonal secant, and commissioned PI each entered contract in 50/50 cases; dense finite difference and do nothing entered in 0/50. The three confirmation seeds were also simulated before hardware submission and showed the same qualitative split. These are development checks, not hardware results.

One retained-residual Tuna-9 development job is allowed before the confirmation campaign. It may expose transport, syntax, bit-layout, or provider-metadata defects. Scientific thresholds and controller gains may not be retuned after viewing it. If provider behavior makes the declared measurement physically meaningless, the campaign is stopped and reported rather than repaired post hoc.

## Timing and evidence

For each job, retain creation, queue, start, and finish timestamps; provider-reported execution time; the five hybrid call durations; completed shots; controller-only update time; and all response and payload summaries. Queue and cloud orchestration latency are reported separately from QPU execution.

Any hardware time-to-contract number is measured only at width four. Width scaling remains simulator/reduced-model evidence from the frozen local campaign. Large-width physical times are explicit projections using measured acquisition depth and stated interface assumptions. The Tuna-9 experiment cannot, by itself, establish flat physical scaling.
