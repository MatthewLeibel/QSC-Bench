# QSC-Bench

QSC-Bench is a neutral benchmark for maintaining drifting hybrid quantum
systems. It asks how many sequential plant interactions, how much host work,
and how much interface traffic are required to restore a finite-shot quantum
plant to a declared operating contract and make an independent payload usable.

TrueLoop retained residual is one controller in the suite. The implementation
here is an independent manuscript-level reference, not the proprietary hosted
TrueLoop runtime and not a claim of bitwise equivalence to it.

This repository is the QSC-Bench v1.0.0 public evidence package and the source
for the benchmark proposal submitted to Metriq Gym.

## What was established

The frozen primary simulator campaign contains 1,470 paired records across
seven widths from 16 through 65,536 channels and 30 confirmation seeds per
width. Retained residual and fixed-window Anderson each passed 210/210 trials.
Their fitted acquisition-depth exponents were 0.0055 (95% bootstrap CI
[-0.0064, 0.0123]) and -0.0023 ([-0.0153, 0.0074]), below the predeclared 0.05
upper-confidence limit. Every success required both the component monitor and
an independent payload to pass for three consecutive ordinary acquisitions.

The full Aer core produced 60/60 retained-residual successes at 4 and 8 qubits.
A separately validated exact-marginal ring backend supports the larger-width
inference; the 65,536-channel result is not represented as a globally entangled
65,536-qubit simulation. A labeled implementation extension reached one million
channels in 5/5 runs for each qualifying controller. That extension is
development evidence, not part of the frozen 30-seed inference.

Strong baselines were retained. Dense finite difference exposed its charged
`n+1` commissioning depth. Full Broyden exposed quadratic state and dense-solve
cost. Diagonal retained secant and commissioned PI provide important boundary
results: methods other than retained residual can win individual cells or meet
short deadlines when their information and commissioning assumptions permit it.
The architectural result concerns resource classes, not a branded controller
winning every comparison.

## Real-QPU evidence

Two adaptive hardware campaigns and two static diagnostics are published with
raw captures, source hashes, job identifiers, reductions, and negative evidence.

| Provider / device | Scope | Result | Claim limit |
|---|---|---|---|
| Quantum Inspire Tuna-9 | 4 controlled channels, 3 seeds, 75 adaptive jobs | Retained residual, diagonal secant, and commissioned PI passed 3/3; dense finite difference and do-nothing passed 0/3 | Finite-width transfer, not hardware scaling |
| OpenQuantum Rigetti Cepheus-1-108Q | 48 controlled channels on 96 physical qubits, 1 seed, 8 jobs | Retained residual entered the joint contract at acquisition 4; do-nothing failed | Single-seed command-restoration evidence, not a scaling exponent |
| OpenQuantum Rigetti Cepheus-1-108Q | One 8-channel static monitor acquisition | Portability rule passed | Not adaptive control |
| OpenQuantum IQM Emerald | One 54-qubit static paired diagnostic | Corrected-minus-unmaintained bitwise-zero score = 0.21448 | Not a stability-contract result |

The Cepheus confirmation used 2,048 shots per acquisition. Retained residual
passed acquisitions 3 and 4 with monitor RMSE 0.06213 and 0.06187 and payload
quality 0.89196 and 0.90450. The shared reference payload was 0.90698 and the
frozen payload threshold was 0.80698. A dense finite-difference cold start had a
51-acquisition structural minimum under the declared charging rule, so it was
outside the four-acquisition deadline and was not executed.

The hardware disturbance was commanded in submitted circuits. No provider-private
calibration register was read or repaired. OpenQuantum did not expose device
execution duration for the Cepheus jobs, so cloud queue/wall time is not treated
as QPU latency. The single Cepheus seed requires independent replication before
any hardware reliability claim.

Failed, blocked, and inadmissible OpenQuantum generations are preserved in
`results/hardware/openquantum_development_evidence`; they are not silently
discarded or included in the successful v3 claim.

Powered by OpenQuantum. Attribution guidance:
<https://www.openquantum.com/citation>.

## What “flat” means

One monitor acquisition is one configured quantum circuit, one finite shot
batch, and one simultaneous vector of all channel marginals. Commissioning
acquisitions count. Failed runs are censored failures, not last-value successes.
Reference-target generation is shared benchmark setup and is reported separately
from controller cold-start cost.

