#!/usr/bin/env python3
"""Record pre-freeze development behavior for the 96-qubit single-Rx payload."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import resource
from statistics import median
import time

from qiskit import qasm2

from qsc_bench.openquantum_scale import (
    build_openquantum_qasm,
    cepheus_single_rx_protocol,
    derive_openquantum_scenario,
    run_openquantum_rehearsal,
)


DEVELOPMENT_SEEDS = tuple(range(2026082401, 2026082421))
ARMS = ("retained_residual", "diagonal_secant", "commissioned_pi", "do_nothing")
OUTPUT = Path("results/development/openquantum_cepheus_96q_single_rx_v3_rehearsal.json")


def main() -> None:
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    protocol = cepheus_single_rx_protocol()
    scenario = derive_openquantum_scenario(DEVELOPMENT_SEEDS[0], protocol)
    source = build_openquantum_qasm([0.0] * protocol.width, scenario, protocol)
    circuit = qasm2.loads(source)
    rows = []
    for arm in ARMS:
        for seed in DEVELOPMENT_SEEDS:
            result = run_openquantum_rehearsal(
                arm=arm,
                seed=seed,
                protocol=protocol,
                readout_flip=0.035,
            )
            rows.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "contract_success": result["contract_success"],
                    "contract_entry_acquisition": result["contract_entry_acquisition"],
                    "final_monitor_rmse": result["trace"][-1]["monitor_rmse"],
                    "final_payload_bitwise_zero": result["trace"][-1]["payload_bitwise_zero"],
                }
            )
    summary = {}
    for arm in ARMS:
        subset = [row for row in rows if row["arm"] == arm]
        entries = [
            row["contract_entry_acquisition"]
            for row in subset
            if row["contract_success"]
        ]
        summary[arm] = {
            "trials": len(subset),
            "successes": sum(bool(row["contract_success"]) for row in subset),
            "entry_acquisitions_successes_only": entries,
            "median_entry_acquisition_successes_only": (
                None if not entries else median(entries)
            ),
            "median_final_monitor_rmse": median(row["final_monitor_rmse"] for row in subset),
            "median_final_payload_bitwise_zero": median(
                row["final_payload_bitwise_zero"] for row in subset
            ),
        }
    payload = {
        "schema_version": "qsc-openquantum-single-rx-development-rehearsal-v3",
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": time.perf_counter() - started,
        "peak_rss_raw_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "confirmation_seed_evaluated": False,
        "model": "exact factorized single-qubit blocks with 3.5% symmetric readout flips",
        "model_limit": "logic rehearsal only; not a calibrated Cepheus predictor",
        "circuit": {
            "physical_qubits": circuit.num_qubits,
            "classical_bits": circuit.num_clbits,
            "logical_depth_before_provider_compilation": circuit.depth(),
            "operation_counts_before_provider_compilation": {
                str(key): int(value) for key, value in circuit.count_ops().items()
            },
        },
        "summary": summary,
        "runs": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
