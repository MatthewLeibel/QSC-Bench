# QSC-Bench v1.0 local confirmation report

Date: 2026-08-14  
Status: complete local campaign; not published, uploaded, or submitted upstream.

## Decision

The frozen finite-range resource-class criterion passed.

Two structurally qualifying controllers—retained residual and fixed-window Anderson—restored the declared monitor contract and independently validated the payload in all 210 primary runs each, spanning 16 to 65,536 controlled channels with 30 paired seeds per width. Neither showed statistically resolved acquisition-depth growth beyond the frozen equivalence margin.

| Controller | Successful runs | Median acquisitions, n=16 | Median acquisitions, n=65,536 | Fitted alpha | Bootstrap 95% CI | Frozen result |
|---|---:|---:|---:|---:|---:|---:|
| Retained residual | 210/210 | 11.5 | 12.0 | 0.0055 | [-0.0064, 0.0123] | PASS |
| Fixed-window Anderson | 210/210 | 11.0 | 11.0 | -0.0023 | [-0.0153, 0.0074] | PASS |

The minimum per-width Wilson lower bound was 0.886 for both. The frozen requirement was at least 0.85. All 30 seeds formed complete successful pairs. The upper confidence limits on alpha, 0.0123 and 0.0074, were below the predeclared 0.05 margin.

This establishes the benchmark's finite-range result. It does not prove universal or asymptotic constant acquisition depth.

## What the result supports

The result supports the architecture more strongly than a controller leaderboard would.

1. Two distinct controllers satisfied the same resource contract. The result is therefore not dependent on one branded equation.
2. Both used one ordinary component-resolved frame per update, retained every applied configuration, discarded no separate cold-start probe, stored bounded state per channel, and performed linear work in width for fixed design constants.
3. Every accepted entry passed a separate payload circuit. Matching the monitor alone was insufficient.
4. Full Aer quantum-circuit runs and a separately validated exact-marginal scale model agreed within frozen validation limits.
5. Out-of-class methods exposed the ceilings predicted by their procedures: coordinate commissioning grew with width, and dense model state grew quadratically.

Within this benchmark, the architecture has done what it was designed to do: remove channel count from the sequential plant-revisit multiplier without pretending that information, total state, local arithmetic, traffic, or physical energy are constant.

## Full Aer core

The exact core used Qiskit Aer density-matrix simulation, finite shots, RZZ coupling, one- and two-qubit depolarizing noise, symmetric readout error, mixed drift, and an entangled mirror payload.

| Controller | n=4 | n=8 | Total |
|---|---:|---:|---:|
| Retained residual | 30/30; median 11 | 30/30; median 11 | 60/60 |
| Diagonal retained secant | 30/30; median 9 | 30/30; median 13.5 | 60/60 |
| Commissioned PI | 30/30; median 8.5 | 29/30; median 12 | 59/60 |
| Fixed-window Anderson | 26/30; median 11 | 27/30; median 13 | 53/60 |
| Do nothing | 0/30 | 0/30 | 0/60 |
| SPSA | 0/30 | 0/30 | 0/60 |
| Oracle, unranked | 30/30 | 30/30 | 60/60 |

Retained residual was the only ranked cold-start candidate that succeeded in every full-Aer run. Diagonal secant also succeeded in every Aer run but later crossed its operability boundary in the large-width plant. This is an important negative result: satisfying the formal state/work class does not guarantee robust control on every member of the plant class.

## Scale-model validation

The large-width backend is not a global-state simulation. It evaluates exact ideal component marginals for the same unitary ring monitor and exact local-mirror payload marginals. Symmetric readout error is exact. Each finite-shot marginal is sampled from its exact binomial distribution; cross-channel shot covariance is omitted.

The frozen validation gate passed:

| Check | Observed | Frozen maximum |
|---|---:|---:|
| Monitor expectation difference | 1.10e-14 | 1e-12 |
| Payload expectation difference | 2.55e-14 | 1e-12 |
| Jacobian difference | 5.90e-7 | 2e-5 |
| Closed-loop success-rate difference | 0.10 | 0.25 |
| Closed-loop median-acquisition difference | 3.5 | 6 |

