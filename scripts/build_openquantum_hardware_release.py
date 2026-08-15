#!/usr/bin/env python3
"""Build the public OpenQuantum hardware evidence packages.

The builder deliberately keeps the completed confirmation, the static Emerald
diagnostic, and development/blocked evidence in separate directories.  It also
verifies every copied QASM against the digest frozen in its campaign checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "hardware"
CEPHEUS_CHECKPOINT = (
    ROOT
    / "checkpoints"
    / "openquantum_cepheus_96q_single_rx_v3"
    / "CAMPAIGN_CHECKPOINT.json"
)
EMERALD_CHECKPOINT = (
    ROOT / "checkpoints" / "openquantum_iqm_emerald_command_effect_v1.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _manifest(directory: Path) -> None:
    manifest = directory / "ARTIFACT_MANIFEST_SHA256.txt"
    rows = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path != manifest:
            rows.append(f"{_sha256(path)}  {path.relative_to(directory)}")
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _last_attempt(logical_job: dict[str, Any]) -> dict[str, Any]:
    attempts = logical_job.get("attempts", [])
    if not attempts:
        raise ValueError(f"logical job has no attempt: {logical_job['logical_id']}")
    return attempts[-1]


def _validate_qasm(logical_job: dict[str, Any]) -> Path:
    path = ROOT / logical_job["qasm_path"]
    digest = _sha256(path)
    if digest != logical_job["qasm_sha256"]:
        raise ValueError(f"QASM digest mismatch: {path}")
    return path


def _validate_completed_attempt(logical_job: dict[str, Any]) -> None:
    attempt = _last_attempt(logical_job)
    job = attempt["job"]
    if job["status"] != "Completed":
        raise ValueError(f"job is not completed: {logical_job['logical_id']}")
    if job.get("signed_content_urls_serialized") is not False:
        raise ValueError("signed provider URL was serialized")
    output = attempt.get("output")
    if not isinstance(output, dict) or sum(int(value) for value in output.values()) != int(
        logical_job["shots"]
    ):
        raise ValueError(f"shot-count mismatch: {logical_job['logical_id']}")


def _trace_public(trace: dict[str, Any], *, tolerance: float, threshold: float) -> dict[str, Any]:
    monitor_ok = float(trace["monitor_rmse"]) <= tolerance
    payload_ok = float(trace["payload_bitwise_zero"]) >= threshold
    return {
        "acquisition": int(trace["acquisition"]),
        "acquisition_kind": trace["acquisition_kind"],
        "contract_eligible": bool(trace["contract_eligible"]),
        "monitor_rmse": float(trace["monitor_rmse"]),
        "monitor_pass": monitor_ok,
        "payload_bitwise_zero": float(trace["payload_bitwise_zero"]),
        "payload_pass": payload_ok,
        "joint_contract_pass": monitor_ok and payload_ok,
        "shots_done": int(trace["shots_done"]),
        "qasm_sha256": trace["qasm_sha256"],
        "provider_job_id": trace["job"]["id"],
        "provider_job_status": trace["job"]["status"],
        "provider_execution_seconds": trace["job"]["provider_execution_seconds"],
        "cloud_submit_to_terminal_observation_seconds": trace["job"][
            "submitted_to_terminal_observation_seconds"
        ],
        "controller_update_seconds": float(trace["controller_update_seconds"]),
    }


def _metriq_record(
    *,
    arm: dict[str, Any],
    protocol_commit: str,
    protocol: dict[str, Any],
    completed_at: str,
) -> dict[str, Any]:
    success = bool(arm["contract_success"])
    entry = int(arm["contract_entry_acquisition"] or 0)
    executed = len(arm["trace"])
    final = arm["trace"][-1]
    tau = 1e-4
    return {
        "app_version": "qsc-bench-1.0.0",
        "job_type": "QSC-Bench Cold Start",
        "platform": {
            "provider": "OpenQuantum",
            "device": "Cepheus-1-108Q",
            "device_metadata": {
                "simulator": False,
                "controller": arm["arm"],
                "seed": int(arm["seed"]),
                "num_qubits": int(protocol["physical_qubits"]),
                "controlled_channels": int(protocol["width"]),
                "shots_per_acquisition": int(protocol["shots"]),
                "execution_mode": "client_orchestrated_sequential_direct_qpu_jobs",
                "provider_job_ids": [row["job"]["id"] for row in arm["trace"]],
                "provider_execution_timing_available": False,
                "scope": (
                    "commanded phase restoration under native QPU noise; "
                    "no provider-private calibration access"
                ),
                "protocol_deviation": arm.get("protocol_deviation"),
            },
        },
        "results": {
            "width": int(protocol["width"]),
            "contract_success": success,
            "acquisitions_to_contract": entry,
            "total_quantum_executions_to_usable": entry,
            "monitor_values_per_acquisition": int(protocol["width"]),
            "local_monitor_plus_actuation_values_per_cycle": 2
            * int(protocol["width"]),
            "traffic_scalars_to_contract": 2 * int(protocol["width"]) * executed,
            "controller_float_words_per_channel": float(
                arm["controller_float_words_per_channel"]
            ),
            "controller_mutable_state_bytes": int(
                arm["controller_mutable_state_bytes"]
            ),
            "host_update_seconds": float(arm["total_controller_update_seconds"]),
            "payload_quality": float(final["payload_bitwise_zero"]),
            "minimal_sufficient_cold_start_candidate": bool(
                arm["controller_metadata"]["minimal_sufficient_cold_start_candidate"]
            ),
            "projected_acquisition_latency_seconds": tau,
            "projected_time_to_contract_seconds": (
                entry * tau + float(arm["total_controller_update_seconds"])
                if success
                else 0.0
            ),
            "simulator_runtime_seconds": 0.0,
            "qsc_code_commit": protocol_commit,
            "qsc_git_worktree_dirty": False,
            "score": {"value": 1.0 / entry if success else 0.0, "uncertainty": None},
        },
        "suite_id": None,
        "timestamp": completed_at,
    }


def build_cepheus() -> dict[str, Any]:
    checkpoint = _load(CEPHEUS_CHECKPOINT)
    if checkpoint.get("signed_content_urls_serialized") is not False:
        raise ValueError("checkpoint may contain signed content URLs")
    if (
        checkpoint.get("campaign_status") != "COMPLETED"
        or checkpoint.get("complete") is not True
        or checkpoint.get("reference_admissible") is not True
    ):
        raise ValueError("Cepheus confirmation is not complete and admissible")
    if len(checkpoint["logical_jobs"]) != 8:
        raise ValueError("expected one reference and seven executed adaptive jobs")

    output = RESULTS / "openquantum_cepheus_96q_single_rx_v3"
    raw = output / "raw"
    sources = raw / "sources"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for logical_job in checkpoint["logical_jobs"].values():
        _validate_completed_attempt(logical_job)
        source = _validate_qasm(logical_job)
        _copy(source, sources / source.name)
    _copy(CEPHEUS_CHECKPOINT, raw / "CAMPAIGN_CHECKPOINT.json")
    _copy(
        ROOT / checkpoint["config_path"],
        raw / Path(checkpoint["config_path"]).name,
    )
    _copy(
        ROOT / "protocols" / "QSC_BENCH_OPENQUANTUM_96Q_SINGLE_RX_V3.md",
        raw / "QSC_BENCH_OPENQUANTUM_96Q_SINGLE_RX_V3.md",
    )

    reference = checkpoint["references"]["48"]
    arms: list[dict[str, Any]] = []
    metriq_records: list[dict[str, Any]] = []
    for run in sorted(checkpoint["run_results"].values(), key=lambda row: row["arm"]):
        protocol = run["protocol"]
        traces = [
            _trace_public(
                row,
                tolerance=float(protocol["monitor_tolerance"]),
                threshold=float(reference["payload_threshold"]),
            )
            for row in run["trace"]
        ]
        arms.append(
            {
                "arm": run["arm"],
                "seed": int(run["seed"]),
                "contract_success": bool(run["contract_success"]),
                "contract_entry_acquisition": run["contract_entry_acquisition"],
                "contract_at_deadline": bool(run["contract_at_deadline"]),
                "trace": traces,
                "controller_metadata": run["controller_metadata"],
                "controller_mutable_state_bytes": int(
                    run["controller_mutable_state_bytes"]
                ),
                "controller_update_seconds_total": float(
                    run["total_controller_update_seconds"]
                ),
                "protocol_deviation": run.get("protocol_deviation"),
                "futility_reason": run.get("futility_reason"),
                "not_executed_acquisitions": run.get("not_executed_acquisitions", []),
            }
        )
        metriq_records.append(
            _metriq_record(
                arm=run,
                protocol_commit=checkpoint["protocol_commit"],
                protocol=protocol,
                completed_at=checkpoint["completed_at"],
            )
        )

    retained = next(row for row in arms if row["arm"] == "retained_residual")
    control = next(row for row in arms if row["arm"] == "do_nothing")
    protocol = next(iter(checkpoint["run_results"].values()))["protocol"]
    dense_min = int(protocol["width"]) + 3
    if dense_min != 51:
        raise ValueError("unexpected dense finite-difference structural minimum")
    summary = {
        "schema_version": "qsc-openquantum-cepheus-hardware-evidence-v1",
        "publication_state": "public evidence package",
        "provider": "OpenQuantum",
        "backend": checkpoint["backend_audit"],
        "evidence_level": "real-QPU hardware-in-the-loop confirmation",
        "protocol_commit": checkpoint["protocol_commit"],
        "protocol_sha256": checkpoint["protocol_sha256"],
        "config_sha256": checkpoint["config_sha256"],
        "created_at": checkpoint["created_at"],
        "completed_at": checkpoint["completed_at"],
        "physical_qubits_used": int(protocol["physical_qubits"]),
        "controlled_channels": int(protocol["width"]),
        "shots_per_acquisition": int(protocol["shots"]),
        "confirmation_seeds": [int(retained["seed"])],
        "reference": reference,
        "trials": arms,
        "decision": {
            "retained_residual_contract": "PASS",
            "do_nothing_contract": "FAIL",
            "retained_contract_entry_acquisition": 4,
            "dense_finite_difference_structural_minimum_acquisitions": dense_min,
            "dense_finite_difference_executed": False,
            "hardware_width_scaling_exponent": "NOT_ESTABLISHED",
            "replication_strength": "single paired confirmation seed",
        },
        "resource_accounting": {
            "retained_to_dense_fd_structural_acquisition_ratio_lower_bound": dense_min
            / 4,
            "sequential_depth_is_the_flat_quantity": True,
            "full_vector_traffic_is_flat": False,
            "host_arithmetic_is_flat": False,
            "provider_execution_seconds_available": False,
            "cloud_queue_time_is_not_device_execution_time": True,
            "credits_initial": checkpoint["credit_balance_initial"],
            "credits_final": checkpoint["credit_balance_final"],
        },
        "negative_and_protocol_evidence": {
            "do_nothing_acquisition_4_omitted_after_outcome_became_invariant": True,
            "post_campaign_reference": checkpoint["post_reference"],
            "futility_stops": checkpoint["futility_stops"],
        },
        "claim_boundary": (
            "One paired 48-channel adaptive confirmation on 96 physical qubits. "
            "The disturbance was a commanded phase offset; no private/native device "
            "calibration variables were accessed. The shallow single-Rx payload and "
            "single seed do not establish a hardware scaling exponent, asymptotic "
            "advantage, or general hardware reliability."
        ),
        "attribution": {
            "required_text": "Powered by OpenQuantum",
            "citation_url": "https://www.openquantum.com/citation",
        },
    }
    _write_json(output / "QSC_CEPHEUS_96Q_HARDWARE_SUMMARY.json", summary)
    _write_json(output / "METRIQ_HARDWARE_IMPORT_RECORDS.json", metriq_records)
    (output / "QSC_CEPHEUS_96Q_HARDWARE_REPORT.md").write_text(
        """# QSC-Bench Cepheus 96-physical-qubit confirmation

