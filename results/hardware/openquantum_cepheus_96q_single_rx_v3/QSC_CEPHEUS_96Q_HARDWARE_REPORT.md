# QSC-Bench Cepheus 96-physical-qubit confirmation

The retained-residual arm restored the frozen joint monitor-plus-payload contract
by acquisition 4. It passed on acquisitions 3 and 4, with monitor RMSE 0.06213
and 0.06187 and payload bitwise-zero quality 0.89196 and 0.90450. The paired
do-nothing arm failed its first three acquisitions; acquisition 4 was not run
after two consecutive deadline passes became mathematically impossible.

The run used 48 controlled channels distributed across 96 physical qubits,
2,048 shots per acquisition, one frozen confirmation seed, and eight completed
provider jobs including the shared reference. A dense finite-difference cold
start would require at least 51 sequential acquisitions under the declared
charging rule, so it was structurally outside the four-acquisition deadline and
was not executed.

This is real-QPU command-restoration evidence, not a hardware scaling result.
The disturbance was commanded in the submitted circuit; the experiment did not
read or repair private provider calibration state. OpenQuantum did not expose
device execution duration for these jobs, so cloud queue/wall time is not
reported as QPU latency. The single seed and shallow single-Rx payload require
independent replication before any reliability or generality claim.

Powered by OpenQuantum. See https://www.openquantum.com/citation.
