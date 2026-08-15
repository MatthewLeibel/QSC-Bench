#!/usr/bin/env python3
"""Validate the analytic scale backend against the canonical Aer circuit."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from qiskit.quantum_info import Statevector

from qsc_bench.config import (
    BenchmarkConfig,
    ContractConfig,
    ControllerConfig,
    DriftConfig,
    NoiseConfig,
    PlantConfig,
    load_config,
)
from qsc_bench.plant import AnalyticRingPlant, QuantumStabilityPlant
from qsc_bench.runner import run_suite


def _bitwise_zero_probabilities(state: Statevector, width: int) -> np.ndarray:
    return np.asarray([state.probabilities([qubit])[0] for qubit in range(width)])


def validate(output: Path, seed_config: Path | None = None) -> dict:
    noise_free_aer = PlantConfig(
        backend="aer",
        payload_kind="local_mirror",
        simulator_method="statevector",
        noise=NoiseConfig(0.0, 0.0, 0.0),
    )
    noise_free_analytic = replace(noise_free_aer, backend="analytic_ring")
    maximum_monitor_difference = 0.0
    maximum_payload_difference = 0.0
    maximum_jacobian_difference = 0.0
    expectation_cases = 0
    for width in (1, 2, 4, 8, 16):
        for seed in (330001, 330002, 330003):
            aer = QuantumStabilityPlant(width, seed, noise_free_aer)
            analytic = AnalyticRingPlant(width, seed, noise_free_analytic)
            rng = np.random.default_rng(seed ^ width)
            for _ in range(8):
                phase = rng.uniform(-0.75, 0.75, size=width)
                monitor_difference = float(
                    np.max(
                        np.abs(
                            aer.ideal_monitor_response(phase)
                            - analytic.ideal_monitor_response(phase)
                        )
                    )
                )
                maximum_monitor_difference = max(
                    maximum_monitor_difference, monitor_difference
                )

                payload = aer._payload_circuit(phase).remove_final_measurements(
                    inplace=False
                )
                state = Statevector.from_instruction(payload)
                exact_payload = _bitwise_zero_probabilities(state, width)
                analytic_payload = analytic._local_payload_zero_probabilities(phase)
                payload_difference = float(
                    np.max(np.abs(exact_payload - analytic_payload))
                )
                maximum_payload_difference = max(
                    maximum_payload_difference, payload_difference
                )
                expectation_cases += 1

            if width <= 8:
                exact_jacobian = aer.local_jacobian_diagnostics().jacobian
                analytic_jacobian = analytic.local_jacobian_diagnostics().jacobian
                if exact_jacobian is None or analytic_jacobian is None:
                    raise RuntimeError("small-width validation unexpectedly omitted Jacobian")
                maximum_jacobian_difference = max(
                    maximum_jacobian_difference,
                    float(np.max(np.abs(exact_jacobian - analytic_jacobian))),
                )

    shared_plant = PlantConfig(
        backend="aer",
        coupling_radians=0.15,
        nominal_angle_low=1.30,
        nominal_angle_high=1.80,
        analysis_tilt_radians=0.40,
        gain_low=0.50,
        gain_high=1.20,
        simulator_method="statevector",
        payload_kind="local_mirror",
        payload_error_amplification=3.0,
        noise=NoiseConfig(0.0, 0.0, 0.005),
        drift=DriftConfig(0.45, 0.002, 0.05, 0.0005, 0.0),
    )
    if seed_config is None:
        validation_seeds = tuple(range(330011, 330031))
        development_run = True
        protocol_version = "0.2.0-analytic-validation"
        seed_source = "embedded development seeds"
        seed_source_sha256 = None
    else:
        raw_seed_config = seed_config.read_bytes()
        frozen = load_config(seed_config)
        validation_seeds = frozen.seeds
        development_run = frozen.development_run
        protocol_version = f"{frozen.protocol_version}-analytic-validation"
        seed_source = str(seed_config)
        seed_source_sha256 = hashlib.sha256(raw_seed_config).hexdigest()

    common = dict(
        benchmark_name="QSC-Bench Cold Start",
        protocol_version=protocol_version,
        development_run=development_run,
        # The analytic scale campaign starts at width 16.  Width 4 is excluded
        # from the stochastic overlap because finite-size joint-shot covariance
        # is visibly material there and that cell is retained on Aer instead.
        widths=(8, 12),
        seeds=validation_seeds,
        shots=512,
        reference_shots=4096,
        contract=ContractConfig(0.035, 3, 0.04, 40),
        controllers=ControllerConfig(
            names=(
                "do_nothing",
                "retained_residual",
                "diagonal_secant",
                "anderson_residual",
                "commissioned_pi",
            )
        ),
    )
    aer_bundle = run_suite(BenchmarkConfig(**common, plant=shared_plant))
    analytic_bundle = run_suite(
        BenchmarkConfig(
            **common,
            plant=replace(shared_plant, backend="analytic_ring"),
        )
    )

    def cell_summary(bundle: dict) -> dict[tuple[int, str], tuple[float, float | None]]:
        result = {}
        for row in bundle["summary"]:
            result[(int(row["width"]), str(row["controller"]))] = (
                float(row["success_rate"]),
                row["acquisitions_to_contract"]["median"],
            )
        return result

    aer_cells = cell_summary(aer_bundle)
    analytic_cells = cell_summary(analytic_bundle)
    comparisons = []
    maximum_success_rate_difference = 0.0
    maximum_median_acquisition_difference = 0.0
    for key in sorted(aer_cells):
        aer_success, aer_median = aer_cells[key]
        reduced_success, reduced_median = analytic_cells[key]
        success_difference = abs(aer_success - reduced_success)
        maximum_success_rate_difference = max(
            maximum_success_rate_difference, success_difference
        )
        median_difference = None
        if aer_median is not None and reduced_median is not None:
            median_difference = abs(float(aer_median) - float(reduced_median))
            maximum_median_acquisition_difference = max(
                maximum_median_acquisition_difference, median_difference
            )
        comparisons.append(
            {
                "width": key[0],
                "controller": key[1],
                "aer_success_rate": aer_success,
                "analytic_success_rate": reduced_success,
                "absolute_success_rate_difference": success_difference,
                "aer_median_acquisitions": aer_median,
                "analytic_median_acquisitions": reduced_median,
                "absolute_median_acquisition_difference": median_difference,
            }
        )

    thresholds = {
        "maximum_monitor_expectation_difference": 1e-12,
        "maximum_payload_expectation_difference": 1e-12,
        "maximum_jacobian_difference": 2e-5,
        "maximum_closed_loop_success_rate_difference": 0.25,
        "maximum_closed_loop_median_acquisition_difference": 6.0,
    }
    checks = {
        "monitor_expectation": (
            maximum_monitor_difference
            <= thresholds["maximum_monitor_expectation_difference"]
        ),
        "payload_expectation": (
            maximum_payload_difference
            <= thresholds["maximum_payload_expectation_difference"]
        ),
        "jacobian": (
            maximum_jacobian_difference <= thresholds["maximum_jacobian_difference"]
        ),
        "closed_loop_success_rate": (
            maximum_success_rate_difference
            <= thresholds["maximum_closed_loop_success_rate_difference"]
        ),
        "closed_loop_median_acquisitions": (
            maximum_median_acquisition_difference
            <= thresholds["maximum_closed_loop_median_acquisition_difference"]
        ),
    }
    result = {
        "artifact": "QSC-Bench analytic-ring validation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": (
            "The analytic backend is exact for ideal component marginals and the "
            "local-mirror payload. It samples exact binomial marginals but omits "
            "cross-channel shot covariance, which is assessed by the closed-loop overlap."
        ),
        "seed_source": seed_source,
        "seed_source_sha256": seed_source_sha256,
        "expectation_cases": expectation_cases,
        "observed": {
            "maximum_monitor_expectation_difference": maximum_monitor_difference,
            "maximum_payload_expectation_difference": maximum_payload_difference,
            "maximum_jacobian_difference": maximum_jacobian_difference,
            "maximum_closed_loop_success_rate_difference": maximum_success_rate_difference,
            "maximum_closed_loop_median_acquisition_difference": (
                maximum_median_acquisition_difference
            ),
        },
        "thresholds": thresholds,
        "checks": checks,
        "closed_loop_cells": comparisons,
        "aer_result": aer_bundle,
        "analytic_result": analytic_bundle,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-config", type=Path)
    args = parser.parse_args()
    result = validate(args.output, args.seed_config)
    print(json.dumps({"status": result["status"], **result["observed"]}, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
