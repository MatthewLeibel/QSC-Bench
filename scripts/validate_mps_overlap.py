#!/usr/bin/env python3
"""Compare Aer density-matrix and MPS plant outputs on overlapping widths."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from qsc_bench.config import load_config  # noqa: E402
from qsc_bench.plant import QuantumStabilityPlant  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--widths", type=int, nargs="+", default=[4, 8])
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260813, 20260814])
    parser.add_argument("--commands", type=int, default=3)
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--rmse-tolerance", type=float, default=0.025)
    args = parser.parse_args()

    config = load_config(args.config)
    density_config = replace(config.plant, simulator_method="density_matrix")
    mps_config = replace(config.plant, simulator_method="matrix_product_state")
    records = []

    for width in args.widths:
        for seed in args.seeds:
            density = QuantumStabilityPlant(width, seed, density_config)
            mps = QuantumStabilityPlant(width, seed, mps_config)
            density_reference = density.reference_monitor_target(args.shots)
            mps_reference = mps.reference_monitor_target(args.shots)
            reference_rmse = float(
                np.sqrt(np.mean(np.square(density_reference - mps_reference)))
            )

            rng = np.random.default_rng(np.random.SeedSequence([seed, width, 991]))
            monitor_rmse = []
            for _ in range(args.commands):
                command = rng.uniform(-0.60, 0.60, size=width)
                density_acquisition = density.acquire_monitor(command, args.shots)
                mps_acquisition = mps.acquire_monitor(command, args.shots)
                monitor_rmse.append(
                    float(
                        np.sqrt(
                            np.mean(
                                np.square(
                                    density_acquisition.response - mps_acquisition.response
                                )
                            )
                        )
                    )
                )

            payload_command = rng.uniform(-0.25, 0.25, size=width)
            density_payload = density.acquire_payload(payload_command, args.shots)
            mps_payload = mps.acquire_payload(payload_command, args.shots)
            payload_bitwise_difference = abs(
                density_payload.bitwise_zero_probability
                - mps_payload.bitwise_zero_probability
            )
            maximum_difference = max(
                [reference_rmse, payload_bitwise_difference, *monitor_rmse]
            )
            records.append(
                {
                    "width": width,
                    "seed": seed,
                    "reference_response_rmse": reference_rmse,
                    "ordinary_response_rmse": monitor_rmse,
                    "payload_bitwise_probability_absolute_difference": payload_bitwise_difference,
                    "maximum_declared_difference": maximum_difference,
                    "passed": maximum_difference <= args.rmse_tolerance,
                }
            )

    result = {
        "artifact": "QSC-Bench density-matrix/MPS overlap validation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_run": True,
        "config": str(args.config),
        "widths": args.widths,
        "seeds": args.seeds,
        "commands_per_cell": args.commands,
        "shots": args.shots,
        "rmse_tolerance": args.rmse_tolerance,
        "records": records,
        "passed": all(record["passed"] for record in records),
        "maximum_declared_difference": max(
            record["maximum_declared_difference"] for record in records
        ),
        "claim_boundary": (
            "This validates output agreement only on the declared overlap widths and finite-shot "
            "samples. It does not validate arbitrary-width MPS or tiled extrapolation."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"passed": result["passed"], "maximum_difference": result["maximum_declared_difference"]}, indent=2))
    print(f"JSON: {args.output}")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
