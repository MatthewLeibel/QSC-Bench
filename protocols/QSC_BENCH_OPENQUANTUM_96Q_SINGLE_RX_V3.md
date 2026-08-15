# QSC-Bench OpenQuantum 96-qubit single-Rx confirmation v3

## Status and prior failures

This is a prospectively frozen, post-characterization confirmation. It does not replace either blocked 96-qubit workload.

The paired-CZ payload reference was 0.61065 against a frozen 0.70 floor. The five-gate local mirror returned 0.68268 against the same floor. The native `Rx(+pi/2) -> Rz(0) -> Rx(-pi/2)` mirror then returned 0.51337 against a frozen 0.80 floor. Each protocol stopped before its adaptive comparison. Their complete jobs and outputs remain negative evidence.

The native-mirror reference did confirm that the remapped 48-channel monitor surface was admissible: its targets ranged from 0.17090 to 0.66895. This v3 protocol retains that mapping and changes only the unusable payload circuit. The controller constants, shock magnitude, acquisition deadline, and absolute-quality discipline remain unchanged.

## Physical allocation

The circuit declares and uses physical qubits 0--95: 48 component monitors and 48 disjoint payload qubits. The monitor map removes characterized near-flat sites 16, 40, and 43 and replaces them with sites 71, 78, and 85. The payload is the complementary set. The mapping is fixed before the v3 seed is evaluated.

## Plant and shortest error-sensitive payload

For logical channel i,

    e_i = d_i + s_i g_i u_i.

The monitor remains

    H -> Rz(pi/2 + e_i) -> H -> measure.

The payload is

    Rx(3 e_i) -> measure.

At zero error this is the identity. Under the frozen 0.45-radian RMS shock it produces a substantial population error; restoring `e_i` restores the all-zero workload output. The payload is deliberately minimal because two longer circuits failed their nominal hardware reference. It is a shallow local validity proxy, not a claim about deep-algorithm fidelity.

## Frozen admissibility and contract

Before either adaptive arm runs, one 2,048-shot zero-disturbance reference must return exactly 2,048 shots, payload bitwise-zero probability at least 0.80, and every monitor target inside [0.15, 0.85]. Failure blocks the campaign without lowering a threshold.

For an admissible reference, the payload contract is

    payload >= max(0.80, reference - 0.10).

Monitor RMSE must be at most 0.08. Entry requires both conditions for two consecutive ordinary acquisitions within a four-acquisition deadline.

The paired hidden seed is 881723051, derived from the SHA-256 phrase in the JSON protocol and not evaluated during development. Retained residual and do-nothing each receive four acquisitions. Retained residual uses one retained identification action and the manuscript-level constants eta 0.65, momentum 0.15, estimator smoothing 0.50, gain floor 0.15, and identification amplitude 0.150 radians.

At width 48, dense finite difference has an exact structural minimum of 49 commissioning acquisitions plus two confirmation acquisitions, or 51 total. It cannot enter this four-read contract and is not executed. Strong in-class and commissioned baselines remain available in the frozen simulator and Tuna-9 evidence; they are not represented as rerun here.

## Credit and claim guard

Only Public Plan, Standard Queue jobs quoted at no more than one Spark credit are allowed. One reference plus eight adaptive acquisitions uses all nine remaining Spark credits. No Full credits, priority queue, post-reference, or extra-credit retry is authorized.

If retained maintenance passes and do-nothing does not, the result is one high-width hardware transfer consistent with the stability-contract mechanism. It remains a single scenario on a device-characterized mapping and a shallow local payload. It does not establish a hardware scaling exponent, native QPU calibration, a measured cloud speedup, independent replication, or Metriq acceptance. Time-to-contract remains `A_contract * tau + T_host`; queue time is reported separately and never treated as feedback latency.

Nothing is pushed, uploaded, or published without owner review.
