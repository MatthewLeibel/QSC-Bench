# QSC-Bench OpenQuantum 96-qubit local-payload confirmation v1

## Motivation

The preregistered executable-width ladder found that the paired-CZ QSC circuit executes at 96 physical qubits. Its nominal payload reference, however, returned only 0.61065 mean bitwise-zero probability, below the unchanged 0.70 workload-usability floor. That track is blocked before controller comparison: a stability controller cannot be credited with restoring a workload whose nominal hardware reference does not meet the declared contract.

This final credit-bounded confirmation keeps the 48 component monitors, 48 disjoint payload qubits, phase plant, controller constants, shock, shots, tolerance, and four-acquisition deadline. It removes only the two CZ layers from the payload. The resulting payload is still a nontrivial local mirror:

    Ry(a_i) -> Rx(b_i) -> Rz(1.25 e_i) -> Rx(-b_i) -> Ry(-a_i).

At zero phase error it is the identity; nonzero commanded error perturbs workload output. This tests whether component-resolved phase restoration also restores an executable useful-output proxy without asking noisy 96-qubit hardware to pass a two-qubit workload it cannot satisfy at nominal calibration.

## Precondition

The 2,048-shot zero-disturbance reference must itself have payload bitwise-zero probability at least 0.70. If it does not, the experiment stops before any adaptive job and is marked blocked. The monitor marginals from an admissible reference become the immutable component targets. The payload threshold remains

    max(0.70, reference bitwise-zero - 0.10).

This precondition is frozen before the reference is submitted.

## Arms and accounting

The paired confirmation seed is derived from the SHA-256 phrase in the JSON protocol. Retained residual and do-nothing each receive four acquisitions on the same hidden scenario. Contract entry requires monitor RMSE at most 0.08 and payload score at least the frozen threshold for two consecutive ordinary frames.

Dense finite difference requires 49 commissioning frames plus two confirmation frames at width 48, so its exact structural minimum is 51 and it cannot enter the four-read contract. The earlier Tuna hardware campaign and frozen simulator campaign retain commissioned PI and retained secant comparisons. This reduced final matrix does not pretend those baselines ran again; it spends the remaining credits on the clearest real-hardware maintenance-versus-no-maintenance contrast.

One reference plus eight adaptive jobs costs nine Spark credits. One credit is reserved for a verified infrastructure retry or, if unused, a post-campaign reference. At least one Spark credit remains unspent. Only public compute and standard queue are allowed; Full paid credits are forbidden.

## Claim boundary

Success would show one 48-channel commanded-phase hardware-transfer scenario in which a bounded retained controller restores both a component monitor and disjoint local workload within four acquisitions while no maintenance does not. It would not establish a hardware scaling exponent, native calibration access, population-level reliability, or Metriq acceptance. Every failed 108-qubit and paired-payload result remains in the evidence package.

Nothing is pushed or published without owner review.
