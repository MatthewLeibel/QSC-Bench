# QSC-Bench OpenQuantum 96-qubit native-mirror confirmation v2

## Status and provenance

This is a prospectively frozen, post-characterization confirmation. It is not the original 96-qubit confirmation and must never replace its negative result.

The first paired-CZ payload executed on 96 physical qubits but its zero-disturbance payload reference was 0.61065, below the frozen 0.70 floor. A second local-mirror reference returned 0.68268 and also stopped below its frozen 0.70 floor. That second reference additionally placed physical monitor qubits 16, 40, and 43 at 0.00391, 0.03662, and 0.00000. These sites violate the locally informative operating condition. Both blocked protocols, sources, provider jobs, and outputs remain part of the final evidence.

The completed second reference is used only as development characterization for this v2 design. Before any v2 confirmation outcome is observed, this document freezes the mapping, circuit, controller constants, seed, thresholds, deadline, arms, and credit guard.

## Physical allocation and mapping

The job declares and operates on 96 physical qubits. It contains 48 monitor qubits and 48 disjoint payload qubits. Every declared qubit is used.

The monitor map begins with physical qubits 0--47, removes the three non-informative sites 16, 40, and 43, and adds physical qubits 71, 78, and 85. Those replacements were the three highest bitwise-zero payload sites in the completed characterization. The payload map is the complement inside physical qubits 0--95.

This is a disclosed device-aware mapping, not a random mapping and not an outcome selected from the v2 confirmation.

## Plant and payload

Each logical channel has the same frozen commanded phase error

    e_i = d_i + s_i g_i u_i,

where the confirmation seed fixes the hidden shock, polarity, gain, and retained identification signs. The monitor is the component-resolved Ramsey response

    H -> Rz(pi/2 + e_i) -> H -> measure.

The disjoint payload is a native-gate Ramsey mirror

    Rx(pi/2) -> Rz(3 e_i) -> Rx(-pi/2) -> measure.

At zero commanded error the ideal payload returns zero. The factor of three makes the useful-output proxy sensitive to the declared shock while retaining a short circuit composed only of Cepheus native `rx` and `rz` payload operations. There are no two-qubit gates.

## Reference gate

One 2,048-shot zero-disturbance reference is submitted before any adaptive job. The experiment proceeds only if:

1. exactly 2,048 shots return;
2. mean payload bitwise-zero probability is at least 0.80; and
3. every monitor target lies in the closed interval [0.15, 0.85].

Failure of any condition marks v2 blocked and stops all adaptive submissions. An admissible reference supplies immutable monitor targets. The per-frame payload threshold is

    max(0.80, reference bitwise-zero - 0.10).

## Frozen comparison

The confirmation seed is 1971365805, derived from the SHA-256 phrase recorded in the JSON protocol. It was not evaluated during development.

Retained residual and do-nothing receive four acquisitions each on the same hidden scenario. Contract entry requires monitor RMSE at most 0.08 and payload bitwise-zero at least the frozen threshold for two consecutive ordinary acquisitions. Retained residual uses one retained identification action, then the manuscript-level direct-residual update with eta 0.65, momentum 0.15, estimator smoothing 0.50, gain floor 0.15, and identification amplitude 0.150 radians.

Dense finite difference is not executed. At width 48 it needs 49 commissioning acquisitions plus two ordinary confirmation acquisitions, so its exact structural minimum is 51, outside the four-acquisition deadline. The Tuna-9 hardware campaign and frozen simulator campaign retain the broader PI, retained-secant, Anderson, and model-based comparisons. This credit-bounded run does not claim those methods were rerun at width 48.

## Spending and stopping

Only OpenQuantum Public Plan and Standard Queue jobs priced at no more than one Spark credit are permitted. Full paid credits are forbidden. One reference plus eight adaptive jobs uses nine Spark credits. One Spark credit is reserved only for a verified provider-infrastructure retry. If no retry is needed, it remains unspent. No post-campaign reference is authorized.

## Claim boundary

If retained maintenance enters contract and do-nothing does not, the result is one paired high-width hardware-transfer observation consistent with the stability-contract architecture. It is not by itself a hardware scaling exponent, a measured large-width time-to-solution speedup, native QPU calibration, an independent replication, or a Metriq-reviewed result. Provider queue time is not physical feedback latency. The system-level time remains the parameterized quantity `A_contract * tau + T_host`.

Nothing is pushed, uploaded to Metriq, or published without owner review.
