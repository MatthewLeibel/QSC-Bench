"""Independent validation and summary of QSC-Bench hardware captures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import numpy as np

from .hardware import QIHardwareProtocol, reference_payload_threshold, score_acquisition_counts


@dataclass(frozen=True)
class ProviderTiming:
    created_on: str
    queued_at: str | None
    finished_at: str | None
    create_to_finish_seconds: float | None
    queue_to_finish_seconds: float | None
    provider_result_execution_seconds: float | None


def load_qi_capture(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("capture_schema") != "qsc-quantum-inspire-job-capture-v1":
        raise ValueError(f"unexpected Quantum Inspire capture schema in {path}")
    return data


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def provider_timing(capture: Mapping[str, Any]) -> ProviderTiming:
    job = capture["job"]
    created = _parse_datetime(job["created_on"])
    queued = _parse_datetime(job.get("queued_at"))
    finished = _parse_datetime(job.get("finished_at"))
    execution_values = [
        float(result["execution_time_in_seconds"])
        for result in capture.get("results", [])
        if result.get("execution_time_in_seconds") is not None
    ]
    return ProviderTiming(
        created_on=job["created_on"],
        queued_at=job.get("queued_at"),
        finished_at=job.get("finished_at"),
        create_to_finish_seconds=(
            None if created is None or finished is None else (finished - created).total_seconds()
        ),
        queue_to_finish_seconds=(
            None if queued is None or finished is None else (finished - queued).total_seconds()
        ),
        provider_result_execution_seconds=(
            None if not execution_values else float(sum(execution_values))
        ),
    )


def normalize_qi_reference(
    capture: Mapping[str, Any], protocol: QIHardwareProtocol
) -> dict[str, Any]:
    if capture["job"].get("status") != "completed":
        raise ValueError("reference job is not completed")
    results = capture.get("results", [])
    if len(results) != 1 or not isinstance(results[0].get("results"), dict):
        raise ValueError("reference job must expose exactly one histogram result")
    provider_result = results[0]
    if provider_result.get("shots_done") != provider_result.get("shots_requested"):
        raise ValueError("reference job did not complete every requested shot")
    scores = score_acquisition_counts(provider_result["results"], protocol)
    return {
        "job_id": int(capture["job"]["id"]),
        "shots_requested": int(provider_result["shots_requested"]),
        "shots_done": int(provider_result["shots_done"]),
        "monitor_target": list(scores.monitor_response),
        "payload_reference_bitwise_zero": scores.payload_bitwise_zero,
        "payload_reference_all_zero": scores.payload_all_zero,
        "payload_threshold": reference_payload_threshold(
            scores.payload_bitwise_zero, protocol
        ),
        "timing": asdict(provider_timing(capture)),
    }


def _row_passes(
    row: Mapping[str, Any], protocol: QIHardwareProtocol, payload_threshold: float
) -> bool:
    return (
        bool(row.get("contract_eligible"))
        and float(row["monitor_rmse"]) <= protocol.monitor_tolerance
        and float(row["payload_bitwise_zero"]) >= payload_threshold
    )


def _recompute_entry(
    trace: Sequence[Mapping[str, Any]],
    protocol: QIHardwareProtocol,
    payload_threshold: float,
) -> int | None:
    required = protocol.required_consecutive
    for stop in range(required, len(trace) + 1):
        if all(
            _row_passes(row, protocol, payload_threshold)
            for row in trace[stop - required : stop]
        ):
            return stop
    return None


def _normalize_final_payload(
    final: Mapping[str, Any], protocol: QIHardwareProtocol
) -> dict[str, Any]:
    trace = final.get("trace", [])
    if len(trace) != protocol.acquisitions:
        raise ValueError("hardware run did not return the frozen acquisition count")
    for expected, row in enumerate(trace, start=1):
        if int(row["acquisition"]) != expected:
            raise ValueError("hardware acquisition indices are not contiguous")
        if int(row["shots_done"]) != int(row["shots_requested"]):
            raise ValueError("hardware acquisition has incomplete shots")
    threshold = float(final["payload_threshold"])
    entry = _recompute_entry(trace, protocol, threshold)
    at_deadline = all(
        _row_passes(row, protocol, threshold)
        for row in trace[-protocol.required_consecutive :]
    )
    if final.get("contract_entry_acquisition") != entry:
        raise ValueError("reported and independent contract-entry calculations disagree")
    if bool(final.get("contract_at_deadline")) != at_deadline:
        raise ValueError("reported and independent deadline calculations disagree")
    return {
        "arm": str(final["arm"]),
        "seed": int(final["seed"]),
        "contract_entry_acquisition": entry,
        "contract_success": entry is not None,
        "contract_at_deadline": at_deadline,
        "final_monitor_rmse": float(trace[-1]["monitor_rmse"]),
        "final_payload_bitwise_zero": float(trace[-1]["payload_bitwise_zero"]),
        "monitor_rmse_at_entry": (
            None if entry is None else float(trace[int(entry) - 1]["monitor_rmse"])
        ),
        "payload_bitwise_zero_at_entry": (
            None
            if entry is None
            else float(trace[int(entry) - 1]["payload_bitwise_zero"])
        ),
        "minimum_monitor_rmse": min(float(row["monitor_rmse"]) for row in trace),
        "ordinary_acquisitions": sum(bool(row["contract_eligible"]) for row in trace),
        "discarded_probe_acquisitions": sum(
            not bool(row["contract_eligible"]) for row in trace
        ),
        "shots_requested": sum(int(row["shots_requested"]) for row in trace),
        "shots_done": sum(int(row["shots_done"]) for row in trace),
        "controller_update_seconds": sum(
            float(row["controller_update_seconds"]) for row in trace
        ),
        "controller_update_seconds_to_contract": (
            None
            if entry is None
            else sum(
                float(row["controller_update_seconds"])
                for row in trace[: int(entry)]
            )
        ),
        "structural_minimum_acquisitions_to_confirm": int(
            final["structural_minimum_acquisitions_to_confirm"]
        ),
        "trace": trace,
    }


def normalize_qi_hybrid_capture(
    capture: Mapping[str, Any], protocol: QIHardwareProtocol
) -> dict[str, Any]:
    if capture["job"].get("status") != "completed":
        raise ValueError("hybrid job is not completed")
    wrapper = capture.get("final_result")
    if not wrapper or not isinstance(wrapper.get("final_result"), dict):
        raise ValueError("hybrid job has no final result")
    final = wrapper["final_result"]
    normalized = _normalize_final_payload(final, protocol)
    normalized.update(
        {
        "job_id": int(capture["job"]["id"]),
        "hybrid_execute_call_seconds": sum(
            float(row["hybrid_execute_call_seconds"]) for row in normalized["trace"]
        ),
        "server_total_elapsed_seconds": float(final["server_total_elapsed_seconds"]),
        "timing": asdict(provider_timing(capture)),
        }
    )
    return normalized


def normalize_qi_sequential_run(
    run: Mapping[str, Any], protocol: QIHardwareProtocol
) -> dict[str, Any]:
    if run.get("capture_schema") != "qsc-qi-sequential-hardware-run-v1":
        raise ValueError("unexpected sequential-run schema")
    calls = run.get("sequential_calls", [])
    if len(calls) != protocol.acquisitions:
        raise ValueError("sequential run does not contain the frozen number of calls")
    final = run.get("final_result")
    if not isinstance(final, dict):
        raise ValueError("sequential run has no final result")
    normalized = _normalize_final_payload(final, protocol)
    selected_jobs: list[int] = []
    execution_seconds: list[float] = []
    call_timings: list[dict[str, Any]] = []
    infrastructure_failures = 0
    for expected, call in enumerate(calls, start=1):
        if int(call["acquisition"]) != expected:
            raise ValueError("sequential call indices are not contiguous")
        attempts = call.get("attempts", [])
        infrastructure_failures += sum(
            attempt["job"].get("status") != "completed" for attempt in attempts
        )
        selected_job_id = call.get("selected_job_id")
        selected = [
            attempt
            for attempt in attempts
            if int(attempt["job"]["id"]) == int(selected_job_id)
        ] if selected_job_id is not None else []
        if len(selected) != 1 or selected[0]["job"].get("status") != "completed":
            raise ValueError("sequential call has no unique completed selected job")
        capture = selected[0]
        results = capture.get("results", [])
        if len(results) != 1:
            raise ValueError("selected direct job does not have exactly one result")
        result = results[0]
        if int(result["shots_done"]) != int(result["shots_requested"]):
            raise ValueError("selected direct job has incomplete shots")
        selected_jobs.append(int(selected_job_id))
        execution_seconds.append(float(result["execution_time_in_seconds"]))
        call_timings.append(asdict(provider_timing(capture)))
    normalized.update(
        {
            "execution_mode": "client_orchestrated_sequential_direct_qpu_jobs",
            "source_sha256": str(run["source_sha256"]),
            "capture_completed_at": str(run["completed_at"]),
            "selected_job_ids": selected_jobs,
            "provider_execution_seconds_by_acquisition": execution_seconds,
            "provider_execution_seconds_total": float(sum(execution_seconds)),
            "client_wall_seconds": float(run["client_wall_seconds"]),
            "infrastructure_failures": int(infrastructure_failures),
            "orchestration_resumed": bool(run.get("orchestration_resumed", False)),
            "network_retry_count": int(run.get("network_retry_count", 0)),
            "resume_events": list(run.get("resume_events", [])),
            "direct_job_timings": call_timings,
        }
    )
    entry = normalized["contract_entry_acquisition"]
    normalized["provider_execution_seconds_to_contract"] = (
        None if entry is None else float(sum(execution_seconds[: int(entry)]))
    )
    provider_job_wall = [
        timing["create_to_finish_seconds"] for timing in call_timings
    ]
    normalized["provider_job_create_to_finish_seconds_total"] = (
        None
        if any(value is None for value in provider_job_wall)
        else float(sum(float(value) for value in provider_job_wall))
    )
    normalized["provider_job_create_to_finish_seconds_to_contract"] = (
        None
        if entry is None
        or any(value is None for value in provider_job_wall[: int(entry)])
        else float(sum(float(value) for value in provider_job_wall[: int(entry)]))
    )
    return normalized


def summarize_hardware_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(str(row["arm"]), []).append(row)
    summary: dict[str, Any] = {}
    for arm, arm_rows in sorted(by_arm.items()):
        entries = [
            int(row["contract_entry_acquisition"])
            for row in arm_rows
            if row.get("contract_entry_acquisition") is not None
        ]
        summary[arm] = {
            "trials": len(arm_rows),
            "contract_successes": sum(bool(row["contract_success"]) for row in arm_rows),
            "contract_at_deadline": sum(
                bool(row["contract_at_deadline"]) for row in arm_rows
            ),
            "median_entry_acquisition_successes_only": (
                None if not entries else float(median(entries))
            ),
            "median_final_monitor_rmse": float(
                np.median([float(row["final_monitor_rmse"]) for row in arm_rows])
            ),
            "median_final_payload_bitwise_zero": float(
                np.median(
                    [float(row["final_payload_bitwise_zero"]) for row in arm_rows]
                )
            ),
            "total_controller_update_seconds": float(
                sum(float(row["controller_update_seconds"]) for row in arm_rows)
            ),
        }
    return summary
