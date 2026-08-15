# Developmental smoke-test report

Run date: 2026-08-13. Status: development / not for publication.

## What passed

- Submission archive: 41/41 manifested hashes match.
- Original reproduction tests: 11/11 pass.
- QSC-Bench local unit and adapter tests: 13/13 pass after adding the manuscript certificate, resource-class audit, architecture projection, and Metriq adaptive-adapter checks.
- Monitor interface: one noisy shot batch returns every component.
- Primary plant at 4 qubits: minimum nominal diagonal Jacobian magnitude about 0.447 and maximum row off-diagonal/diagonal ratio about 0.127 for the inspected seed.
- Retained-controller state: exactly six mutable float64 arrays, or six words/channel in abstract word accounting; the immutable identification sign is separate.
- Local adaptive runner: completes and writes JSON plus CSV.
- Metriq local path: dispatch, persistence, poll, and JSON export complete successfully.

## Defect found and corrected

The first monitor design put the physical angle on a low central angle range. It had nonzero local derivatives at the nominal point but admitted a second fringe-equivalent root inside the reachable region. In one seed, controllers achieved monitor RMSE below tolerance with hidden phase RMS near 0.4–0.6 radians. The mirror payload returned only about 0.65–0.80 and correctly refused contract entry.

This exposed an observability/capture-basin failure, not an energy or controller anomaly. The primary track was corrected to put the controlled phase on an \(R_Z\) fringe centered near \(\pi/2\), with a fixed \(R_Y\) tilt that preserves neighbor-dependent RZZ coupling. The persistent cold-start offset was also moved from the mean-reverting state into the slow state so do-nothing cannot improve by passive reset.

The original ambiguous-fringe results were overwritten only in the development output file; their diagnosis is retained here. A frozen benchmark must preserve every confirmation result, including failures.

## Final local smoke matrix

Two development seeds were run at 4 and 8 qubits, 1,024 shots/acquisition, 8,192 reference shots, three-pass confirmation, a separate payload threshold, and a 24-monitor-acquisition budget.

| Width | Controller | Successes | Median verified acquisitions | Range |
|---:|---|---:|---:|---:|
| 4 | retained residual | 2/2 | 11.5 | 10–13 |
| 4 | diagonal secant | 2/2 | 14.0 | 7–21 |
| 4 | commissioned PI | 2/2 | 15.0 | 14–16 |
| 4 | dense finite difference | 2/2 | 14.5 | 12–17 |
| 4 | do nothing | 0/2 | — | timeout |
| 4 | oracle, unranked | 2/2 | 3.0 | 3–3 |
| 8 | retained residual | 2/2 | 14.5 | 13–16 |
| 8 | diagonal secant | 2/2 | 21.0 | 19–23 |
| 8 | commissioned PI | 2/2 | 16.5 | 15–18 |
| 8 | dense finite difference | 2/2 | 21.0 | 21–21 |
| 8 | do nothing | 0/2 | — | timeout |
| 8 | oracle, unranked | 2/2 | 3.0 | 3–3 |

These values include commissioning and three consecutive confirmation measurements. They are therefore not directly comparable to the manuscript's “first crossing in four to five acquisitions” metric. With only two seeds and two widths, they do not establish flat scaling or a speedup exponent. They do show that the adaptive contract logic, baseline charging, payload validation, failure handling, and machine-readable accounting work end to end.

## Metriq smoke record

Metriq Gym job `0d9ff0c3-46f5-4b7e-9ad1-55245bfeca1a` ran the 4-qubit, 256-shot development configuration through `local:aer_simulator` from clean QSC code commit `5a47cabdbc30eeb1dbd3261a5ab7582bc68a2f09`. The exported record reports:

- contract success: true;
- verified acquisitions to contract: 11;
- payload quality: 0.9912109375;
- total quantum executions to usability: 12, including payload validation;
- full-vector monitor width: 4 values; local monitor-plus-actuation frame: 8 values/cycle;
- retained state: six float words/channel, 192 implementation bytes at width 4;
- simulator runtime: 0.1378 s;
- host update time: 0.00304 s;
- projected time at the declared 1 ms acquisition latency: 0.0140 s;
- score: 1/11.

The simulator reports 29 available qubits and Aer 0.17.2. This is proof of software integration, not evidence about a 29-qubit benchmark result or a physical device.

## Interpretation

The smoke outcome is encouraging but not “breakthrough evidence.” Retained residual is the most consistent ranked method in this tiny matrix, while diagonal secant wins one 4-qubit seed and is substantially more variable. Commissioned PI remains competitive. Dense finite difference pays increasing commissioning cost and still succeeds at these small widths. Those are precisely the regimes the full benchmark must map.

No confirmation seeds have been generated or run. No public claim should be made from these numbers.
