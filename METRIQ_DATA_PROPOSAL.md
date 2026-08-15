# Metriq Data proposal: QSC-Bench hardware ingestion

This issue requests guidance and eventual support for QSC-Bench result ingestion
from Quantum Inspire and OpenQuantum. It is intentionally not a data pull
request.

The benchmark and adaptive orchestration proposal is tracked in
unitaryfoundation/metriq-gym#803:

https://github.com/unitaryfoundation/metriq-gym/issues/803

The public v1.0 package contains 17 candidate Metriq result envelopes:

- 15 Quantum Inspire Tuna-9 records: three seeds by five controllers, backed by
  75 adaptive direct-QPU jobs at 4,096 shots each;
- two OpenQuantum Rigetti Cepheus-1-108Q records: retained residual and
  do-nothing at 48 controlled channels on 96 physical qubits, backed by eight
  completed jobs including the shared reference.

Submission inventory:
https://github.com/MatthewLeibel/QSC-Bench/blob/main/results/METRIQ_SUBMISSION_INDEX.json

Hardware evidence index:
https://github.com/MatthewLeibel/QSC-Bench/blob/main/results/hardware/HARDWARE_EVIDENCE_INDEX.json

Every envelope links to a public package containing raw captures, provider job
IDs, source hashes, shot counts, frozen protocols, reductions, and SHA-256
manifests. Simulator runtime, provider execution time, cloud wall time, local
controller time, and parameterized latency projections are separated. The
OpenQuantum provider did not expose device execution duration for the Cepheus
jobs, and that field is therefore unavailable rather than inferred from queue
time.

The repository also publishes static diagnostics and failed, blocked, pending at
last capture, and reference-inadmissible development campaigns. Those are not
proposed as ranked Metriq results.

Under the metriq-data contribution policy, I will not open a result-data PR
before QSC-Bench and its provider execution path are supported in Metriq Gym.
After issue 803 is resolved, I propose to:

1. regenerate or validate all envelopes against the accepted result model;
2. establish the accepted provenance/import path for client-orchestrated
   adaptive provider jobs;
3. submit Quantum Inspire and OpenQuantum records in separate reviewable PRs;
4. retain all failures and censored outcomes without replacement.

Questions:

1. Should these providers be added to Metriq Gym/qBraid before any data PR, or
   can an audited external adaptive import path be supported?
2. What device metadata is required when provider execution duration is
   unavailable?
3. Should the single-seed 48-channel Cepheus result be admitted with its explicit
   limitation, or held until independent replication?