“Flat” refers only to sequential acquisition depth. Full-vector traffic, host
arithmetic, total state, sensor count, actuator count, and physical energy are
not constant in channel count. The systems metric is

\[
T_{\mathrm{contract}}(\tau)
= A_{\mathrm{contract}}\tau + T_{\mathrm{host}},
\]

reported over explicit acquisition-latency assumptions. Aer runtime is simulator
cost; it is never reported as physical QPU latency.

## Evidence map

- `reports/QSC_BENCH_V1_CONFIRMATION_REPORT.md`: frozen simulator result,
  uncertainty, strong baselines, projections, and negative results.
- `results/confirmation/QSC_BENCH_V1_SUMMARY.json`: compact machine-readable
  index of the confirmation bundle.
- `reports/HARDWARE_TRANSFER_REPORT.md`: combined real-QPU interpretation and
  claim boundary.
- `results/hardware/HARDWARE_EVIDENCE_INDEX.json`: machine-readable hardware
  evidence map.
- `results/hardware/quantum_inspire_tuna9_v1`: complete three-seed adaptive
  Tuna-9 package and 15 candidate Metriq envelopes.
- `results/hardware/openquantum_cepheus_96q_single_rx_v3`: complete 48-channel
  Cepheus package and two candidate Metriq envelopes.
- `results/hardware/openquantum_iqm_emerald_command_effect_v1`: static Emerald
  diagnostic.
- `results/hardware/openquantum_development_evidence`: failed, blocked, pending,
  and inadmissible OpenQuantum captures.
- `results/METRIQ_SUBMISSION_INDEX.json`: exact Metriq submission inventory.
- `reports/MANUSCRIPT_REVIEW.md`: claim, mathematics, evidence, and implementation
  audit against the source manuscript.
- `protocols/QSC_BENCH_V1_LOCAL_FREEZE.md`: immutable confirmation design, seed
  derivation, evidence layers, and pass/fail rules.

## Reproduction

QSC-Bench requires Python 3.12 or 3.13. Create the lean local environment with:

```sh
./scripts/bootstrap_local.sh
.venv/bin/python -m pytest -q
```

Run the smallest finite-shot smoke campaign:

```sh
.venv/bin/python -m qsc_bench.cli diagnose-plant \
  --config configs/smoke.json --width 4

.venv/bin/python -m qsc_bench.cli run \
  --config configs/smoke.json \
  --output results/development/smoke_results.json
```

Rebuild and verify the public OpenQuantum packages from the ignored local
checkpoints:

```sh
.venv/bin/python scripts/build_openquantum_hardware_release.py
```

The architecture projection keeps measured anchors, procedural lower bounds,
and hypothetical no-growth extrapolations separate:

```sh
.venv/bin/python -m qsc_bench.cli project-architecture \
  --measured-results results/development/smoke_results.json \
  --output results/development/architecture_projection.json
```

## Metriq status

The repository contains a QSC benchmark schema, a local Aer adapter, 17
hardware candidate result envelopes, and every underlying result package. The
local adapter completed dispatch/poll smoke tests.

Public review is open in
[Metriq Gym issue 803](https://github.com/unitaryfoundation/metriq-gym/issues/803)
and [Metriq Data issue 530](https://github.com/unitaryfoundation/metriq-data/issues/530).

QSC-Bench is adaptive: measurement result `p_t` is required before command
`u_(t+1)` can be constructed. Metriq's current remote execution paths are
batch-oriented, so hardware ingestion requires an upstream adaptive state-machine
design. The benchmark proposal is therefore submitted to Metriq Gym first.
Under Metriq Data's documented policy, provider result records are submitted only
after the benchmark and execution path are accepted. A public result package is
not described as a Metriq-hosted result until that merge occurs.

See `reports/METRIQ_INTEGRATION.md` for the exact upstream sequence and
`results/METRIQ_SUBMISSION_INDEX.json` for the records awaiting ingestion.

## License and IP boundary

The files in this repository are MIT licensed. The hosted TrueLoop runtime,
licensed offline build, credentials, patent drafts, and unpublished service
implementation are excluded. See `NOTICE` and `IP_AND_DISCLOSURE_BOUNDARY.md`.

Contributions accepted into Metriq Gym are governed by Metriq Gym's Apache-2.0
license and contribution terms. The repository records the technical disclosure
boundary, but patent and license strategy should still be reviewed by qualified
counsel.
