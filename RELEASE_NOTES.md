# QSC-Bench v1.0.0

This release publishes the complete frozen simulator campaign, development
results, real-QPU transfers, static hardware diagnostics, candidate Metriq result
envelopes, and captured negative evidence available on 2026-08-14.

## Primary result

- 1,470 paired simulator records across widths 16--65,536 and 30 confirmation
  seeds per width.
- Retained residual and fixed-window Anderson: 210/210 successes each.
- Acquisition-depth exponents: 0.0055 (95% bootstrap CI [-0.0064, 0.0123])
  and -0.0023 ([-0.0153, 0.0074]).
- Full Aer core: retained residual passed 60/60 trials at 4 and 8 qubits.
- One-million-channel implementation extension: 5/5 successes for each
  qualifying controller, explicitly outside the frozen primary inference.

## Hardware result

- Quantum Inspire Tuna-9: 75 adaptive jobs, three seeds, four controlled
  channels. Retained residual, diagonal retained secant, and commissioned PI
  passed 3/3; dense finite difference and do-nothing passed 0/3.
- OpenQuantum Rigetti Cepheus-1-108Q: one paired confirmation seed, 48 controlled
  channels on 96 physical qubits. Retained residual entered the joint contract
  at acquisition 4; do-nothing failed.
- OpenQuantum IQM Emerald: one 54-qubit static command-effect diagnostic passed
  its frozen rule. It is not an adaptive stability-contract result.
- Failed, blocked, pending-at-last-capture, and reference-inadmissible
  OpenQuantum campaigns are included as a separate evidence layer.

## Metriq submission

The release contains the QSC-Bench schema, local Aer adapter, 15 Tuna-9 and two
Cepheus candidate result envelopes, and their complete evidence packages.
Metriq Data ingestion awaits acceptance of the new benchmark and an auditable
adaptive remote execution path. The public records must not be described as
Metriq-hosted until that upstream review is complete.

## Claim boundary

“Flat” means bounded sequential acquisition depth over the tested simulator
range. It does not mean constant traffic, arithmetic, memory, sensor count,
actuator count, or energy. Hardware experiments establish finite-width transfer,
not a hardware scaling exponent. The public retained-residual controller is an
independent manuscript-level implementation, not the proprietary TrueLoop
runtime.

Powered by OpenQuantum. See https://www.openquantum.com/citation.