Ideal expectation checks included width 16. Closed-loop stochastic overlap used widths 8 and 12. A prior development validation at width 4 failed because omitted joint-shot covariance was material at very small width; that failure is retained, and widths 4 and 8 remain in the full Aer core.

## Primary scale campaign

| Width | Retained residual | Anderson | Commissioned PI | Diagonal secant | Do nothing | SPSA |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 30/30; 11.5 | 30/30; 11 | 28/30; 10 | 28/30; 17 | 0/30 | 0/30 |
| 64 | 30/30; 11.5 | 30/30; 11.5 | 26/30; 18 | 26/30; 25.5 | 0/30 | 0/30 |
| 256 | 30/30; 12 | 30/30; 11 | 25/30; 19 | 11/30; 37 | 0/30 | 0/30 |
| 1,024 | 30/30; 12 | 30/30; 11 | 20/30; 22 | 3/30; 36 | 0/30 | 0/30 |
| 4,096 | 30/30; 12 | 30/30; 11 | 26/30; 22.5 | 1/30; 40 | 0/30 | 0/30 |
| 16,384 | 30/30; 12 | 30/30; 11 | 29/30; 23 | 0/30 | 0/30 | 0/30 |
| 65,536 | 30/30; 12 | 30/30; 11 | 30/30; 26 | 0/30 | 0/30 | 0/30 |

Each entry is successes/runs followed by the success-only median acquisition count. Failures were right-censored at 40 acquisitions. The analysis includes censored restricted-mean and Kaplan-Meier fields; the table does not silently replace failures with 40.

Payload margins were positive at every accepted entry. The minimum margin above the payload threshold was 0.000846 for retained residual and 0.00935 for Anderson. The maximum final monitor RMSE among their successful runs remained below the 0.035 threshold.

Commissioned PI is an important strong result, not a straw baseline. It has linear state and arithmetic, and its two coded parallel probes do not create an asymptotic width sweep on this plant. It is excluded only from the stricter retained cold-start class because those probe configurations are discarded. Its non-flat acquisition behavior and intermittent failures are empirical, not a claim that all commissioned PI laws must scale poorly.

## Dense baseline campaign

| Width | Retained residual | Anderson | Full Broyden | Dense finite difference | Charged FD commissioning |
|---:|---:|---:|---:|---:|---:|
| 4 | 30/30 | 30/30 | 30/30 | 28/30 | 5 |
| 8 | 28/30 | 28/30 | 27/30 | 25/30 | 9 |
| 16 | 30/30 | 30/30 | 26/30 | 7/30 | 17 |
| 32 | 30/30 | 30/30 | 23/30 | 0/30 | 33 |
| 64 | 30/30 | 30/30 | 12/30 | 0/30 | 65 |
| 128 | 30/30 | 30/30 | 1/30 | 0/30 | 129 |

The budget was 180 acquisitions, so dense finite difference was not rejected merely because its commissioning could not fit. Its sequential coordinate probes became stale while drift continued. Full Broyden retained ordinary acquisitions, but its dense model became unreliable and expensive.

Measured mutable-state scaling over widths 4–128 was 1.000 in exponent for retained residual and Anderson, 1.852 for full Broyden, and 1.942 for dense finite difference. The exact formulas are:

- retained residual: 6n float64 words = 48n bytes;
- fixed-window Anderson: 16n float64 words = 128n bytes;
- full Broyden: n^2 + 3n float64 words;
- dense finite difference: n^2 + n float64 words.

At n=100 million, either dense matrix alone would require approximately 80 PB in float64. Retained residual would require 4.8 GB and Anderson 12.8 GB. Those linear amounts are not free; they are simply in the same class as the physical interface instead of a re-imported dense model.

The full Broyden implementation uses a regularized direct dense solve with O(n^3) work. The measured host-time exponent over these small, frequently censored runs was 1.35, not 3; the campaign is too small and failure-limited to measure the asymptotic solver exponent. The cubic statement is an algorithmic property of the implemented solve, not a fitted runtime claim.

The reduced model's width-8 candidate failures show why the strong-baseline campaign is not reused as the primary class decision. Small-width joint-shot covariance is outside that model's validated stochastic regime. Resource formulas and charged acquisition counts remain exact; small-width quantum behavior is taken from the Aer core.

