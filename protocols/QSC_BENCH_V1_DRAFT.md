# QSC-Bench v1.0 draft protocol

Status: superseded for the cold-start confirmation campaign by `QSC_BENCH_V1_LOCAL_FREEZE.md`. The wider multi-track suite remains a development plan. Neither document is a public preregistration or upstream submission.

## Research question

Given a drifting quantum computational substrate, how many sequential plant interactions, how much host computation, how much retained controller state, and how much interface traffic does a controller require to restore a declared operating contract and make a separate payload computation usable?

QSC-Bench is controller-neutral. “Retained residual” is one entry. Any method may win a track if it obeys that track's information-access rules.

The architectural hypothesis concerns a resource class, not controller branding. A cold-start controller is a candidate for the manuscript's minimal-sufficient class only if it:

1. carries the writable plant configuration forward as retained state;
2. updates that configuration from the current ordinary acquisition instead of constructing and discarding probe configurations;
3. receives the complete component-resolved response in one parallel acquisition;
4. uses bounded auxiliary state per channel and no dense plant model;
5. performs no more than linear host/local arithmetic per update; and
6. actually discharges restoration, spread tolerance, composability, and operability within the declared plant conditions.

The first five items are resource/access tests. The sixth is empirical. A do-nothing method has cheap resource counts but is not sufficient if it fails the contract. Conversely, a full dense Broyden/Jacobian method is not in class merely because it regulates well: its model state and update burden are superlinear. A retained *diagonal* secant method can be in class because it retains only a fixed number of scalars per channel. “Broyden” without this qualifier is too ambiguous for benchmark reporting.

## Access model

The host receives the public target vector, the current finite-shot component response, and only the state its controller is permitted to retain. Ranked controllers cannot inspect hidden drift, actuator gains, polarities, circuit statevectors, density matrices, analytic probabilities, or analytic gradients.

One monitor acquisition is:

1. apply one \(n\)-component command frame;
2. execute one quantum monitor circuit for \(S\) shots;
3. measure every qubit in the same shot batch;
4. return one empirical \(n\)-component marginal vector.

The number of values in that vector is \(\Theta(n)\). The sequential acquisition depth is one. These quantities are recorded separately.

## Plant

The plant starts in \(|0\rangle^{\otimes n}\). Channel \(i\) receives the effective phase

\[
\theta^{\mathrm{eff}}_{i,t}=\theta_i^{(0)}+s_i g_i u_{i,t}+d_{i,t},
\]

where \(u_i\) is the public command, \(s_i\in\{-1,+1\}\) and \(g_i>0\) are hidden, and \(d_i\) is hidden drift. The main monitor applies \(H\), \(R_Z(\theta_i^{\mathrm{eff}})\), a fixed \(R_Y(0.40)\) analysis tilt, a sparse ring of \(R_{ZZ}(\chi)\) gates, a final \(H\), and simultaneous Z measurement. The primary track uses \(\theta_i^{(0)}\in[1.30,1.80]\) radians and \(\chi=0.15\) radians. This places the plant on a high-slope fringe and gives real but weak neighbor coupling.

Finite shots, public one- and two-qubit depolarizing rates, and public symmetric readout error define the noise model. These are benchmark parameters, not claims about a named QPU.

The hidden drift is

\[
d_t=f_t+w_t,
\qquad
f_{t+1}=(1-\lambda)f_t+\nu_t,
\qquad
w_{t+1}=w_t+\zeta_t.
\]

The cold-start offset is placed in the persistent component \(w\). Otherwise a do-nothing controller can appear to calibrate as the initialization passively mean-reverts.

The benchmark computes an evaluator-only numerical Jacobian at the reference point. The primary track must have nonzero diagonal sensitivity and strict row diagonal dominance. This diagnostic is published but never supplied to controllers.

## Target and payload

A shared high-shot reference acquisition at zero drift and zero command defines the monitor target \(y\). Reference generation is benchmark setup, not controller cold-start cost.

The payload is separate. A seeded shallow unitary \(U\), an amplified instance of the same hidden phase error, and \(U^{-1}\) form a randomized mirror workload. Its mean per-qubit zero-return probability and all-zero probability are recorded. The payload passes when its bitwise return probability is no more than a declared amount below the nominal high-shot payload reference.

The component contract and payload contract are deliberately distinct. A controller cannot win by matching an aliased monitor root that leaves the computation wrong.

## Contract entry

The default monitor condition is

\[
\sqrt{n^{-1}\sum_i(\hat p_i-y_i)^2}\le \epsilon_p
\]

on three consecutive ordinary monitor acquisitions. After the third pass, the payload is executed at the current configuration. Entry is accepted only if the payload also passes. A failed payload resets the streak. Runs that exhaust their budget are failures/censored outcomes.

The primary metric is verified acquisitions to contract, including charged commissioning acquisitions. Secondary metrics include first monitor pass, confirmation depth, payload attempts, total quantum executions to usability, host update time, simulator runtime, traffic scalars, actuation frames, shot count, controller state, hidden phase RMS for evaluator audit, and payload quality.

For an explicit physical acquisition latency \(\tau\), report

\[
T_{\mathrm{contract}}(\tau)=A_{\mathrm{contract}}\tau+T_{\mathrm{host}}
\]

and

