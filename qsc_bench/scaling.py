"""Auditable architecture projections from measured QSC-Bench acquisition counts.

This module never turns a projection into a measurement.  It combines measured
development or confirmation records with explicit structural costs for methods
whose first complete update requires a channel sweep.  Acquisition latency,
host work, interface traffic, and state are kept as separate axes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Iterable

import numpy as np


def _analysis_revision() -> tuple[str | None, bool | None]:
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def _load_bundle(path: str | Path) -> tuple[Path, dict[str, Any], str]:
    source = Path(path)
    raw = source.read_bytes()
    bundle = json.loads(raw)
    if not isinstance(bundle, dict) or not isinstance(bundle.get("records"), list):
        raise ValueError("measured result bundle must contain a records array")
    return source, bundle, hashlib.sha256(raw).hexdigest()


def _qualifying_anchors(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        metadata = record.get("controller_metadata", {})
        if not metadata.get("minimal_sufficient_cold_start_candidate", False):
            continue
        groups.setdefault(str(record["controller"]), []).append(record)

    anchors: list[dict[str, Any]] = []
    for controller, group in sorted(groups.items()):
        successes = [r for r in group if r.get("contract_success")]
        if len(successes) != len(group):
            # A no-growth projection must not be anchored to a controller that
            # already crossed its observed operability boundary. Failures remain
            # in the source result bundle and campaign analysis.
            continue
        counts = [int(r["acquisitions_to_contract"]) for r in successes]
        largest_width = max(int(r["width"]) for r in group)
        largest_successes = [
            r for r in successes if int(r["width"]) == largest_width
        ]
        normalized_host = [
            float(r["host_update_seconds"]) / largest_width
            for r in largest_successes
            if r.get("host_update_seconds") is not None
        ]
        anchors.append(
            {
                "controller": controller,
                "observed_widths": sorted({int(r["width"]) for r in group}),
                "runs": len(group),
                "successes": len(successes),
                "failures": len(group) - len(successes),
                "success_rate": len(successes) / len(group),
                "observed_acquisition_min": min(counts) if counts else None,
                "observed_acquisition_median": (
                    float(sorted(counts)[len(counts) // 2])
                    if len(counts) % 2 == 1
                    else float(
                        (sorted(counts)[len(counts) // 2 - 1] + sorted(counts)[len(counts) // 2])
                        / 2
                    )
                    if counts
                    else None
                ),
                "observed_acquisition_max": max(counts) if counts else None,
                "projection_anchor_acquisitions": max(counts) if counts else None,
                "largest_measured_width": largest_width,
                "largest_width_host_seconds_per_channel_p95": (
                    float(np.quantile(np.asarray(normalized_host), 0.95))
                    if normalized_host
                    else None
                ),
                "largest_width_state_bytes_per_channel": (
                    max(
                        float(r["controller_mutable_state_bytes"]) / largest_width
                        for r in largest_successes
                        if r.get("controller_mutable_state_bytes") is not None
                    )
                    if any(
                        r.get("controller_mutable_state_bytes") is not None
                        for r in largest_successes
                    )
                    else None
                ),
                "anchor_rule": "worst successful measured run; no failed run is imputed",
                "projection_condition": (
                    "Hypothetical no-growth continuation of the measured acquisition-depth "
                    "envelope. It is not evidence at unmeasured widths."
                ),
            }
        )
    return anchors


def _seconds_label(seconds: float) -> str:
    if seconds < 1e-3:
        return f"{seconds * 1e6:.3g} us"
    if seconds < 1:
        return f"{seconds * 1e3:.3g} ms"
    if seconds < 86400:
        return f"{seconds:.3g} s"
    days = seconds / 86400
    if days < 365.25 * 2:
        return f"{days:.3g} days"
    return f"{days / 365.25:.3g} years"


def _time_record(
    acquisitions: int,
    latency: float,
    *,
    projected_host_seconds: float | None = None,
    interface_total_bytes: int | None = None,
    bandwidths_bytes_per_second: Iterable[float] = (),
) -> dict[str, Any]:
    seconds = acquisitions * latency
    record: dict[str, Any] = {
        "sequential_acquisitions": acquisitions,
        "acquisition_latency_seconds": latency,
        "acquisition_only_seconds": seconds,
        "acquisition_only_human": _seconds_label(seconds),
    }
    if projected_host_seconds is not None:
        record["projected_host_seconds"] = projected_host_seconds
        record["acquisition_plus_projected_host_seconds"] = (
            seconds + projected_host_seconds
        )
    if interface_total_bytes is not None:
        record["interface_total_bytes"] = interface_total_bytes
        record["bandwidth_scenarios"] = [
            {
                "bandwidth_bytes_per_second": bandwidth,
                "interface_seconds": interface_total_bytes / bandwidth,
                "acquisition_interface_host_seconds": (
                    seconds
                    + interface_total_bytes / bandwidth
                    + (projected_host_seconds or 0.0)
                ),
            }
            for bandwidth in bandwidths_bytes_per_second
        ]
    return record


def build_architecture_projection(
    measured_results: str | Path,
    *,
    widths: Iterable[int],
    latencies_seconds: Iterable[float],
    confirmation_depth: int = 3,
    value_bits: int = 16,
    bandwidths_bytes_per_second: Iterable[float] = (1e9, 1e10, 1e11),
) -> dict[str, Any]:
    source, bundle, source_sha256 = _load_bundle(measured_results)
    widths = tuple(int(n) for n in widths)
    latencies = tuple(float(tau) for tau in latencies_seconds)
    bandwidths = tuple(float(value) for value in bandwidths_bytes_per_second)
    if not widths or any(n < 1 for n in widths):
        raise ValueError("projection widths must be positive")
    if not latencies or any(tau <= 0 for tau in latencies):
        raise ValueError("projection latencies must be positive")
    if confirmation_depth < 1:
        raise ValueError("confirmation_depth must be positive")
    if value_bits < 1:
        raise ValueError("value_bits must be positive")
    if not bandwidths or any(value <= 0 for value in bandwidths):
        raise ValueError("bandwidth scenarios must be positive")

    anchors = _qualifying_anchors(bundle["records"])
    rows: list[dict[str, Any]] = []
    for n in widths:
        methods: list[dict[str, Any]] = []
        for anchor in anchors:
            k = anchor["projection_anchor_acquisitions"]
            if k is None:
                continue
            bytes_per_acquisition = math.ceil(2 * n * value_bits / 8)
            interface_total_bytes = k * bytes_per_acquisition
            host_per_channel = anchor["largest_width_host_seconds_per_channel_p95"]
            projected_host_seconds = (
                host_per_channel * n if host_per_channel is not None else None
            )
            methods.append(
                {
                    "method": anchor["controller"],
                    "resource_class": "minimal-sufficient cold-start candidate",
                    "evidence_kind": "projection anchored to measured benchmark runs",
                    "sequential_acquisitions": k,
                    "host_arithmetic": "O(n)",
                    "host_state": "O(n) total; O(1) per channel",
                    "full_vector_values_per_acquisition": n,
                    "local_monitor_plus_actuation_bytes_per_cycle": math.ceil(
                        2 * n * value_bits / 8
                    ),
                    "projected_host_seconds": projected_host_seconds,
                    "host_projection_rule": (
                        "linear continuation of the 95th percentile measured total host "
                        "time per channel at the largest executed width; cache and bandwidth "
                        "regime changes can make this optimistic"
                    ),
                    "times": [
                        _time_record(
                            k,
                            tau,
                            projected_host_seconds=projected_host_seconds,
                            interface_total_bytes=interface_total_bytes,
                            bandwidths_bytes_per_second=bandwidths,
                        )
                        for tau in latencies
                    ],
                }
            )

        dense_acquisitions = n + 1 + confirmation_depth
        dense_interface_bytes = dense_acquisitions * math.ceil(2 * n * value_bits / 8)
        methods.append(
            {
                "method": "dense_finite_difference_best_case_verified",
                "resource_class": "out of class",
                "evidence_kind": "structural lower bound, not an executed large-width run",
                "sequential_acquisitions": dense_acquisitions,
                "commissioning_acquisitions": n + 1,
                "confirmation_acquisitions": confirmation_depth,
                "host_arithmetic": "at least O(n^2) to form a dense update; O(n^3) direct solve here",
                "host_state": "O(n^2)",
                "dense_float64_jacobian_bytes": 8 * n * n,
                "full_vector_values_per_acquisition": n,
                "times": [
                    _time_record(
                        dense_acquisitions,
                        tau,
                        interface_total_bytes=dense_interface_bytes,
                        bandwidths_bytes_per_second=bandwidths,
                    )
                    for tau in latencies
                ],
            }
        )
        sweep_acquisitions = math.ceil(n / 1024) + confirmation_depth
        sweep_interface_bytes = sweep_acquisitions * math.ceil(2 * n * value_bits / 8)
        methods.append(
            {
                "method": "scheduled_sweep_1024_channels_per_acquisition_best_case",
                "resource_class": "out of class when sweep width grows",
                "evidence_kind": "structural acquisition count, not an executed large-width run",
                "sequential_acquisitions": sweep_acquisitions,
                "sweep_acquisitions": math.ceil(n / 1024),
                "confirmation_acquisitions": confirmation_depth,
                "host_arithmetic": "O(n)",
                "host_state": "O(n)",
                "full_vector_values_per_acquisition": n,
                "times": [
                    _time_record(
                        sweep_acquisitions,
                        tau,
                        interface_total_bytes=sweep_interface_bytes,
                        bandwidths_bytes_per_second=bandwidths,
                    )
                    for tau in latencies
                ],
            }
        )
        rows.append({"width": n, "methods": methods})

    threshold_rows: list[dict[str, Any]] = []
    durations = {
        "10_days": 10 * 86400.0,
        "20_days": 20 * 86400.0,
        "10_years": 10 * 365.25 * 86400.0,
        "200_years": 200 * 365.25 * 86400.0,
    }
    for latency in latencies:
        for label, duration in durations.items():
            # n+1 commissioning plus confirmation_depth acquisitions.
            minimum_n = max(1, math.ceil(duration / latency - 1 - confirmation_depth))
            threshold_rows.append(
                {
                    "target_duration": label,
                    "target_seconds": duration,
                    "acquisition_latency_seconds": latency,
                    "minimum_width_for_dense_fd_best_case": minimum_n,
                    "scope": "hypothetical sensitivity; no device of this width is asserted",
                }
            )

    analysis_commit, analysis_dirty = _analysis_revision()
    return {
        "artifact": "QSC-Bench architecture projection",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_git_commit": analysis_commit,
        "analysis_git_worktree_dirty": analysis_dirty,
        "source_result_path": str(source),
        "source_result_sha256": source_sha256,
        "source_result_label": bundle.get("result_label"),
        "source_development_run": bundle.get("development_run"),
        "protocol_version": bundle.get("protocol_version"),
        "semantics": {
            "flat_quantity": "sequential acquisition depth under the stated no-growth hypothesis",
            "not_flat": [
                "full-vector data volume",
                "host arithmetic",
                "total controller state",
                "sensor and actuator count",
                "actuation energy",
                "simulator runtime",
            ],
            "time_formula": "T_acquisition_only = A_contract * tau",
            "total_time_warning": (
                "Acquisition-only time is not end-to-end wall time. Add readout, transport, "
                "host/local update, command distribution, and settling unless included in tau."
            ),
            "placement_warning": (
                "The 2n-value maintenance frame remains local only when the maintenance layer is "
                "placed beside the plant. If it crosses the workload host boundary, routing closure "
                "must be checked separately."
            ),
        },
        "measured_anchor_summary": anchors,
        "projection_anchor_policy": (
            "Structurally qualifying cold-start candidates are projected only when "
            "every source-bundle record succeeded. A controller with any observed "
            "timeout is not extrapolated, even if some of its runs succeeded."
        ),
        "projection_rows": rows,
        "resource_ceiling_rows": [
            {
                "width": n,
                "full_broyden_float64_state_bytes": 8 * (n * n + 3 * n),
                "full_broyden_direct_solve": "O(n^3)",
                "dense_fd_minimum_commissioning_acquisitions": n + 1,
                "dense_fd_minimum_response_values_returned": (n + 1) * n,
                "spsa_probe_acquisitions_per_update": 2,
                "spsa_warning": (
                    "constant probes per update do not imply constant time to contract; "
                    "the scalar estimator's width dependence is empirical"
                ),
            }
            for n in widths
        ],
        "interface_bandwidth_scenarios_bytes_per_second": list(bandwidths),
        "duration_sensitivity": threshold_rows,
    }


def write_architecture_projection(bundle: dict[str, Any], output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(destination)
    return destination
