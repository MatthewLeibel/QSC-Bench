# QSC-Bench OpenQuantum IQM Emerald command-effect diagnostic v1

## Purpose

This one-job diagnostic uses the final available non-Cepheus Spark credit to test a frozen retained correction on a second physical backend. It is not an adaptive Emerald campaign and cannot replace the 96-qubit Cepheus confirmation.

The retained command comes from the first two completed hardware acquisitions of the frozen Cepheus single-Rx campaign. Before the Emerald outcome is observed, the exact QASM, source job IDs, request hash, expected ideal values, physical pairing, shot count, and decision rule are frozen in the repository.

## Circuit

IQM Emerald exposes 54 qubits. The circuit uses all 54 as 27 adjacent logical pairs:

- even physical qubit `2i`: `Rx(3 d_i)`, the unmaintained commanded shock;
- odd physical qubit `2i+1`: `Rx(3 e_i^corr)`, the retained acquisition-3 corrected error.

All qubits begin in zero and are measured once per shot. The score for each arm is mean bitwise-zero probability across its 27 qubits. The ideal source vectors predict 0.69274 without maintenance and 0.96813 after correction, a difference of 0.27540.

The diagnostic passes only if the measured corrected score is at least 0.80 and exceeds the unmaintained score by at least 0.10. There is no retuning, retry, or threshold change after output.

## Cost guard

The run uses 512 shots, Public Plan, and Standard Queue. Its exact quote must be one Spark credit, Full-credit balance must be zero, and at least one Spark credit must remain afterward for the pending Cepheus retained acquisition 4. No retry is authorized.

## Claim boundary

The two arms occupy different physical qubits in one simultaneous job, so qubit-to-qubit variation is a confound. This is a static command-effect and portability diagnostic. It does not measure adaptive convergence on Emerald, native calibration, flat acquisition scaling, or time to contract. A pass shows that the correction vector corresponds to a materially better shallow workload state on this second hardware execution; a failure remains reportable negative evidence.

Nothing is pushed, uploaded to Metriq, or published without owner review.
