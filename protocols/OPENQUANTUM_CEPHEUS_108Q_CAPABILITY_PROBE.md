# OpenQuantum Cepheus 108-qubit capability probe

This is a post-failure provider-capability diagnostic, not a QSC-Bench confirmation arm.

The frozen 108-qubit QSC reference passed provider preparation but twice returned `Execution failed after 3 attempts`, with both failed credits refunded. The 36-qubit reference completed. This probe distinguishes failure of full-device allocation from failure of the two-qubit payload circuit.

The probe declares and measures all 108 qubits, applying only the single-qubit sequence `H -> Rz(pi/2) -> H`. It uses 256 shots. Before creation, the quote must be exactly one Spark credit on `Public Plan` and `Standard Queue`; paid Full credits are forbidden.

Interpretation is frozen:

- If the probe fails after successful preparation, full 108-qubit execution is currently unavailable through this provider path. The original failures remain `BLOCKED WITH EVIDENCE`, and the campaign moves to a separately frozen fallback-width ladder.
- If the probe succeeds, full-device allocation works and the failed component is associated with the original payload/compilation path. A separately frozen single-qubit-payload 108-qubit campaign may then be attempted.

No failure is discarded. Nothing is pushed or published without owner approval.
