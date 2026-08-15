# Publication checklist

The owner explicitly authorized public release and Metriq submission on
2026-08-14. This checklist distinguishes the completed v1.0 evidence package
from future expansion of the benchmark suite.

## Completed local resource-class confirmation

- [x] Freeze commit, configuration hashes, and deterministic seed derivation recorded before outcome analysis.
- [x] Thirty paired seeds at seven primary widths from 16 through 65,536 channels.
- [x] Full Aer density-matrix core with finite shots, quantum noise, coupling, drift, and independent payload validation.
- [x] Reduced-backend expectation, Jacobian, and closed-loop overlap gates passed before scale inference.
- [x] Strong PI, diagonal secant, Anderson, full Broyden, dense finite-difference, SPSA, do-nothing, and oracle comparators retained.
- [x] Failures preserved as censored outcomes; scaling exponents reported with bootstrap uncertainty.
- [x] Host work, state, interface traffic, simulator time, and assumed physical acquisition latency separated.
- [x] Post-confirmation one-million-channel extension labeled as exploratory rather than frozen inference.
- [x] Local Metriq dispatch/poll smoke completed without claiming upstream acceptance.
- [x] Complete report, machine-readable summary, raw records, reductions, projections, and figures generated locally.

## Completed local real-QPU transfer

- [x] Tuna-9 protocol, sources, source hashes, thresholds, and three confirmation seeds frozen before confirmation outcomes.
- [x] Seventy-five adaptive confirmation jobs completed at 4,096/4,096 shots, with unique provider job IDs and no scientific failure replaced.
- [x] Strong in-class and out-of-class comparators retained; 3/3 and 0/3 outcomes reported without selection.
- [x] Provider execution, provider job wall time, client wall time, and local controller update time separated.
- [x] Independent post-campaign reference recorded without changing the frozen target or threshold.
- [x] Failed server-side hybrid jobs retained as infrastructure evidence; direct-job fallback documented.
- [x] Secondary OpenQuantum/Rigetti portability check quoted before submission and charged only 1 free Spark credit; paid balance remained zero.
- [x] Raw captures, machine-readable summaries, local Metriq-import records, reports, and SHA-256 manifests generated.
- [x] Hardware claims limited to finite-width transfer; simulator scaling remains a separate evidence layer.

The items below concern a broader public suite and external release. They are not prerequisites retroactively imposed on the completed, narrower local resource-class confirmation.

## Required before a broader public-suite freeze

- [ ] User reviews plant, contract semantics, controller tiers, and naming.
- [ ] Add Anderson, RLS/model-based, SPSA, and periodic-recalibration baselines.
- [ ] Implement hold, shock, drift, coupling, shot, noise, correlated-drift, moving-target, breakeven, and application tracks.
- [ ] Define exact-track width limits by measured memory, not aspiration.
- [ ] Verify matrix-product-state results against exact simulation at overlapping widths.
- [ ] Define the tiled extension and prohibit globally-entangled language.
- [ ] Resolve the manuscript scale-ladder mismatch: executed eight-neighbour, c=0.30 protocol versus radius-one, c=0.20 supplement prose.
- [ ] Decide whether the recovered classical scale ladder is a separate QSC scale-extension track or manuscript-only supporting evidence.
- [ ] Decide whether target-generation cost is shared setup or charged per run in each track.
- [ ] Freeze every controller parameter using development seeds only.
- [ ] Add censored time-to-event statistics and bootstrap intervals.
- [ ] Add full run checkpoint/resume and append-only confirmation records.
- [x] MIT selected for the standalone QSC-Bench repository; proprietary runtime
  exclusions and the separate Apache-2.0 Metriq contribution boundary documented.

## Additional gates before an externally released confirmation package

- [ ] Clean unit/static/schema tests pass.
- [ ] Independent review of the monitor's injectivity/capture basin.
- [ ] Independent review of baseline information access and acquisition charging.
- [x] No credentials, evaluation keys, endpoint tokens, personal paths, signed
  result URLs, or job secrets found in tracked files or Git history.
- [ ] Environment lock and container or reproducible build are complete.
- [ ] Obtain independent or higher-powered real-QPU replication before presenting 3/3 as a hardware reliability estimate.
- [x] OpenQuantum attribution is present in the root notice, README, hardware
  report, and each OpenQuantum evidence package.
- [ ] Repository commit and config hashes are frozen.
- [ ] Confirmation-seed derivation is committed before seed generation.
- [ ] No confirmation seed has been inspected during tuning.

## Required before any public claim

- [x] Thirty paired seeds per declared primary simulator cell.
- [x] Every captured failure, timeout, blocked generation, and inadmissible
  reference published with its evidence level.
- [x] Scaling exponent reported with bootstrap uncertainty.
- [x] Large-width claims distinguish frozen reruns, development extensions,
  hash-verified recovered records, and structural projections.
- [x] Simulator runtime separated from projected device latency.
- [x] Projected time curves label every assumed \(\tau\).
- [x] No simulated width described as physical hardware.
- [x] No tiled/reduced width described as global entanglement.
- [x] No local implementation described as hosted TrueLoop equivalence.
- [x] Manuscript reference-code state mismatch disclosed.
- [x] User gave explicit green light to push and publish.