## Million-channel extension

After the frozen decision, a separately seeded extension ran at one million channels:

| Controller | Success | Acquisitions | Median host update time | Median process wall time | Mutable state |
|---|---:|---:|---:|---:|---:|
| Retained residual | 5/5 | 12, 12, 12, 12, 12 | 2.20 s | 18.59 s | 48 MB |
| Fixed-window Anderson | 5/5 | 11, 11, 11, 11, 11 | 3.13 s | 18.18 s | 128 MB |
| Oracle, unranked | 5/5 | 3 each | 0.012 s | 4.45 s | 8 MB |
| Do nothing | 0/5 | censored | 0.164 s | 46.41 s | 8 MB |

Peak process RSS reached approximately 731 MiB. This extension supports implementation feasibility at one million channels, but it is not part of the frozen 30-seed inference.

## Time-to-contract consequence

The conservative projections use the worst successful acquisition count observed anywhere in the frozen scale bundle: 20 for retained residual and 33 for Anderson. Dense finite difference uses its exact n+1 commissioning count plus three confirmation acquisitions.

At n=100 million and 100 microseconds per physical acquisition:

| Method | Sequential acquisitions | Acquisition-only time | Acquisition-depth ratio vs retained |
|---|---:|---:|---:|
| Retained residual, no-growth projection | 20 | 2.0 ms | 1x |
| Anderson, no-growth projection | 33 | 3.3 ms | 1.65x |
| Scheduled sweep, 1,024 channels/frame | 97,660 | 9.77 s | 4,883x |
| Dense finite difference | 100,000,004 | 10,000 s = 2.78 h | 5,000,000x |

At n=10 billion and the same latency, dense finite difference reaches 1,000,000 s, or 11.6 days, while the retained acquisition-only term remains 2 ms under the stated no-growth projection. That width is a hypothetical sensitivity point, not an asserted device.

These are acquisition-only numbers. The present serial NumPy implementation is not millisecond end to end. A linear continuation of the largest-width Mac timing gives approximately 167 s of local host work for retained residual at n=100 million. That extrapolation is implementation-specific and may be pessimistic for adjacent parallel hardware or optimistic across memory-system transitions.

The 16-bit monitor-plus-command interface also moves 8.0 GB over 20 retained frames at n=100 million. Finishing a complete 10 ms cycle with 100-microsecond acquisitions would leave 8 ms and require at least 1 TB/s of interface bandwidth, before state traffic and actuation settling. It would also require roughly 2.5e11 channel updates per second. Thus the experiment validates removal of the sequential revisit explosion; it does not validate a universal 10 ms wall clock.

At 65,536 measured channels, retained residual's median host update time was 68.5 ms, Anderson's was 124 ms, and their mutable states were 3 MiB and 8 MiB. The flat quantity is acquisition depth, not serial Mac runtime.

## Metriq status

The local Metriq Gym dispatch/poll smoke passed after the campaign. The adapter returned:

- contract success in 11 acquisitions;
- payload quality 0.9912;
- 6 float words/channel and 192 mutable bytes at width 4;
- 88 charged monitor-plus-command scalars;
- separate host, simulator, and projected acquisition timing; and
- a clean QSC source revision.

This proves local adapter compatibility with the current Metriq workflow. QSC-Bench has not been submitted, reviewed, merged, or accepted by Metriq. Remote adaptive orchestration remains unimplemented.

## Real-QPU addendum

After the simulator result was locked, a separate hardware-transfer protocol was frozen for Quantum Inspire Tuna-9. The campaign used four component monitors, a disjoint four-qubit entangled mirror payload, a five-acquisition deadline, 4,096 shots per acquisition, and three deterministic confirmation seeds.

| Controller | Hardware success | Entry acquisitions | Median provider execution to contract |
|---|---:|---:|---:|
| Retained residual | 3/3 | 4, 4, 4 | 11.942 s |
| Diagonal retained secant | 3/3 | 4, 4, 5 | 12.238 s |
| Commissioned PI | 3/3 | 4, 4, 4 | 11.898 s |
| Dense finite difference | 0/3 | none | -- |
| Do nothing | 0/3 | none | -- |