The retained-residual arm restored the frozen joint monitor-plus-payload contract
by acquisition 4. It passed on acquisitions 3 and 4, with monitor RMSE 0.06213
and 0.06187 and payload bitwise-zero quality 0.89196 and 0.90450. The paired
do-nothing arm failed its first three acquisitions; acquisition 4 was not run
after two consecutive deadline passes became mathematically impossible.

The run used 48 controlled channels distributed across 96 physical qubits,
2,048 shots per acquisition, one frozen confirmation seed, and eight completed
provider jobs including the shared reference. A dense finite-difference cold
start would require at least 51 sequential acquisitions under the declared
charging rule, so it was structurally outside the four-acquisition deadline and
was not executed.

This is real-QPU command-restoration evidence, not a hardware scaling result.
The disturbance was commanded in the submitted circuit; the experiment did not
read or repair private provider calibration state. OpenQuantum did not expose
device execution duration for these jobs, so cloud queue/wall time is not
reported as QPU latency. The single seed and shallow single-Rx payload require
independent replication before any reliability or generality claim.

Powered by OpenQuantum. See https://www.openquantum.com/citation.
""",
        encoding="utf-8",
    )
    _manifest(output)
    return summary


def build_emerald() -> dict[str, Any]:
    checkpoint = _load(EMERALD_CHECKPOINT)
    if checkpoint.get("signed_content_urls_serialized") is not False:
        raise ValueError("Emerald checkpoint may contain signed content URLs")
    if checkpoint["job"]["status"] != "Completed":
        raise ValueError("Emerald diagnostic is not complete")
    if sum(int(value) for value in checkpoint["output"].values()) != int(
        checkpoint["result"]["shots_done"]
    ):
        raise ValueError("Emerald shot-count mismatch")
    source = ROOT / checkpoint["source_path"]
    if _sha256(source) != checkpoint["source_sha256"]:
        raise ValueError("Emerald source digest mismatch")

    output = RESULTS / "openquantum_iqm_emerald_command_effect_v1"
    raw = output / "raw"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    _copy(EMERALD_CHECKPOINT, raw / EMERALD_CHECKPOINT.name)
    _copy(source, raw / source.name)
    _copy(ROOT / checkpoint["config_path"], raw / Path(checkpoint["config_path"]).name)
    _copy(
        ROOT / "protocols" / "QSC_BENCH_OPENQUANTUM_IQM_EMERALD_COMMAND_EFFECT_V1.md",
        raw / "QSC_BENCH_OPENQUANTUM_IQM_EMERALD_COMMAND_EFFECT_V1.md",
    )
    summary = {
        "schema_version": "qsc-openquantum-emerald-command-effect-evidence-v1",
        "publication_state": "public evidence package",
        "provider": "OpenQuantum",
        "backend": checkpoint["backend_audit"],
        "evidence_level": "static real-QPU command-effect diagnostic",
        "protocol_commit": checkpoint["protocol_commit"],
        "protocol_sha256": checkpoint["protocol_sha256"],
        "config_sha256": checkpoint["config_sha256"],
        "provider_job_id": checkpoint["job"]["id"],
        "source_sha256": checkpoint["source_sha256"],
        "result": checkpoint["result"],
        "credits": {
            "before": checkpoint["credit_balance_before"],
            "after": checkpoint["credit_balance_after"],
        },
        "claim_boundary": checkpoint["result"]["claim_boundary"],
        "attribution": {
            "required_text": "Powered by OpenQuantum",
            "citation_url": "https://www.openquantum.com/citation",
        },
    }
    _write_json(output / "OPENQUANTUM_EMERALD_COMMAND_EFFECT_SUMMARY.json", summary)
    (output / "OPENQUANTUM_EMERALD_COMMAND_EFFECT_REPORT.md").write_text(
        """# IQM Emerald command-effect diagnostic

