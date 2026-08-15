# QSC-Bench OpenQuantum executable-width extension v1

## Why this extension exists

The frozen 54-channel/108-physical-qubit reference passed OpenQuantum preparation but failed twice after three provider execution attempts per job. A separately frozen 108-qubit diagnostic containing only single-qubit gates and measurement failed the same way. All three failed jobs produced no counts and were refunded. The 18-channel/36-qubit QSC reference completed.

This is evidence that the current public path cannot execute full-device jobs. It is not evidence against the controller, because no 108-qubit measurement reached any controller. The failed jobs remain part of the final record.

## Frozen executable-width ladder

The fallback is selected before observing any further QPU output. The QSC reference circuit is attempted at controlled widths

    48, 42, 36, 30, 24,

corresponding to

    96, 84, 72, 60, 48

physical qubits. Each width has an explicit disjoint payload matching made entirely from edges in the live Cepheus coupling map. Candidates are attempted in descending order. The first candidate that returns all 2,048 shots becomes the high-width endpoint. A failed candidate is bypassed only if it returns the same provider execution-failure class and the quoted Spark credit is refunded. Any other failure stops the ladder.

This capability-driven selection does not inspect controller performance. It selects only a width at which the provider returns a reference measurement.

## Scientific protocol

The monitor, payload, target, shock, hidden gains and polarities, controller constants, four-acquisition deadline, two-consecutive-frame rule, monitor tolerance, and payload threshold rule are unchanged from the frozen 108-qubit protocol.

The completed 18-channel reference is reused after its QASM hash is checked against the current renderer. Retained residual runs at width 18 under a new frozen seed. At the selected high width, retained residual, diagonal retained secant, commissioned PI, and do-nothing run on one paired scenario. Dense finite difference remains structural: its minimum is `n + 3` total acquisitions, which exceeds the four-acquisition deadline at every candidate width. Full dense Broyden remains outside the bounded per-channel state and linear-host-work class.

Confirmation seeds are derived from the SHA-256 phrase in the JSON protocol and have not been used for development tuning. No controller constant or contract threshold may change after the first ladder reference is submitted.

## Credits and failure handling

At launch, 22 Spark credits and zero Full credits remain. One completed high-width reference plus twenty adaptive jobs costs 21 Spark credits at the inspected quote. One credit remains reserved. Failed capability-ladder jobs must be refunded before the next candidate is attempted and are not silently removed from the ledger.

Every job is separately prepared. Creation is permitted only for `Public Plan`, `Standard Queue`, and a one-credit total quote. Paid credits are forbidden. The reserve can replace at most one verified adaptive-job infrastructure failure. If unused, it funds one post-campaign reference at the selected high width.

## Claims

The selected high width is the largest width returned by this frozen executable-width ladder, not the hardware vendor's advertised maximum. A successful low/high retained pair supports high-width hardware transfer and consistency with bounded acquisition depth. It cannot by itself estimate a scaling exponent. Scaling claims require the frozen multi-width simulator evidence and exact resource accounting.

OpenQuantum does not expose provider execution duration for these jobs through the current SDK. Cloud submitted-to-observed-completion time is retained but never presented as physical QPU runtime. Direct-interface timing is reported only as `T_contract(tau) = A_contract tau + T_host`.

Nothing is pushed to GitHub, uploaded to Metriq, or published without owner review.