All 75 confirmation jobs returned every requested shot. The server-side hybrid execution path failed in two retained diagnostics, so the adaptive loop was client-orchestrated with one direct QPU job per acquisition. This preserves causal feedback but includes public-cloud queue and API latency. Provider-reported execution, job wall time, and controller update time are recorded separately. An independent post-campaign reference moved by 0.00962 monitor RMSE and -0.00635 payload bitwise-zero probability; the original target and thresholds were not changed.

This is real-QPU feasibility and deadline evidence at width four. It strengthens transfer of the simulator-derived architecture result but does not independently demonstrate flat hardware scaling or access provider-private calibration registers. The complete local evidence is in `results/hardware/quantum_inspire_tuna9_v1`.

A secondary static check on OpenQuantum/Rigetti Cepheus-1-108Q returned all 1,024 shots, matched the ideal eight-channel marginals at 0.0916 RMSE, and gave the expected direction for 4/4 shifted channels. It consumed 1 free Spark credit and 0 paid credits. Because that job had no adaptive update, it supports cross-provider component-observability portability only. Its local evidence is in `results/hardware/openquantum_static_crosscheck_v1`.

## Negative results and failure boundaries

- Do nothing and scalar-loss SPSA failed every primary scale cell.
- Diagonal retained secant was strong in the exact Aer core but collapsed from 28/30 success at n=16 to 0/30 at n=16,384 and 65,536.
- Commissioned PI remained competitive and recovered to 30/30 at n=65,536, but its paired scaling estimate did not meet the frozen criterion: alpha 0.0947 with 95% CI [0.0644, 0.1322], and only 14 seeds succeeded at every width.
- Full Broyden sometimes matched or beat retained methods at small width. It nevertheless imported quadratic state and degraded to 1/30 at n=128.
- Dense finite difference failed completely from n=32 despite a 180-acquisition budget.
- A development width-4 reduced/full stochastic comparison failed its validation threshold. The result was retained and used to narrow the reduced-model claim.
- The manuscript's recovered classical scale-ladder runner uses eight-neighbor coupling 0.30, while the current supplement describes radius-one coupling 0.20. That manuscript issue remains unresolved and is not hidden by QSC-Bench.

## Scientific interpretation

The frozen campaign achieved the criterion that would make the result larger than “TrueLoop won a benchmark.” It provides controlled simulator evidence for a maintenance resource class: retained, component-resolved, bounded-state, linear-work controllers can preserve payload usability without a width-dependent sequential acquisition multiplier over the tested range, while dense or probe-sweep architectures expose the predicted acquisition, state, or computation ceiling.

That is a strong architecture result and a credible breakthrough candidate.

It is not yet a community-established hardware breakthrough. That stronger status requires independent reproduction, public review, Metriq upstream acceptance or another neutral benchmark venue, and preferably execution against real native drift on physical hardware. The current evidence is simulator-derived, the scale model is marginal rather than global-state, the plant is weakly coupled and diagonally dominant, and the contract uses normalized RMSE rather than a worst-channel guarantee.

## Provenance

- Manuscript package SHA-256: `bcb0d5ddfa01ef609b74a28c5be5ca2cea2478c6beb327a7aeed39e09e64fbe9`.
- Frozen protocol/code commit: `945705d8a55f06e68e85a496607b55c1c2f01b2b`.
- Local tag: `qsc-bench-v1.0-local-freeze`.
- Primary, Aer, dense-baseline, and validation records report that commit and a clean worktree.
- Projection-anchor audit fix: `d3e41288277926ca548858a3046e27414e2734ae`.
- Million-channel extension commit: `016a1614d54affb0cfa25024f962b90e1935d203`.
- Compact-summary generator commit: `d37530c4f7cf9f6773c5837acd7b13981053cfd1`.

The complete machine-readable summary is `results/confirmation/QSC_BENCH_V1_SUMMARY.json`. Raw results, CSV reductions, statistical analyses, validation bundles, projections, and the Metriq smoke record remain local pending owner review.

SHA-256 checksums for the complete local evidence bundle are recorded in `results/confirmation/ARTIFACT_MANIFEST_SHA256.txt`.