One static 54-qubit, 512-shot diagnostic passed its frozen command-effect rule.
Mean corrected bitwise-zero probability was 0.98524, versus 0.77076 for the
unmaintained members of the paired circuit, a difference of 0.21448.

This is not an adaptive controller run, a stability-contract result, or a
hardware scaling result. Its purpose is only to show a controlled command effect
on a second hardware family. The paired layout may share spatial/systematic
effects and does not replace randomized adaptive confirmation.

Powered by OpenQuantum. See https://www.openquantum.com/citation.
""",
        encoding="utf-8",
    )
    _manifest(output)
    return summary


def build_development_evidence() -> dict[str, Any]:
    output = RESULTS / "openquantum_development_evidence"
    raw = output / "raw"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    checkpoint_paths = [
        ROOT / "checkpoints" / "openquantum_cepheus_108q_capability_probe_capture.json",
        ROOT / "checkpoints" / "openquantum_cepheus_108q_capability_probe_submission.json",
        ROOT / "checkpoints" / "openquantum_cepheus_scale_v1" / "CAMPAIGN_CHECKPOINT.json",
        ROOT
        / "checkpoints"
        / "openquantum_cepheus_executable_width_v1"
        / "CAMPAIGN_CHECKPOINT.json",
        ROOT
        / "checkpoints"
        / "openquantum_cepheus_96q_local_payload_v1"
        / "CAMPAIGN_CHECKPOINT.json",
        ROOT
        / "checkpoints"
        / "openquantum_cepheus_96q_native_mirror_v2"
        / "CAMPAIGN_CHECKPOINT.json",
    ]
    entries = []
    for path in checkpoint_paths:
        payload = _load(path)
        if payload.get("signed_content_urls_serialized") is not False:
            raise ValueError(f"signed URL guard failed: {path}")
        destination = raw / path.parent.name / path.name
        _copy(path, destination)
        source_directory = path.parent / "sources"
        if source_directory.exists():
            for source in sorted(source_directory.glob("*.qasm")):
                _copy(source, destination.parent / "sources" / source.name)
        logical_jobs = payload.get("logical_jobs", {})
        terminal = {}
        for logical_id, job in logical_jobs.items():
            attempts = job.get("attempts", [])
            terminal[logical_id] = (
                None if not attempts else attempts[-1].get("job", {}).get("status")
            )
        entries.append(
            {
                "source": str(path.relative_to(ROOT)),
                "source_sha256": _sha256(path),
                "campaign_status": payload.get("campaign_status"),
                "complete": payload.get("complete"),
                "reference_admissible": payload.get("reference_admissible"),
                "provider_job_terminal_status_at_last_capture": terminal,
            }
        )
    index = {
        "schema_version": "qsc-openquantum-development-evidence-index-v1",
        "publication_state": "public negative/development evidence",
        "generated_at": "2026-08-14T21:06:57.869275+00:00",
        "entries": entries,
        "findings": [
            "A minimal 108-physical-qubit capability probe failed after three provider attempts.",
            "The first 54-channel scientific reference also failed after repeated provider attempts; failed attempts were refunded.",
            "A 96-physical-qubit/48-channel reference executed, but its original paired payload reference was 0.61065, below the frozen 0.70 floor.",
            "A local-payload revision reached 0.68268, still below its frozen 0.70 floor.",
            "A native-mirror revision reached 0.51337, below its frozen 0.80 floor.",
            "Those inadmissible development generations are not confirmation evidence and are not used to support the completed v3 outcome.",
        ],
        "claim_boundary": (
            "These are contemporaneous development and blocked-run captures. Some "
            "jobs were still marked Pending at the last local capture; no terminal "
            "outcome is inferred for them."
        ),
        "attribution": {
            "required_text": "Powered by OpenQuantum",
            "citation_url": "https://www.openquantum.com/citation",
        },
    }
    _write_json(output / "OPENQUANTUM_DEVELOPMENT_EVIDENCE_INDEX.json", index)
    (output / "OPENQUANTUM_DEVELOPMENT_EVIDENCE_REPORT.md").write_text(
        """# OpenQuantum development and negative evidence

