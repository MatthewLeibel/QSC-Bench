"""Experiment orchestration, accounting, aggregation, and serialization."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

import numpy as np

from .config import BenchmarkConfig
from .contract import ContractTracker, response_rmse
from .controllers import (
    CommissionedPI,
    Controller,
    DenseFiniteDifference,
    Oracle,
    SPSA,
    make_controller,
)
from .plant import MonitorAcquisition, make_plant


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux and most BSD-derived CI images report KiB.
    return value if sys.platform == "darwin" else value * 1024


def _git_commit(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _git_dirty(path: Path) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return bool(result.stdout.strip())


def _package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def environment_manifest(project_root: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(project_root)
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "peak_rss_bytes_at_manifest": _peak_rss_bytes(),
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "git_commit": _git_commit(project_root),
        "git_worktree_dirty": _git_dirty(project_root),
        "packages": {
            name: _package_version(name)
            for name in ["qsc-bench", "metriq-gym", "qiskit", "qiskit-aer", "numpy", "pydantic"]
        },
    }


def _record_monitor(
    acquisition: MonitorAcquisition,
    *,
    stage: str,
    index: int,
    target: np.ndarray,
    command: np.ndarray,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "monitor_acquisition": index,
        "measured_response_rmse": response_rmse(acquisition.response, target),
        "evaluator_only_phase_rmse": float(
            np.sqrt(np.mean(np.square(acquisition.phase_error_before_acquisition)))
        ),
        "command_rms": float(np.sqrt(np.mean(np.square(command)))),
        "simulator_seconds": acquisition.simulator_seconds,
        "shots": acquisition.shots,
        "circuit_depth": acquisition.circuit_depth,
        "two_qubit_gates": acquisition.circuit_two_qubit_gates,
        "seed_simulator": acquisition.seed_simulator,
    }


def _commission_controller(
    controller: Controller,
    plant: Any,
    target: np.ndarray,
    shots: int,
    trace: list[dict[str, Any]],
    max_monitor_acquisitions: int,
) -> tuple[int, float]:
    """Run and charge baseline-specific commissioning acquisitions."""
    count = 0
    host_seconds = 0.0
    if isinstance(controller, CommissionedPI):
        if max_monitor_acquisitions < 2:
            return 0, 0.0
        rng = np.random.default_rng(controller.seed ^ 0xC0111551)
        code = rng.choice(np.array([-1.0, 1.0]), size=controller.n)
        amplitude = 0.30
        minus_command = -amplitude * code
        minus = plant.acquire_monitor(minus_command, shots)
        count += 1
        trace.append(
            _record_monitor(
                minus, stage="commission_minus", index=count, target=target, command=minus_command
            )
        )
        plus_command = amplitude * code
        plus = plant.acquire_monitor(plus_command, shots)
        count += 1
        trace.append(
            _record_monitor(
                plus, stage="commission_plus", index=count, target=target, command=plus_command
            )
        )
        host_start = time.perf_counter()
        controller.set_commissioning(minus.response, plus.response, code, amplitude)
        host_seconds += time.perf_counter() - host_start
    elif isinstance(controller, DenseFiniteDifference):
        needed = controller.n + 1
        if max_monitor_acquisitions < needed:
            return 0, 0.0
        amplitude = 0.30
        zero = np.zeros(controller.n, dtype=np.float64)
        base = plant.acquire_monitor(zero, shots)
        count += 1
        trace.append(
            _record_monitor(base, stage="commission_base", index=count, target=target, command=zero)
        )
        probes = []
        for channel in range(controller.n):
            command = np.zeros(controller.n, dtype=np.float64)
            command[channel] = amplitude
            acquisition = plant.acquire_monitor(command, shots)
            probes.append(acquisition.response)
            count += 1
            trace.append(
                _record_monitor(
                    acquisition,
                    stage=f"commission_channel_{channel}",
                    index=count,
                    target=target,
                    command=command,
                )
            )
        host_start = time.perf_counter()
        controller.set_commissioning(base.response, probes, amplitude)
        host_seconds += time.perf_counter() - host_start
    return count, host_seconds


def run_controller(
    config: BenchmarkConfig,
    *,
    n: int,
    seed: int,
    controller_name: str,
    reference_target: np.ndarray | None = None,
    reference_payload: tuple[float, float] | None = None,
    plant_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start_wall = time.perf_counter()
    peak_before = _peak_rss_bytes()
    plant = make_plant(n=n, seed=seed, config=config.plant)
    if reference_target is None:
        reference_target = plant.reference_monitor_target(config.reference_shots)
    if reference_payload is None:
        reference_payload = plant.reference_payload_quality(config.reference_shots)
    if plant_diagnostics is None:
        diagnostics = plant.local_jacobian_diagnostics()
        plant_diagnostics = {
            "minimum_diagonal_magnitude": diagnostics.minimum_diagonal_magnitude,
            "maximum_row_offdiag_to_diag_ratio": diagnostics.maximum_row_offdiag_to_diag_ratio,
            "spectral_norm": diagnostics.spectral_norm,
        }

    controller_start = time.perf_counter()
    controller = make_controller(controller_name, n=n, seed=seed ^ 0x5A17)
    host_controller_initialization_seconds = time.perf_counter() - controller_start
    trace: list[dict[str, Any]] = []
    simulator_seconds = 0.0
    host_update_seconds = host_controller_initialization_seconds
    monitor_acquisitions, host_commissioning_seconds = _commission_controller(
        controller,
        plant,
        reference_target,
        config.shots,
        trace,
        config.contract.max_monitor_acquisitions,
    )
    commissioning_acquisitions = monitor_acquisitions
    simulator_seconds += sum(item["simulator_seconds"] for item in trace)
    host_update_seconds += host_commissioning_seconds
    host_ordinary_update_seconds = 0.0
    host_probe_update_seconds = 0.0
    probe_acquisitions = 0

    payload_threshold = max(
        0.0, reference_payload[0] - config.contract.payload_drop_tolerance
    )
    tracker = ContractTracker(
        monitor_tolerance=config.contract.monitor_rmse_tolerance,
        required_consecutive=config.contract.consecutive_acquisitions,
        payload_threshold=payload_threshold,
    )
    payload_attempts = 0
    success = False
    acquisitions_to_contract: int | None = None
    payload_quality_at_entry: float | None = None
    payload_all_zero_at_entry: float | None = None
    final_monitor_rmse: float | None = None
    final_phase_rmse: float | None = None
    first_monitor_pass_acquisition: int | None = None
    confirmed_monitor_entry_acquisition: int | None = None

    while monitor_acquisitions < config.contract.max_monitor_acquisitions:
        if isinstance(controller, Oracle):
            controller.set_hidden_state(plant.drift, plant.polarities, plant.gains)
        measured_command = controller.u.copy()
        acquisition = plant.acquire_monitor(measured_command, config.shots)
        monitor_acquisitions += 1
        simulator_seconds += acquisition.simulator_seconds
        final_monitor_rmse = response_rmse(acquisition.response, reference_target)
        final_phase_rmse = float(
            np.sqrt(np.mean(np.square(acquisition.phase_error_before_acquisition)))
        )
        if (
            first_monitor_pass_acquisition is None
            and final_monitor_rmse <= config.contract.monitor_rmse_tolerance
        ):
            first_monitor_pass_acquisition = monitor_acquisitions
        trace_item = _record_monitor(
            acquisition,
            stage="ordinary",
            index=monitor_acquisitions,
            target=reference_target,
            command=measured_command,
        )
        candidate = tracker.observe_monitor(final_monitor_rmse)
        trace_item["contract_streak"] = tracker.streak
        trace_item["candidate_entry"] = candidate
        trace.append(trace_item)

        if candidate:
            if isinstance(controller, Oracle):
                controller.set_hidden_state(plant.drift, plant.polarities, plant.gains)
            payload = plant.acquire_payload(controller.u, config.shots)
            payload_attempts += 1
            simulator_seconds += payload.simulator_seconds
            payload_pass = tracker.observe_payload(payload.bitwise_zero_probability)
            trace.append(
                {
                    "stage": "payload_validation",
                    "after_monitor_acquisition": monitor_acquisitions,
                    "payload_attempt": payload_attempts,
                    "bitwise_zero_probability": payload.bitwise_zero_probability,
                    "all_zero_probability": payload.all_zero_probability,
                    "threshold": payload_threshold,
                    "passed": payload_pass,
                    "evaluator_only_phase_rmse": float(
                        np.sqrt(np.mean(np.square(payload.phase_error_before_acquisition)))
                    ),
                    "simulator_seconds": payload.simulator_seconds,
                    "shots": payload.shots,
                    "circuit_depth": payload.circuit_depth,
                    "two_qubit_gates": payload.circuit_two_qubit_gates,
                    "seed_simulator": payload.seed_simulator,
                }
            )
            if payload_pass:
                success = True
                acquisitions_to_contract = monitor_acquisitions
                confirmed_monitor_entry_acquisition = monitor_acquisitions
                payload_quality_at_entry = payload.bitwise_zero_probability
                payload_all_zero_at_entry = payload.all_zero_probability
                break

        if isinstance(controller, SPSA):
            if monitor_acquisitions + 2 > config.contract.max_monitor_acquisitions:
                break
            plus_command, minus_command, perturbation = controller.probe_commands()
            plus = plant.acquire_monitor(plus_command, config.shots)
            monitor_acquisitions += 1
            probe_acquisitions += 1
            simulator_seconds += plus.simulator_seconds
            trace.append(
                _record_monitor(
                    plus,
                    stage="spsa_probe_plus",
                    index=monitor_acquisitions,
                    target=reference_target,
                    command=plus_command,
                )
            )
            minus = plant.acquire_monitor(minus_command, config.shots)
            monitor_acquisitions += 1
            probe_acquisitions += 1
            simulator_seconds += minus.simulator_seconds
            trace.append(
                _record_monitor(
                    minus,
                    stage="spsa_probe_minus",
                    index=monitor_acquisitions,
                    target=reference_target,
                    command=minus_command,
                )
            )
            loss_plus = response_rmse(plus.response, reference_target) ** 2
            loss_minus = response_rmse(minus.response, reference_target) ** 2
            update_start = time.perf_counter()
            controller.update_from_probe_losses(loss_plus, loss_minus, perturbation)
            elapsed_update = time.perf_counter() - update_start
            host_probe_update_seconds += elapsed_update
            host_update_seconds += elapsed_update
        else:
            update_start = time.perf_counter()
            controller.update(acquisition.response, reference_target)
            elapsed_update = time.perf_counter() - update_start
            host_ordinary_update_seconds += elapsed_update
            host_update_seconds += elapsed_update

    total_quantum_executions = monitor_acquisitions + payload_attempts
    ttc_by_latency: dict[str, float] = {}
    ttu_by_latency: dict[str, float] = {}
    if success and acquisitions_to_contract is not None:
        for latency in config.latency_seconds:
            key = f"{latency:.9g}"
            ttc_by_latency[key] = acquisitions_to_contract * latency + host_update_seconds
            ttu_by_latency[key] = total_quantum_executions * latency + host_update_seconds

    peak_after = _peak_rss_bytes()
    return {
        "status": "PASS" if success else "FAIL_CONTRACT_TIMEOUT",
        "development_run": config.development_run,
        "protocol_version": config.protocol_version,
        "qsc_git_commit": _git_commit(Path(__file__).resolve().parents[1]),
        "qsc_git_worktree_dirty": _git_dirty(Path(__file__).resolve().parents[1]),
        "width": n,
        "seed": seed,
        "controller": controller.metadata.name,
        "controller_metadata": asdict(controller.metadata),
        "ranked": bool(
            controller.metadata.ranked
            and (controller.metadata.name != "oracle" or config.controllers.include_oracle_in_ranking)
        ),
        "contract_success": success,
        "acquisitions_to_contract": acquisitions_to_contract,
        "first_monitor_pass_acquisition": first_monitor_pass_acquisition,
        "confirmed_monitor_entry_acquisition": confirmed_monitor_entry_acquisition,
        "commissioning_acquisitions": commissioning_acquisitions,
        "ordinary_monitor_acquisitions": (
            monitor_acquisitions - commissioning_acquisitions - probe_acquisitions
        ),
        "probe_acquisitions": probe_acquisitions,
        "total_monitor_acquisitions": monitor_acquisitions,
        "payload_validation_acquisitions": payload_attempts,
        "total_quantum_executions_to_usable": total_quantum_executions if success else None,
        "final_measured_monitor_rmse": final_monitor_rmse,
        "final_evaluator_only_phase_rmse": final_phase_rmse,
        "reference_payload_bitwise_zero_probability": reference_payload[0],
        "reference_payload_all_zero_probability": reference_payload[1],
        "payload_quality_threshold": payload_threshold,
        "payload_bitwise_zero_probability_at_entry": payload_quality_at_entry,
        "payload_all_zero_probability_at_entry": payload_all_zero_at_entry,
        "contract_candidate_entries": tracker.candidate_entries,
        "controller_mutable_float_words": controller.mutable_float_words(),
        "controller_mutable_float_words_per_channel": controller.mutable_float_words_per_channel(),
        "controller_mutable_state_bytes": controller.mutable_state_bytes(),
        "controller_updates_to_contract": controller.update_count if success else None,
        "host_update_seconds": host_update_seconds,
        "host_controller_initialization_seconds": host_controller_initialization_seconds,
        "host_commissioning_seconds": host_commissioning_seconds,
        "host_ordinary_update_seconds": host_ordinary_update_seconds,
        "host_probe_update_seconds": host_probe_update_seconds,
        "simulator_runtime_seconds": simulator_seconds,
        "wall_runtime_seconds": time.perf_counter() - start_wall,
        "peak_rss_bytes_before": peak_before,
        "peak_rss_bytes_after": peak_after,
        "traffic_scalars": int(monitor_acquisitions * 2 * n),
        "traffic_bytes_float64": int(monitor_acquisitions * 2 * n * 8),
        "monitor_values_per_acquisition": n,
        "actuation_values_per_frame": n,
        "maintenance_placement_in_benchmark": "logical digital host",
        "actuation_frames": monitor_acquisitions,
        "total_counted_shots": int(total_quantum_executions * config.shots),
        "time_to_contract_seconds_by_acquisition_latency": ttc_by_latency,
        "time_to_usable_seconds_by_acquisition_latency": ttu_by_latency,
        "score_inverse_acquisitions": (
            1.0 / acquisitions_to_contract if success and acquisitions_to_contract else 0.0
        ),
        "plant_diagnostics": plant_diagnostics,
        "trace": trace,
    }


def _quantile_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "q1": None, "q3": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "median": float(np.median(array)),
        "q1": float(np.quantile(array, 0.25)),
        "q3": float(np.quantile(array, 0.75)),
    }


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault((record["width"], record["controller"]), []).append(record)
    summaries = []
    for (width, controller), group in sorted(groups.items()):
        successes = [record for record in group if record["contract_success"]]
        acquisitions = [float(record["acquisitions_to_contract"]) for record in successes]
        simulator_times = [float(record["simulator_runtime_seconds"]) for record in group]
        summaries.append(
            {
                "width": width,
                "controller": controller,
                "runs": len(group),
                "successes": len(successes),
                "failures": len(group) - len(successes),
                "success_rate": len(successes) / len(group),
                "acquisitions_to_contract": _quantile_summary(acquisitions),
                "simulator_runtime_seconds": _quantile_summary(simulator_times),
                "ranked": bool(group[0]["ranked"]),
            }
        )
    return summaries


def run_suite(
    config: BenchmarkConfig,
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    config.validate()
    project_root = Path(__file__).resolve().parents[1]
    records: list[dict[str, Any]] = []
    reference_setup: list[dict[str, Any]] = []
    reference_cache: dict[tuple[int, int], tuple[np.ndarray, tuple[float, float], dict[str, Any]]] = {}

    for n in config.widths:
        for seed in config.seeds:
            cache_key = (n, seed)
            reference_start = time.perf_counter()
            reference_peak_before = _peak_rss_bytes()
            reference_plant = make_plant(n=n, seed=seed, config=config.plant)
            target = reference_plant.reference_monitor_target(config.reference_shots)
            payload_reference = reference_plant.reference_payload_quality(config.reference_shots)
            diagnostics = reference_plant.local_jacobian_diagnostics()
            diagnostic_dict = {
                "minimum_diagonal_magnitude": diagnostics.minimum_diagonal_magnitude,
                "maximum_row_offdiag_to_diag_ratio": diagnostics.maximum_row_offdiag_to_diag_ratio,
                "spectral_norm": diagnostics.spectral_norm,
            }
            reference_cache[cache_key] = (target, payload_reference, diagnostic_dict)
            reference_setup.append(
                {
                    "width": n,
                    "seed": seed,
                    "wall_seconds": time.perf_counter() - reference_start,
                    "peak_rss_bytes_before": reference_peak_before,
                    "peak_rss_bytes_after": _peak_rss_bytes(),
                    "reference_shots_per_circuit": config.reference_shots,
                    "reference_circuit_evaluations": 2,
                    "charged_to_controller_cold_start": False,
                    "plant_diagnostics": diagnostic_dict,
                }
            )
            for controller_name in config.controllers.names:
                target, payload_reference, diagnostic_dict = reference_cache[cache_key]
                try:
                    record = run_controller(
                        config,
                        n=n,
                        seed=seed,
                        controller_name=controller_name,
                        reference_target=target,
                        reference_payload=payload_reference,
                        plant_diagnostics=diagnostic_dict,
                    )
                except Exception as exc:  # failures remain visible in public records
                    record = {
                        "status": "ERROR",
                        "development_run": config.development_run,
                        "protocol_version": config.protocol_version,
                        "width": n,
                        "seed": seed,
                        "controller": controller_name,
                        "ranked": controller_name != "oracle",
                        "contract_success": False,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                records.append(record)
                if progress is not None:
                    progress(record)

    canonical_config = json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":"))
    return {
        "benchmark_name": config.benchmark_name,
        "protocol_version": config.protocol_version,
        "development_run": config.development_run,
        "result_label": "DEVELOPMENT / NOT FOR PUBLICATION" if config.development_run else "FROZEN CONFIRMATION",
        "config_sha256": hashlib.sha256(canonical_config.encode("utf-8")).hexdigest(),
        "config": config.to_dict(),
        "environment": environment_manifest(project_root),
        "reference_setup": reference_setup,
        "records": records,
        "summary": summarize(records),
    }


def write_results(bundle: dict[str, Any], output_json: str | Path) -> tuple[Path, Path]:
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_json.with_suffix(output_json.suffix + ".tmp")
    temporary.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output_json)

    csv_path = output_json.with_suffix(".csv")
    fieldnames = [
        "status",
        "development_run",
        "protocol_version",
        "width",
        "seed",
        "controller",
        "ranked",
        "contract_success",
        "acquisitions_to_contract",
        "first_monitor_pass_acquisition",
        "confirmed_monitor_entry_acquisition",
        "commissioning_acquisitions",
        "ordinary_monitor_acquisitions",
        "probe_acquisitions",
        "total_monitor_acquisitions",
        "payload_validation_acquisitions",
        "total_quantum_executions_to_usable",
        "final_measured_monitor_rmse",
        "final_evaluator_only_phase_rmse",
        "payload_bitwise_zero_probability_at_entry",
        "simulator_runtime_seconds",
        "host_update_seconds",
        "host_controller_initialization_seconds",
        "host_commissioning_seconds",
        "host_ordinary_update_seconds",
        "host_probe_update_seconds",
        "traffic_scalars",
        "traffic_bytes_float64",
        "controller_mutable_float_words_per_channel",
        "controller_updates_to_contract",
        "error_type",
        "error_message",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in bundle["records"]:
            writer.writerow(record)
    return output_json, csv_path
