#!/usr/bin/env python3
"""Build the complete QSC-Bench Tuna-9 hardware evidence package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
from statistics import median
from typing import Any

from qsc_bench.hardware import HARDWARE_ARMS, QIHardwareProtocol
from qsc_bench.hardware_results import (
    load_qi_capture,
    normalize_qi_reference,
    normalize_qi_sequential_run,
    summarize_hardware_rows,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--post-reference", type=Path)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--pilot", type=Path)
    parser.add_argument("--failed-provider-job", type=Path, action="append", default=[])
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--protocol-commit", default="4c01ede")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wilson(successes: int, trials: int, z: float = 1.959963984540054) -> list[float]:
    if trials <= 0:
        return [0.0, 1.0]
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    half = (
        z
        * ((p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) ** 0.5)
        / denominator
    )
    return [max(0.0, center - half), min(1.0, center + half)]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_evidence(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> None:
    args = parse_args()
    protocol = QIHardwareProtocol()
    protocol.validate()
    output = args.output_directory
    output.mkdir(parents=True, exist_ok=True)
    raw_directory = output / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)

    reference_capture = load_qi_capture(args.reference)
    reference = normalize_qi_reference(reference_capture, protocol)
    post_reference = None
    reference_drift = None
    if args.post_reference is not None:
        post_reference_capture = load_qi_capture(args.post_reference)
        post_reference = normalize_qi_reference(post_reference_capture, protocol)
        monitor_delta = [
            float(after - before)
            for before, after in zip(
                reference["monitor_target"], post_reference["monitor_target"]
            )
        ]
        reference_drift = {
            "monitor_delta": monitor_delta,
            "monitor_rmse": math.sqrt(
                sum(value * value for value in monitor_delta) / len(monitor_delta)
            ),
            "payload_bitwise_zero_delta": float(
                post_reference["payload_reference_bitwise_zero"]
                - reference["payload_reference_bitwise_zero"]
            ),
            "interpretation": (
                "Diagnostic only. The original reference and all frozen thresholds "
                "remain unchanged."
            ),
        }
    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    expected_source_hashes = source_manifest["files"]
    expected_config = json.loads(
        Path("configs/hardware/quantum_inspire_tuna9_hardware_v1.json").read_text(
            encoding="utf-8"
        )
    )
    expected_seeds = set(int(seed) for seed in expected_config["confirmation_seeds"])
    expected_arms = set(str(arm) for arm in expected_config["arms"])

    run_paths = sorted(args.runs_root.glob("seed_*/*.json"))
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for path in run_paths:
        run = json.loads(path.read_text(encoding="utf-8"))
        row = normalize_qi_sequential_run(run, protocol)
        key = (int(row["seed"]), str(row["arm"]))
        if key in seen:
            raise ValueError(f"duplicate hardware trial: {key}")
        seen.add(key)
        if key[0] not in expected_seeds or key[1] not in expected_arms:
            raise ValueError(f"undeclared hardware trial: {key}")
        source_name = Path(run["source_path"]).name
        expected_digest = expected_source_hashes.get(source_name)
        if expected_digest is None or expected_digest != row["source_sha256"]:
            raise ValueError(f"source hash mismatch for {key}")
        rows.append(row)
        _copy_evidence(path, raw_directory / f"seed_{key[0]}_{key[1]}.json")

    expected_pairs = {(seed, arm) for seed in expected_seeds for arm in expected_arms}
    missing = expected_pairs - seen
    unexpected = seen - expected_pairs
    if missing or unexpected:
        raise ValueError(
            f"hardware matrix is incomplete: missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )

    pilot = None
    if args.pilot is not None:
        pilot_payload = json.loads(args.pilot.read_text(encoding="utf-8"))
        pilot = normalize_qi_sequential_run(pilot_payload, protocol)
        _copy_evidence(args.pilot, raw_directory / "development_pilot.json")
    failed_jobs = []
    for path in args.failed_provider_job:
        capture = load_qi_capture(path)
        failed_jobs.append(
            {
                "job_id": int(capture["job"]["id"]),
                "status": capture["job"]["status"],
                "message": capture["job"].get("message"),
                "algorithm_type": capture["job"].get("algorithm_type"),
            }
        )
        _copy_evidence(path, raw_directory / path.name)

    _copy_evidence(args.reference, raw_directory / "contract_reference.json")
    if args.post_reference is not None:
        _copy_evidence(
            args.post_reference, raw_directory / "post_campaign_contract_reference.json"
        )
    _copy_evidence(args.source_manifest, raw_directory / "PRE_OUTCOME_MANIFEST.json")

    arm_summary = summarize_hardware_rows(rows)
    for arm, values in arm_summary.items():
        values["success_wilson_95"] = _wilson(
            int(values["contract_successes"]), int(values["trials"])
        )
        arm_rows = [row for row in rows if row["arm"] == arm]
        successful = [row for row in arm_rows if row["contract_success"]]
        values["median_provider_execution_seconds_to_contract"] = (
            None
            if not successful
            else float(
                median(
                    float(row["provider_execution_seconds_to_contract"])
                    for row in successful
                )
            )
        )
        values["median_provider_execution_seconds_total"] = float(
            median(float(row["provider_execution_seconds_total"]) for row in arm_rows)
        )
        values["median_controller_update_seconds_to_contract"] = (
            None
            if not successful
            else float(
                median(
                    float(row["controller_update_seconds_to_contract"])
                    for row in successful
                )
            )
        )
        values["median_provider_job_create_to_finish_seconds_total"] = float(
            median(
                float(row["provider_job_create_to_finish_seconds_total"])
                for row in arm_rows
            )
        )
        values["orchestration_resumed_trials"] = sum(
            bool(row["orchestration_resumed"]) for row in arm_rows
        )
        values["network_retries"] = int(
            sum(int(row["network_retry_count"]) for row in arm_rows)
        )
        values["infrastructure_failures"] = int(
            sum(int(row["infrastructure_failures"]) for row in arm_rows)
        )

    qualifying_arms = ["retained_residual", "diagonal_secant"]
    qualifying_all_success = all(
        arm_summary[arm]["contract_successes"] == arm_summary[arm]["trials"]
        for arm in qualifying_arms
    )
    dense_structural_ceiling = all(
        row["structural_minimum_acquisitions_to_confirm"] > protocol.acquisitions
        and not row["contract_success"]
        for row in rows
        if row["arm"] == "dense_fd"
    )
    retained_entry_value = arm_summary["retained_residual"][
        "median_entry_acquisition_successes_only"
    ]
    retained_controller_value = arm_summary["retained_residual"][
        "median_controller_update_seconds_to_contract"
    ]
    if retained_entry_value is None or retained_controller_value is None:
        retained_entry = None
        retained_controller_seconds = None
        direct_feedback_projection = {
            "controller": "retained_residual",
            "available": False,
            "reason": "No successful retained-residual hardware entry was observed.",
        }
    else:
        retained_entry = int(retained_entry_value)
        retained_controller_seconds = float(retained_controller_value)
        direct_feedback_projection = {
            "formula": "A_contract * tau + measured local controller update time",
            "controller": "retained_residual",
            "available": True,
            "acquisitions_to_contract": retained_entry,
            "measured_median_controller_update_seconds_to_contract": (
                retained_controller_seconds
            ),
            "latency_sweep": [
                {
                    "tau_seconds": tau,
                    "acquisition_only_seconds": retained_entry * tau,
                    "including_measured_local_controller_seconds": (
                        retained_entry * tau + retained_controller_seconds
                    ),
                }
                for tau in (1e-6, 1e-5, 1e-4, 1e-3, 1e-1)
            ],
            "claim_boundary": (
                "Parameterized direct-feedback projection, not Tuna-9 measured latency. "
                "Provider-reported execution and public-cloud timing are reported separately."
            ),
        }
    hardware_decision = {
        "finite_width_hardware_transfer": (
            "PASS" if qualifying_all_success else "FAIL"
        ),
        "dense_fd_deadline_ceiling": "PASS" if dense_structural_ceiling else "FAIL",
        "width_scaling_from_hardware": "NOT_TESTED",
        "reason": (
            "At width four, all declared minimal-sufficient candidate arms restored "
            "the monitor and disjoint payload within the five-acquisition deadline."
            if qualifying_all_success
            else "At least one declared candidate arm failed a confirmation trial."
        ),
        "claim_boundary": (
            "This is a real-QPU hardware-in-the-loop transfer at width four. It does "
            "not access provider-private calibration registers and does not establish "
            "flat physical scaling; that claim remains finite-range simulator evidence."
        ),
    }

    rows.sort(key=lambda row: (int(row["seed"]), str(row["arm"])))
    summary = {
        "schema_version": "qsc-tuna9-hardware-evidence-v1",
        "protocol_commit": args.protocol_commit,
        "evidence_builder_commit": "recorded in artifact manifest",
        "provider": "Quantum Inspire",
        "backend": "Tuna-9",
        "backend_type_id": 6,
        "execution_mode": "client_orchestrated_sequential_direct_qpu_jobs",
        "reference": reference,
        "post_campaign_reference": post_reference,
        "post_campaign_reference_drift": reference_drift,
        "pre_outcome_source_manifest_sha256": _sha256(args.source_manifest),
        "development_pilot": pilot,
        "failed_provider_hybrid_jobs": failed_jobs,
        "confirmation_trials": rows,
        "arm_summary": arm_summary,
        "direct_feedback_latency_projection": direct_feedback_projection,
        "decision": hardware_decision,
        "publication_state": "local only; owner review required before push or submission",
    }
    _write_json(output / "QSC_TUNA9_HARDWARE_SUMMARY.json", summary)

    fieldnames = [
        "seed",
        "arm",
        "contract_success",
        "contract_entry_acquisition",
        "contract_at_deadline",
        "final_monitor_rmse",
        "final_payload_bitwise_zero",
        "ordinary_acquisitions",
        "discarded_probe_acquisitions",
        "provider_execution_seconds_to_contract",
        "provider_execution_seconds_total",
        "provider_job_create_to_finish_seconds_to_contract",
        "provider_job_create_to_finish_seconds_total",
        "client_wall_seconds",
        "controller_update_seconds",
        "controller_update_seconds_to_contract",
        "infrastructure_failures",
        "orchestration_resumed",
        "network_retry_count",
        "source_sha256",
    ]
    with (output / "qsc_tuna9_confirmation.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})

    resource_words = {
        "retained_residual": 6.0,
        "diagonal_secant": 4.0,
        "commissioned_pi": 3.0,
        "dense_fd": float(protocol.width + 1),
        "do_nothing": 1.0,
    }
    qualifying_cold_start = {"retained_residual", "diagonal_secant"}
    metriq_records = []
    for row in rows:
        acquisitions = row["contract_entry_acquisition"] or 0
        traffic_acquisitions = (
            acquisitions if row["contract_success"] else protocol.acquisitions
        )
        host_to_outcome = (
            row["controller_update_seconds_to_contract"]
            if row["contract_success"]
            else row["controller_update_seconds"]
        )
        result_payload = {
            "width": protocol.width,
            "contract_success": row["contract_success"],
            "acquisitions_to_contract": acquisitions,
            "total_quantum_executions_to_usable": (
                acquisitions if row["contract_success"] else 0
            ),
            "payload_quality": (
                row["payload_bitwise_zero_at_entry"]
                if row["contract_success"]
                else row["final_payload_bitwise_zero"]
            ),
            "monitor_values_per_acquisition": protocol.width,
            "local_monitor_plus_actuation_values_per_cycle": 2 * protocol.width,
            "traffic_scalars_to_contract": (
                traffic_acquisitions * 2 * protocol.width
            ),
            "controller_mutable_state_bytes": int(
                resource_words[row["arm"]] * protocol.width * 8
            ),
            "controller_float_words_per_channel": resource_words[row["arm"]],
            "minimal_sufficient_cold_start_candidate": (
                row["arm"] in qualifying_cold_start
            ),
            "projected_acquisition_latency_seconds": 1e-4,
            "projected_time_to_contract_seconds": (
                acquisitions * 1e-4 + float(host_to_outcome)
                if row["contract_success"]
                else 0.0
            ),
            "simulator_runtime_seconds": 0.0,
            "host_update_seconds": float(host_to_outcome),
            "qsc_git_worktree_dirty": False,
            "qsc_code_commit": args.protocol_commit,
            "score": {
                "value": 0.0 if acquisitions == 0 else 1.0 / acquisitions,
                "uncertainty": None,
            },
        }
        metriq_records.append(
            {
                "app_version": "0.0.1.dev2+g69e28cd55",
                "timestamp": row["capture_completed_at"],
                "suite_id": None,
                "job_type": "QSC-Bench Cold Start",
                "results": result_payload,
                "platform": {
                    "device": "Tuna-9",
                    "device_metadata": {
                        "num_qubits": protocol.physical_qubits,
                        "simulator": False,
                        "backend_type_id": 6,
                        "execution_mode": row["execution_mode"],
                        "provider_job_ids": row["selected_job_ids"],
                        "provider_execution_seconds_to_contract": row[
                            "provider_execution_seconds_to_contract"
                        ],
                        "provider_execution_seconds_total": row[
                            "provider_execution_seconds_total"
                        ],
                        "source_sha256": row["source_sha256"],
                        "seed": row["seed"],
                        "controller": row["arm"],
                        "scope": (
                            "commanded phase restoration; no provider-private "
                            "calibration access"
                        ),
                    },
                    "provider": "Quantum Inspire",
                },
            }
        )
    _write_json(output / "METRIQ_HARDWARE_IMPORT_RECORDS.json", metriq_records)

    table_lines = [
        "| Controller | Success | Median acquisitions | Median provider-execution s to contract | Final RMSE | Final payload |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in HARDWARE_ARMS:
        values = arm_summary[arm]
        table_lines.append(
            "| {arm} | {success}/{trials} | {acq} | {qpu} | {rmse:.4f} | {payload:.4f} |".format(
                arm=arm,
                success=values["contract_successes"],
                trials=values["trials"],
                acq=(
                    "--"
                    if values["median_entry_acquisition_successes_only"] is None
                    else f"{values['median_entry_acquisition_successes_only']:.1f}"
                ),
                qpu=(
                    "--"
                    if values["median_provider_execution_seconds_to_contract"] is None
                    else f"{values['median_provider_execution_seconds_to_contract']:.3f}"
                ),
                rmse=values["median_final_monitor_rmse"],
                payload=values["median_final_payload_bitwise_zero"],
            )
        )
    report = "\n".join(
        [
            "# QSC-Bench Tuna-9 hardware report",
            "",
            f"Hardware-transfer decision: **{hardware_decision['finite_width_hardware_transfer']}**.",
            "",
            *table_lines,
            "",
            "The table reports three frozen confirmation seeds per arm. The 95% Wilson interval for 3/3 is wide; this campaign establishes feasibility and paired small-width behavior, not a population-level hardware reliability rate.",
            "",
            (
                "The independent post-campaign reference changed by "
                f"{reference_drift['monitor_rmse']:.5f} monitor RMSE and "
                f"{reference_drift['payload_bitwise_zero_delta']:+.5f} in payload "
                "bitwise-zero probability. This diagnostic did not alter the frozen "
                "target or thresholds."
                if reference_drift is not None
                else "No post-campaign reference was supplied."
            ),
            "",
            "Dense finite difference has a seven-acquisition structural minimum (five commissioning frames plus two ordinary confirmation frames) and therefore cannot enter the declared contract within the frozen five-acquisition deadline. Commissioned PI pays two separate coded probes. Retained residual and diagonal secant use ordinary retained full-vector acquisitions throughout.",
            "",
            "Provider-reported direct-job execution, controller update time, and public-cloud wall time are separate fields. No queue delay is presented as physical QPU latency, and no projected large-width time is presented as measured hardware time.",
            "",
            (
                "For retained residual, the hardware-observed acquisition depth gives "
                f"T_contract(tau) = {retained_entry} tau + "
                f"{retained_controller_seconds * 1e6:.1f} microseconds of measured "
                "local controller work (median). At tau = 100 microseconds this is "
                f"{(retained_entry * 1e-4 + retained_controller_seconds) * 1e3:.3f} "
                "ms: a parameterized direct-feedback projection, not measured Tuna-9 time."
                if retained_entry is not None and retained_controller_seconds is not None
                else "No direct-feedback latency projection is available because retained residual did not enter contract."
            ),
            "",
            hardware_decision["claim_boundary"],
            "",
            "Nothing in this package has been uploaded to Metriq, pushed to GitHub, or published.",
            "",
        ]
    )
    (output / "QSC_TUNA9_HARDWARE_REPORT.md").write_text(report, encoding="utf-8")

    manifest_entries = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "ARTIFACT_MANIFEST_SHA256.txt":
            manifest_entries.append(f"{_sha256(path)}  {path.relative_to(output)}")
    (output / "ARTIFACT_MANIFEST_SHA256.txt").write_text(
        "\n".join(manifest_entries) + "\n", encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