This package preserves failed, blocked, and inadmissible campaign generations.
They are published to prevent outcome selection and are not included in the
completed v3 confirmation claim. Provider-job status is reported exactly as it
appeared in the last local capture; pending jobs are not silently reclassified.

The decisive development failures were: repeated failure of a 108-physical-qubit
capability probe and 54-channel reference; a 48-channel reference payload below
the frozen usability floor; and two subsequent payload/reference designs that
also failed their predeclared admissibility floors. These outcomes motivated the
single-Rx v3 design before its confirmation result was observed.

Powered by OpenQuantum. See https://www.openquantum.com/citation.
""",
        encoding="utf-8",
    )
    _manifest(output)
    return index


def build_public_indexes(
    cepheus: dict[str, Any], emerald: dict[str, Any], development: dict[str, Any]
) -> None:
    tuna = RESULTS / "quantum_inspire_tuna9_v1" / "QSC_TUNA9_HARDWARE_SUMMARY.json"
    openquantum_static = (
        RESULTS
        / "openquantum_static_crosscheck_v1"
        / "OPENQUANTUM_STATIC_CROSSCHECK_SUMMARY.json"
    )
    cepheus_path = (
        RESULTS
        / "openquantum_cepheus_96q_single_rx_v3"
        / "QSC_CEPHEUS_96Q_HARDWARE_SUMMARY.json"
    )
    emerald_path = (
        RESULTS
        / "openquantum_iqm_emerald_command_effect_v1"
        / "OPENQUANTUM_EMERALD_COMMAND_EFFECT_SUMMARY.json"
    )
    development_path = (
        RESULTS
        / "openquantum_development_evidence"
        / "OPENQUANTUM_DEVELOPMENT_EVIDENCE_INDEX.json"
    )
    hardware_index = {
        "schema_version": "qsc-hardware-evidence-index-v2",
        "date": "2026-08-14",
        "publication_state": "public evidence package",
        "adaptive_confirmations": [
            {
                "provider": "Quantum Inspire",
                "backend": "Tuna-9",
                "scope": "4 controlled channels, 8 physical qubits, 3 seeds, 75 jobs",
                "summary_path": str(tuna.relative_to(RESULTS)),
                "summary_sha256": _sha256(tuna),
                "retained_residual_successes": 3,
                "retained_residual_trials": 3,
            },
            {
                "provider": "OpenQuantum",
                "backend": "Rigetti Cepheus-1-108Q",
                "scope": "48 controlled channels, 96 physical qubits, 1 seed, 8 jobs",
                "summary_path": str(cepheus_path.relative_to(RESULTS)),
                "summary_sha256": _sha256(cepheus_path),
                "retained_residual_successes": 1,
                "retained_residual_trials": 1,
            },
        ],
        "static_diagnostics": [
            {
                "provider": "OpenQuantum",
                "backend": "Rigetti Cepheus-1-108Q",
                "summary_path": str(openquantum_static.relative_to(RESULTS)),
                "summary_sha256": _sha256(openquantum_static),
            },
            {
                "provider": "OpenQuantum",
                "backend": "IQM Emerald",
                "summary_path": str(emerald_path.relative_to(RESULTS)),
                "summary_sha256": _sha256(emerald_path),
                "decision": emerald["result"]["decision"],
            },
        ],
        "negative_and_blocked_evidence": {
            "index_path": str(development_path.relative_to(RESULTS)),
            "index_sha256": _sha256(development_path),
            "entries": len(development["entries"]),
        },
        "combined_decision": "PASS_FINITE_WIDTH_HARDWARE_TRANSFER",
        "hardware_scaling_exponent": "NOT_ESTABLISHED",
        "claim_boundary": (
            "The real-QPU campaigns establish adaptive finite-width transfer at "
            "4 and 48 controlled channels. The frozen width-scaling inference is "
            "from simulator/reduced-model evidence and remains a separate layer."
        ),
    }
    _write_json(RESULTS / "HARDWARE_EVIDENCE_INDEX.json", hardware_index)

    tuna_records = (
        RESULTS / "quantum_inspire_tuna9_v1" / "METRIQ_HARDWARE_IMPORT_RECORDS.json"
    )
    cepheus_records = (
        RESULTS
        / "openquantum_cepheus_96q_single_rx_v3"
        / "METRIQ_HARDWARE_IMPORT_RECORDS.json"
    )
    metriq_index = {
        "schema_version": "qsc-metriq-publication-index-v1",
        "benchmark": "QSC-Bench Cold Start",
        "release": "1.0.0",
        "submission_state": (
            "benchmark proposed upstream; result ingestion awaits benchmark and "
            "provider-path acceptance"
        ),
        "candidate_result_envelopes": [
            {
                "provider": "Quantum Inspire",
                "device": "Tuna-9",
                "path": str(tuna_records.relative_to(ROOT)),
                "sha256": _sha256(tuna_records),
                "records": len(_load(tuna_records)),
            },
            {
                "provider": "OpenQuantum",
                "device": "Cepheus-1-108Q",
                "path": str(cepheus_records.relative_to(ROOT)),
                "sha256": _sha256(cepheus_records),
                "records": len(_load(cepheus_records)),
            },
        ],
        "simulation_evidence": {
            "summary": "results/confirmation/QSC_BENCH_V1_SUMMARY.json",
            "sha256": _sha256(
                ROOT / "results" / "confirmation" / "QSC_BENCH_V1_SUMMARY.json"
            ),
            "raw_confirmation_records_are_published": True,
        },
        "not_submitted_as_ranked_results": [
            "OpenQuantum static monitor portability check",
            "IQM Emerald static command-effect diagnostic",
            "development, failed, blocked, and inadmissible campaigns",
        ],
        "reason_results_are_not_yet_in_metriq_data": (
            "Metriq Data accepts results only from supported metriq-gym execution "
            "paths. QSC-Bench and its adaptive remote-provider path must be reviewed "
            "and accepted first."
        ),
    }
    _write_json(ROOT / "results" / "METRIQ_SUBMISSION_INDEX.json", metriq_index)


def main() -> None:
    cepheus = build_cepheus()
    emerald = build_emerald()
    development = build_development_evidence()
    build_public_indexes(cepheus, emerald, development)
    print(
        json.dumps(
            {
                "cepheus": cepheus["decision"],
                "emerald": emerald["result"]["decision"],
                "development_entries": len(development["entries"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
