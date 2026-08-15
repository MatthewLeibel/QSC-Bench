# Metriq proposal: QSC-Bench

## Summary

QSC-Bench is a neutral time-to-contract benchmark for stateful hybrid quantum
systems. It measures how quickly, and with what host resources and interface
traffic, a controller restores a drifting finite-shot quantum plant to a
declared component-level contract and makes a separate payload usable.

The benchmark is controller-neutral. TrueLoop retained residual is one method
alongside do-nothing, commissioned PI, retained diagonal secant, fixed-window
Anderson, SPSA, dense finite difference, full Broyden, and an unranked oracle.
Results expose information access, commissioning cost, sequential acquisition
depth, host arithmetic, mutable state, traffic, and payload validity.

Public implementation and complete evidence:
https://github.com/MatthewLeibel/QSC-Bench

## Benchmark question

Given a drifting component-observable quantum plant, how many sequential plant
acquisitions, how much host computation, how much mutable state, and how much
interface traffic are required to enter and confirm a declared operating
contract?

One acquisition is one configured circuit, one finite-shot batch, and one
simultaneous vector of all monitored component marginals. Commissioning probes
are charged. A run enters contract only after consecutive ordinary acquisitions
meet the monitor tolerance and an independent payload meets its usability
threshold.

The primary systems metric is acquisitions to contract. The parameterized
time-to-contract curve is T_contract(tau) = A_contract tau + T_host. Simulator
runtime and assumed physical acquisition latency are separate fields.

## Public v1.0 evidence

The frozen primary campaign contains 1,470 paired records over widths 16 through
65,536 with 30 confirmation seeds per width. Retained residual and fixed-window
Anderson each passed 210/210 trials. Their fitted acquisition-depth exponents
were 0.0055 (95% bootstrap CI [-0.0064, 0.0123]) and -0.0023
([-0.0153, 0.0074]). The exact Aer core contains 60/60 retained-residual
successes at 4 and 8 qubits. The larger-width backend is an independently
validated exact-marginal sparse ring model, not a globally entangled
65,536-qubit simulation.

The public hardware evidence includes:

- Quantum Inspire Tuna-9: 75 adaptive jobs, four controlled channels, three
  seeds. Retained residual, diagonal retained secant, and commissioned PI passed
  3/3; dense finite difference and do-nothing passed 0/3.
- OpenQuantum Rigetti Cepheus-1-108Q: one paired seed, 48 controlled channels on
  96 physical qubits. Retained residual entered the joint contract at
  acquisition 4; do-nothing failed.
- Separate static diagnostics on Rigetti Cepheus and IQM Emerald.
- Failed, blocked, pending-at-last-capture, and reference-inadmissible campaigns
  preserved as negative/development evidence.

These hardware results establish finite-width transfer, not a hardware scaling
exponent. The disturbances were commanded in submitted circuits; no
provider-private calibration state was accessed.

Evidence index:
https://github.com/MatthewLeibel/QSC-Bench/blob/main/results/hardware/HARDWARE_EVIDENCE_INDEX.json

Metriq submission inventory:
https://github.com/MatthewLeibel/QSC-Bench/blob/main/results/METRIQ_SUBMISSION_INDEX.json

## Proposed Metriq contribution

The repository contains:

1. a JSON schema for QSC-Bench Cold Start;
2. a local Aer adapter implementing the current dispatch/poll interface;
3. benchmark and result models with explicit architecture-accounting fields;
4. a small example configuration;
5. unit and local dispatch/poll tests;
6. 15 Tuna-9 and two Cepheus candidate Metriq result envelopes.

The proposed fields include width, contract success, acquisitions to contract,
total quantum executions to usable output, payload quality, monitor values per
acquisition, monitor-plus-actuation values per cycle, traffic to contract,
mutable controller bytes, words per channel, resource-class candidacy, host
update time, simulator time, and projected time-to-contract at a declared
latency.

## Adaptive orchestration question

QSC-Bench is causally adaptive: measurement result p_t is needed before command
u_(t+1) can be constructed. The current Metriq remote flow is batch-oriented.
The local adapter can complete the adaptive Aer loop during dispatch, but an
opaque blocking call for remote hardware would lose intermediate provenance and
make queue, retry, and cancellation behavior difficult to audit.

Before opening a code PR that changes orchestration, I would like maintainer
guidance on one of these designs:

- checkpointable next_batch / consume_result benchmark hooks;
- a persisted composite-job state machine advanced by polling; or
- a provider session interface for repeated feedback rounds.

Whichever route is preferred should preserve every provider job ID, measurement,
command, retry, queue interval, cancellation, and controller update.

## Proposed upstream sequence

1. Agree on the adaptive state-machine interface and result schema in this issue.
2. Submit benchmark code, schema, example, tests, and documentation to
   metriq-gym from its current main branch.
3. Add reviewed provider execution paths.
4. Revalidate candidate envelopes against the accepted result model.
5. Open provider/result-ingestion issues in metriq-data.
6. Upload result PRs only through accepted execution paths.

This ordering follows the Metriq Data requirement that published results come
from supported, reviewable Metriq Gym paths. The public files are candidate
envelopes, not claimed to be Metriq-hosted results.

## Reproduction and integrity

The release passes 46 unit tests; one optional Metriq integration test skips when
Metriq Gym is absent. The publication verifier parses 94 JSON files, verifies
five SHA-256 manifests covering 72 artifacts, and checks all 17 candidate Metriq
envelopes.

Run scripts/bootstrap_local.sh, then:

    .venv/bin/python scripts/verify_publication.py
    .venv/bin/python -m unittest discover -s tests -q

## License and disclosure boundary

The standalone repository is MIT licensed. It includes the neutral benchmark,
baselines, public plant models, results, and an independent manuscript-level
retained-residual reference controller. It excludes the proprietary hosted
TrueLoop runtime, licensed offline build, credentials, patent drafts, and
unpublished implementation details.

I understand that accepted contributions to Metriq Gym are governed by
Metriq Gym's Apache-2.0 terms. The intended upstream contribution is the
benchmark and public reference path, not proprietary runtime code.

Disclosure boundary:
https://github.com/MatthewLeibel/QSC-Bench/blob/main/IP_AND_DISCLOSURE_BOUNDARY.md

## Maintainer questions

1. Is QSC-Bench in scope as a systems benchmark for stateful hybrid quantum
   execution?
2. Which adaptive orchestration design best fits Metriq Gym?
3. Should controller identity and resource-class fields remain benchmark result
   fields, or move partly into suite/platform metadata?
4. After benchmark acceptance, should Quantum Inspire and OpenQuantum ingestion
   be handled as provider additions, external-result import paths, or both?
