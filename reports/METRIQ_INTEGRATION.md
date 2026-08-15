# Metriq integration status

Date: 2026-08-14

## Public submission

QSC-Bench v1.0.0 is public at:

https://github.com/MatthewLeibel/QSC-Bench

The benchmark and adaptive-orchestration proposal is open in Metriq Gym:

https://github.com/unitaryfoundation/metriq-gym/issues/803

The provider and hardware-result ingestion proposal is open in Metriq Data:

https://github.com/unitaryfoundation/metriq-data/issues/530

These issues are public submissions for review. QSC-Bench has not yet been merged
into Metriq Gym, and the 17 candidate hardware envelopes are not yet
Metriq-hosted results.

## Current upstream basis

The proposal was checked against Metriq Gym main commit
e7ca8b23d1b50ce47618e69ca400e0d958af8895, dated 2026-08-14. The current
upstream workflow requires a Benchmark/Data/Result implementation, JSON schema,
example configuration, constants and registry entries, tests, and documentation.

The QSC-Bench repository supplies a schema, local Aer adapter, example
configuration, result model, tests, and complete result evidence. The local
adapter has completed dispatch/poll smoke testing. It is intentionally not
represented as an accepted upstream implementation.

## Adaptive-loop limitation

QSC-Bench is causally adaptive. Measurement result p_t is required before command
u_(t+1) can be constructed. A static batch cannot express this dependency.

The local Aer adapter completes the adaptive loop synchronously during dispatch
and stores the finished benchmark payload for normal polling. This is auditable
for local simulation. It is not a satisfactory remote-hardware architecture:
one opaque blocking call would hide intermediate jobs, commands, queue delays,
retries, cancellation state, and checkpoint recovery.

Issue 803 asks Metriq maintainers to select among:

- checkpointable next_batch / consume_result hooks;
- a persisted composite-job state machine advanced by polling; or
- a provider session abstraction for repeated feedback rounds.

An upstream code PR should follow that design decision rather than imposing a
parallel orchestration model that may conflict with Metriq's roadmap.

## Result inventory

The publication index is
results/METRIQ_SUBMISSION_INDEX.json. It identifies 17 candidate hardware
envelopes:

- 15 Quantum Inspire Tuna-9 records from three seeds and five controllers;
- two OpenQuantum Cepheus-1-108Q records from one 48-channel paired seed.

The static Rigetti and IQM Emerald diagnostics and all failed, blocked, pending
at last capture, and reference-inadmissible development campaigns are published
for transparency but are not candidate ranked results.

Every candidate envelope has an underlying public package containing raw
captures, provider job IDs, source hashes, shot counts, controller state,
timings where available, reductions, protocol files, and SHA-256 manifests.

## Why no Metriq Data pull request exists yet

Metriq Data documents that accepted result records must come from supported,
reviewable Metriq Gym execution paths. QSC-Bench is a new benchmark and Quantum
Inspire/OpenQuantum adaptive execution is not yet a supported path. Opening a
data PR before that review would bypass the repository's stated provenance rule.

The compliant sequence is:

1. agree on the adaptive interface in issue 803;
2. submit and merge the benchmark implementation;
3. establish accepted provider or audited import paths through issue 530;
4. revalidate all envelopes against the merged result model;
5. submit provider/result PRs without replacing failures or censored outcomes.

## Timing and claim boundaries

Aer wall time is simulator cost, never physical-QPU latency. Tuna-9 provider
execution time, cloud wall time, and local controller time are separate.
OpenQuantum supplied no device execution-duration field for the Cepheus
confirmation, so cloud submit-to-terminal time is not relabeled as QPU latency.

The hardware records establish finite-width transfer at 4 and 48 controlled
channels. They do not establish a hardware acquisition-depth exponent. The
frozen scaling inference remains simulator/reduced-model evidence.

## License and IP boundary

The standalone QSC-Bench repository is MIT licensed. The public retained-residual
controller is an independent manuscript-level implementation. The hosted
TrueLoop runtime, licensed offline build, credentials, patent drafts, and
unpublished runtime details are absent.

Any contribution merged into Metriq Gym is governed by Metriq Gym's Apache-2.0
terms. The proposed upstream scope is the neutral benchmark and public reference
path, not proprietary runtime code. See IP_AND_DISCLOSURE_BOUNDARY.md.
