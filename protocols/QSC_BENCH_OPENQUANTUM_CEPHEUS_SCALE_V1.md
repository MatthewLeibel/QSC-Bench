# QSC-Bench OpenQuantum Cepheus scale extension v1

## Question and scope

This separately frozen extension asks whether the commanded-phase hardware-transfer plant can enter the same declared monitor-and-payload contract at 18 and 54 controlled channels on a real QPU, and whether strong controllers separate under a four-acquisition deadline at the maximum width.

The 54-channel track uses all 108 Cepheus qubits: 54 component monitors and 54 disjoint payload qubits. It is a 54-channel contract, not a 108-channel contract. The disturbance and compensation are explicit phase gates in submitted circuits. Native QPU noise is real and uncontrolled, but the experiment does not access or alter provider-private calibration state. It is therefore a hardware-in-the-loop transfer test of the stability-contract interface, not native device calibration.

OpenQuantum's live catalog on 2026-08-14 listed superconducting and trapped-ion QPUs but no neutral-atom backend. Cepheus-1-108Q was the largest available backend and exposed 108 qubits, a native CZ topology, and a 50,000-shot limit. Its public-compute quote was the least expensive available high-width route.

## Plant

For channel `i`, the hidden effective phase error is

    e_i = d_i + s_i g_i u_i,

where the controller sees neither `d_i`, `s_i`, nor `g_i`. The monitor circuit is

    H -> Rz(pi/2 + e_i) -> H -> Z measurement,

so the ideal response is

    p_i(1) = (1 + sin(e_i)) / 2.

The payload is a shallow mirror circuit on a disjoint qubit. Payload qubits are paired only along native Cepheus CZ edges. Each pair receives local `Ry`, one CZ layer, local `Rx -> Rz(1.25 e_i) -> Rx^-1`, the inverse CZ layer, and inverse `Ry`. At zero commanded error the ideal payload returns to all-zero. The scored workload metric is mean bitwise-zero probability, which remains interpretable at width 54; exponentially small all-zero probability is retained only as a diagnostic.

Each reference and adaptive acquisition uses 2,048 shots. A separate zero-disturbance reference is acquired for each width. Its measured monitor marginals become the immutable target for that width. The payload threshold is

    max(0.70, measured reference bitwise-zero - 0.10).

## Contract and deadline

An ordinary acquisition qualifies when monitor RMSE is at most 0.08 and payload bitwise-zero probability is at least the frozen threshold. Contract entry requires two consecutive qualifying ordinary acquisitions. The deadline is four total sequential acquisitions, including any discarded commissioning probes.

The commanded cold-start shock has exactly 0.45 rad RMS. Gains are log-uniform on `[0.85, 1.15]`; polarities and retained identification signs are hidden independent draws from `{-1,+1}` under the frozen seed. The width-18 and width-54 seeds were derived before hardware outcomes from the SHA-256 seed phrase recorded in the JSON protocol.

## Controllers and resource accounting

The width-18 track runs retained residual. The width-54 maximum track runs retained residual, diagonal retained secant, commissioned PI, and do-nothing on the same frozen scenario.

Retained residual and diagonal secant consume every component-resolved frame as retained state. Commissioned PI pays two separate coded commissioning acquisitions. Do-nothing is the no-maintenance control. Dense finite difference is not submitted: base plus 54 coordinate probes plus two ordinary confirmation frames gives an exact 57-acquisition structural minimum at width 54 (21 at width 18), so it cannot enter a four-acquisition contract. Full dense Broyden is likewise represented by its declared `O(n^2)` state and `O(n^3)` direct-solve implementation rather than spending QPU credits on a resource-class violation.

The one-identification-move hardware profile is an independent manuscript-level implementation. It is not claimed to be bit-identical to the hosted TrueLoop service.

## Rehearsal and freeze rule

Before confirmation, the exact factorized one- and two-qubit blocks are solved locally, sampled at finite shots, and perturbed by symmetric readout noise. Development seeds are disjoint from confirmation seeds. QASM is parsed locally at both widths. Controller constants, thresholds, seeds, layouts, shot counts, deadline, arms, and cost rules are committed before any confirmation result is downloaded.

No threshold or controller constant may change after the first confirmation job is submitted. Failures and negative results remain in the result package.

## Credit and submission controls

Two reference jobs plus twenty adaptive jobs require 22 Spark credits at the inspected one-credit public quote. One of the live account's 23 Spark credits is reserved. Every job must be explicitly prepared and quoted before creation. The runner accepts only `Public Plan`, `Standard Queue`, and a total quote of at most one Spark credit. Full paid-credit balance must remain zero.

The reserve may replace at most one terminal infrastructure failure. If no replacement is needed, it may fund one post-campaign width-54 reference. A connection error after job creation must be reconciled by preparation ID; blind resubmission is prohibited.

## Timing and claims

OpenQuantum cloud wall time includes queue and orchestration delay. The current SDK does not expose a provider execution-duration field for these jobs. It must not be reported as QPU execution time. The report will publish cloud wall time, measured local controller-update time, circuit depth/count proxies, and the parameterized direct-interface function

    T_contract(tau) = A_contract tau + T_host.

Two hardware widths cannot establish a reliable scaling exponent. Success at both widths would support high-width hardware transfer and consistency with bounded acquisition depth; the already frozen simulation campaign and exact resource counts remain necessary for the general scale claim. A failure is published as a failure.

Nothing is pushed to GitHub, uploaded to Metriq, or otherwise published without owner review.
