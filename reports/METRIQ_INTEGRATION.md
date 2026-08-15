# Metriq integration status

## Installed environment

- Python 3.13.7, macOS 12.7.6 x86_64
- Qiskit 2.5.2
- Qiskit Aer 0.17.2
- Metriq Gym editable version `0.0.1.dev2+g69e28cd55`
- Metriq Gym upstream base `3b4c355d09001ac34c4b499564207e57079ebf2a` dated 2026-08-11
- Local integration branch `qsc-local-adaptive` at `69e28cd`
- QSC-Bench 0.1.0.dev0

The published `metriq-gym` wheel was not usable as a lean local installation because it imported cloud-provider job classes at CLI startup and declared the complete provider/benchmark stack as mandatory dependencies. The current upstream checkout was installed editable. A compatible binary `cryptography` wheel and Qiskit IBM Runtime were installed solely to satisfy the import path; no account or credential was configured.

## Local integration branch

The local integration branch currently:

1. add `QSC-Bench Cold Start` to `JobType` and schema mapping;
2. add a flat Metriq schema;
3. add a QSC benchmark/result/data adapter;
4. make provider-job imports optional for local CLI startup;
5. make benchmark registry imports tolerant of unavailable optional stacks;
6. use a local-Aer-only device helper to avoid installing unrelated cloud SDKs.
7. expose the architectural accounting fields in the Metriq result: width, verified acquisitions, total quantum executions, values per full-vector acquisition, local monitor-plus-actuation frame size, traffic to contract, controller state, words per channel, resource-class candidacy, and projected time at an explicitly declared acquisition latency.

The local-only replacement of `qplatform/device.py` is an environment shim, not a patch suitable for upstream review. Before a PR, it must be reconciled with upstream through conditional provider registration so no existing provider support is removed.

The complete Metriq provider dependency set is intentionally not installed on this disk-constrained machine. `pip check` therefore reports missing Amazon Braket, dimod, PyQPanda, pytket-qiskit, Qiskit Experiments, and qBraid provider extras. The tested scope is the local Aer/QSC path only; the environment must not be described as a validated full-provider Metriq installation.

## Adaptive-loop limitation

Metriq's benchmark interface exposes `dispatch_handler(device)` followed later by `poll_handler(job_data, results, jobs)`. QSC-Bench needs measurement result \(p_t\) before it can construct command \(u_{t+1}\). A static batch cannot express this dependency.

The draft adapter therefore runs the adaptive Aer loop synchronously inside `dispatch_handler`, stores the completed QSC payload in `BenchmarkData`, and lets normal polling convert it to a `BenchmarkResult`. This is correct for local Aer and was tested end to end. It is not a satisfactory remote-hardware design because dispatch can block across many queue/measurement/update cycles.

An upstream-quality contribution should add one of:

- an adaptive benchmark protocol with checkpointable `next_batch` and `consume_result` hooks;
- a composite job abstraction whose state machine Metriq persists between polls; or
- a provider session abstraction for repeated low-latency feedback.

The design must preserve every provider job ID, intermediate result, command, retry, queue delay, and cancellation state. A single opaque synchronous remote call would be difficult to audit and should not be proposed as final architecture.

## Real-hardware transfer

The first physical-QPU campaign was therefore orchestrated outside Metriq while preserving a Metriq-ready result envelope. Quantum Inspire's server-side hybrid job path failed on Tuna-9 in two recorded diagnostics, although it worked on the emulator. The fallback submitted each next circuit as a direct Tuna-9 job only after consuming the previous result. Every provider job ID, histogram, source hash, shot count, controller update, queue/API interval, provider execution time, retry, and resume event is retained.

The frozen confirmation campaign comprised three seeds, five arms, five sequential acquisitions, and 4,096 shots per acquisition: 75 QPU jobs in total. Retained residual, diagonal retained secant, and commissioned PI each passed in 3/3 seeds; dense finite difference and do-nothing passed in 0/3. Retained residual entered contract on acquisition 4 in all three seeds. The package at `results/hardware/quantum_inspire_tuna9_v1` includes 15 native Metriq result envelopes. All validate against the installed `QSCColdStartResult` model and preserve the hardware platform and provider-job provenance in device metadata. They have not been uploaded and are not represented as accepted Metriq results.

This hardware result tests adaptive finite-width transfer at four monitored channels. It cannot establish width-independent acquisition depth on hardware. The width result remains the frozen simulator campaign, and the two evidence layers must remain separate in any submission.

A separately frozen OpenQuantum public-compute check ran one 1,024-shot circuit on Rigetti Cepheus-1-108Q. It returned eight component marginals with RMSE 0.0916 against the ideal circuit and all four declared phase shifts had the correct response direction. The quote and final balance prove that it used 1 Spark credit and no paid Full credits. This only cross-checks monitor portability on a second provider; it is not adaptive-control evidence. Any public release must include the attribution requested at https://www.openquantum.com/citation.

## Verified command path

The following completed successfully:

```sh
mgym job dispatch integration/metriq_gym/configs/metriq_smoke.json \
  -p local -d aer_simulator

mgym job poll 0d9ff0c3-46f5-4b7e-9ad1-55245bfeca1a \
  --json results/development/metriq_smoke_result.json
```

The exported JSON uses Metriq's standard result envelope and includes benchmark score, platform metadata, resource accounting, and a labeled 1 ms/acquisition projection. It reports 11 verified acquisitions, 12 total quantum executions including payload validation, four monitor values per acquisition, eight local monitor-plus-actuation values per cycle, six controller words per channel, and payload quality 0.9912. The projected time is not Aer runtime and is not a hardware measurement.

## Upstream sequence

Nothing has been pushed or opened upstream. After user approval, the safe sequence is:

1. complete all v1 controllers and tracks;
2. freeze the schema and statistical protocol;
3. add adaptive orchestration without regressing existing providers;
4. run Metriq's full test suite in a sufficiently provisioned environment;
5. open a design discussion before a code PR;
6. run confirmation only from the reviewed commit;
7. archive code/results with a DOI;
8. submit the benchmark PR and methods note.
