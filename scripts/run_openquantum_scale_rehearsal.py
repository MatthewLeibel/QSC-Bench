#!/usr/bin/env python3
"""Record the disjoint-seed, memory-bounded Cepheus campaign rehearsal."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
from statistics import median
import time

from qiskit import qasm2

from qsc_bench.openquantum_scale import (
    OPENQUANTUM_ARMS,
    cepheus_protocol,
    derive_openquantum_scenario,
    build_openquantum_qasm,
    run_openquantum_rehearsal,
)


DEVELOPMENT_SEEDS = tuple(range(2026082101, 2026082111))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/development/openquantum_cepheus_scale_v1_rehearsal.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    rows = []
    circuit_checks = []
    for width in (18, 54):
        protocol = cepheus_protocol(width)
        scenario = derive_openquantum_scenario(DEVELOPMENT_SEEDS[0], protocol)
        source = build_openquantum_qasm([0.0] * width, scenario, protocol)
        circuit = qasm2.loads(source)
        circuit_checks.append(
            {
                "width": width,
                "physical_qubits": circuit.num_qubits,
                "classical_bits": circuit.num_clbits,
                "logical_depth_before_provider_compilation": circuit.depth(),
                "operation_counts_before_provider_compilation": {
                    str(key): int(value) for key, value in circuit.count_ops().items()
                },
            }
        )
        for arm in OPENQUANTUM_ARMS:
            for seed in DEVELOPMENT_SEEDS:
                result = run_openquantum_rehearsal(
                    arm=arm,
                    seed=seed,
                    protocol=protocol,
                    readout_flip=0.035,
                )
                rows.append(
                    {
                        "width": width,
                        "physical_qubits": protocol.physical_qubits,
                        "arm": arm,
                        "seed": seed,
                        "contract_success": result["contract_success"],
                        "contract_entry_acquisition": result[
                            "contract_entry_acquisition"
                        ],
                        "contract_at_deadline": result["contract_at_deadline"],
                        "scenario_sha256": result["scenario_sha256"],
                        "final_monitor_rmse": result["trace"][-1]["monitor_rmse"],
                        "final_payload_bitwise_zero": result["trace"][-1][
                            "payload_bitwise_zero"
                        ],
                        "trace": [
                            {
                                key: acquisition[key]
                                for key in (
                                    "acquisition",
                                    "acquisition_kind",
                                    "contract_eligible",
                                    "monitor_rmse",
                                    "payload_bitwise_zero",
                                    "controller_update_seconds",
                                )
                            }
                            for acquisition in result["trace"]
                        ],
                    }
                )
    summary = {}
    for width in (18, 54):
        summary[str(width)] = {}
        for arm in OPENQUANTUM_ARMS:
            subset = [row for row in rows if row["width"] == width and row["arm"] == arm]
            entries = [
                row["contract_entry_acquisition"]
                for row in subset
                if row["contract_success"]
            ]
            summary[str(width)][arm] = {
                "trials": len(subset),
                "successes": sum(bool(row["contract_success"]) for row in subset),
                "entry_acquisitions_successes_only": entries,
                "median_entry_acquisition_successes_only": (
                    None if not entries else median(entries)
                ),
                "median_final_monitor_rmse": median(
                    row["final_monitor_rmse"] for row in subset
                ),
                "median_final_payload_bitwise_zero": median(
                    row["final_payload_bitwise_zero"] for row in subset
                ),
            }
    payload = {
        "schema_version": "qsc-openquantum-scale-rehearsal-v1",
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": time.perf_counter() - started,
        "peak_rss_raw_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "confirmation_seeds_evaluated": False,
        "model": (
            "exact factorized one-/two-qubit circuit blocks, finite shots, and "
            "independent symmetric 3.5% measurement-bit flips"
        ),
        "model_limit": (
            "rehearsal validates logic and expected observability; it is not a "
            "calibrated predictive model of Cepheus hardware"
        ),
        "circuit_checks": circuit_checks,
        "summary": summary,
        "runs": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