\[
T_{\mathrm{usable}}(\tau)=A_{\mathrm{all\ quantum\ executions}}\tau+T_{\mathrm{host}}.
\]

Aer runtime is never substituted for \(\tau\).

## Controller tiers

| Controller | Access | Cold-start charge | Host work/state | Cold-start class status | Ranking |
|---|---|---:|---:|---|---|
| Do nothing | target only | 0 | \(O(n)\) / \(O(1)\) per channel | resource-cheap but empirically insufficient when contract fails | yes |
| Retained residual | one component vector/cycle | no separate sweep | \(O(n)\) / six float words per channel plus immutable sign bit | candidate minimal sufficient | yes |
| Diagonal retained secant | one component vector/cycle | retained excitation | \(O(n)\) / four float words per channel plus immutable sign bit | candidate minimal sufficient | yes |
| Commissioned PI | component vectors | two coded parallel probes in this implementation | \(O(n)\) / three float words per channel | maintenance-floor comparator after charged commissioning; not retained cold start | yes, labeled commissioned |
| Dense finite difference | component vectors | \(n+1\) sequential probes | dense solve / \(O(n^2)\) state | out of class | small-width only |
| Oracle | hidden state | none | evaluator access | unrealizable lower bound | no |

The first release should add Anderson mixing, an RLS/model-based small-width method, SPSA with scalar access, periodic recalibration, and a declared sweep baseline before confirmation. Their absence from the present smoke implementation must remain visible.

## Planned benchmark tracks

1. Cold start / verified time to contract.
2. Long-horizon drift hold and contract uptime.
3. Shock recovery after a settled state.
4. Drift frontier.
5. Exact-width channel scaling.
6. Coupling sweep through loss of diagonal dominance and beyond.
7. Shot-budget sweep.
8. Gate- and readout-noise sweep.
9. Correlated/full-rank/low-rank drift.
10. Moving target.
11. Periodic-versus-continuous acquisition breakeven.
12. Payload time to usable solution.
13. Tiled bounded-coupling scale extension, explicitly distinct from a globally entangled system.

The current code fully implements only the cold-start track. The plant parameters already expose coupling, shot count, noise, and drift correlation, but sweep orchestration and frozen result schemas remain to be added.

## Scale hierarchy

- Exact density-matrix track: modest widths where noisy coupled evolution is exact.
- Matrix-product-state track: shallow one-dimensional circuits at larger exact widths, after equivalence checks against the exact track.
- Tiled quantum-plant extension: independent or weakly linked blocks of 8–16 simulated qubits. Report it as a tiled bounded-coupling quantum plant, never as a million-qubit globally entangled simulation.
- Analytic/statistical extension: only after reduced-model error is measured against the quantum tracks.

## Architecture-scale result

The intended result has two evidential layers and they must not be collapsed.

First, measured quantum or validated tiled runs estimate acquisitions to verified contract for every controller. The primary class-level test is whether at least one qualifying minimal-sufficient controller has an acquisition-depth curve consistent with no growth over the declared widths while preserving payload validity. Controller-specific ordering is secondary; if diagonal retained secant beats retained residual, both results are published.

Second, structural comparator costs are projected from their declared procedures. A coordinate finite-difference Jacobian cannot complete commissioning in fewer than \(n+1\) sequential acquisitions. At acquisition latency \(\tau\), its best-case acquisition-only time is therefore at least \((n+1)\tau\), before contract confirmation. This is a procedural lower bound, not an executed million-channel quantum run. The qualifying controller projection is \(k\tau\) only under the separately tested no-growth hypothesis.

Every scale artifact must publish:

- the measured width range and seed count;
- the assumed extrapolation range;
- sequential acquisition depth;
- vector values and bytes moved per acquisition;
- host/local arithmetic and state class;
- measured host update time where available;
- acquisition-only time as a function of explicit \(\tau\); and
- placement of the maintenance loop relative to the workload host boundary.

Only sequential depth may be described as flat. The controller still processes \(\Theta(n)\) values, stores \(\Theta(n)\) total bounded state, and drives \(n\) physical controls. End-to-end “10 ms at any scale” wording is permitted only when measured or modeled readout, transport, local update, actuation distribution, and settling all fit inside that deadline. Otherwise the defensible statement is that the *latency multiplier from sequential revisits* remains bounded while a probe sweep's multiplier grows with \(n\).

## Statistical freeze

Development seeds are public and may be used for debugging and controller tuning. Confirmation seeds must be generated by a predetermined public procedure only after the protocol, code, controller parameters, simulator versions, and repository commit are frozen. No controller may be retuned after confirmation results are inspected.

The intended confirmation design is 30 paired seeds per cell where feasible. Every controller receives the same hidden plant realization. Report median, IQR, bootstrap confidence intervals, success count, failure count, and censored time-to-event analysis. Fit \(A(n)=c n^\alpha\) only across predeclared widths and report uncertainty in \(\alpha\). Two-seed smoke data cannot support a scaling exponent.

## Claim discipline

Allowed after a local confirmation run: “Qiskit Aer simulation,” “measured simulator acquisition count,” “projected physical time at stated \(\tau\),” and “tiled bounded-coupling extension.”

Not allowed without new evidence: physical-QPU drift correction, native device latency, quantum advantage, million-qubit entanglement, fabricated hardware, hosted TrueLoop equivalence, or a universal constant-time controller.
