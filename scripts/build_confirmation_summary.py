#!/usr/bin/env python3
"""Build a compact, machine-readable summary from QSC-Bench artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _cell_table(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "width": row["width"],
            "controller": row["controller"],
            "runs": row["runs"],
            "successes": row["successes"],
            "failures": row["failures"],
            "success_rate": row["success_rate"],
            "acquisitions_to_contract": row["acquisitions_to_contract"],
        }
        for row in bundle["summary"]
    ]


def _git_revision() -> tuple[str | None, bool | None]:
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
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


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "scale",
        "scale_analysis",
        "aer",
        "strong",
        "strong_analysis",
        "validation",
        "million",
        "projection",
        "metriq",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    artifacts: dict[str, dict[str, Any]] = {}
    hashes: dict[str, dict[str, str]] = {}
    for name in (
        "scale",
        "scale_analysis",
        "aer",
        "strong",
        "strong_analysis",
        "validation",
        "million",
        "projection",
        "metriq",
    ):
        path = getattr(args, name)
        artifacts[name], digest = _read(path)
        hashes[name] = {"path": str(path), "sha256": digest}

    analysis = artifacts["scale_analysis"]
    strong_analysis = artifacts["strong_analysis"]
    validation = artifacts["validation"]
    projection = artifacts["projection"]
    revision, dirty = _git_revision()

    selected_projection: list[dict[str, Any]] = []
    for row in projection["projection_rows"]:
        if row["width"] not in (100_000_000, 10_000_000_000):
            continue
        for method in row["methods"]:
            if method["method"] not in {
                "retained_residual",
                "anderson_residual",
                "dense_finite_difference_best_case_verified",
            }:
                continue
            timing = next(
                item
                for item in method["times"]
                if item["acquisition_latency_seconds"] == 1e-4
            )
            selected_projection.append(
                {
                    "width": row["width"],
                    "method": method["method"],
                    "sequential_acquisitions": method["sequential_acquisitions"],
                    "timing_at_100us": timing,
                }
            )

    summary = {
        "artifact": "QSC-Bench v1.0 local-confirmation compact summary",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary_generator_git_commit": revision,
        "summary_generator_git_worktree_dirty": dirty,
        "decision": {
            "class_level_result": analysis["class_level_result"],
            "qualifying_controllers": analysis["qualifying_controllers"],
            "claim_scope": analysis["statistical_contract"]["claim_scope"],
        },
        "validation": {
            "status": validation["status"],
            "observed": validation["observed"],
            "thresholds": validation["thresholds"],
        },
        "primary_scaling": [
            {
                "controller": row["controller"],
                "supports_finite_range_claim": row[
                    "supports_bounded_depth_with_payload_over_tested_range"
                ],
                "scaling": row["scaling"],
                "predeclared_tests": row["predeclared_tests"],
                "resource_scaling": row["resource_scaling"],
            }
            for row in analysis["controllers"]
        ],
        "primary_cells": _cell_table(artifacts["scale"]),
        "aer_core_cells": _cell_table(artifacts["aer"]),
        "dense_baseline_cells": _cell_table(artifacts["strong"]),
        "dense_resource_scaling": [
            {
                "controller": row["controller"],
                "resource_scaling": row["resource_scaling"],
            }
            for row in strong_analysis["controllers"]
        ],
        "million_channel_extension_cells": _cell_table(artifacts["million"]),
        "metriq_adapter_smoke": artifacts["metriq"],
        "selected_projections": selected_projection,
        "input_artifacts": hashes,
        "limitations": [
            "The primary scale backend evaluates exact quantum-circuit marginals, not a globally entangled large-width state.",
            "Cross-channel finite-shot covariance is omitted in the scale backend and bounded only by the declared Aer overlap.",
            "The result is finite-range simulator evidence and does not prove asymptotic O(1) acquisition depth.",
            "Only sequential acquisition depth is bounded; traffic, local arithmetic, total state, sensors, actuators, and energy scale with width.",
            "No physical-QPU drift correction, native latency, fabricated maintenance hardware, or hosted-service equivalence is claimed.",
            "The million-channel run is a post-confirmation extension and is not part of the frozen statistical decision.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
