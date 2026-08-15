#!/usr/bin/env python3
"""Validate and package the OpenQuantum static monitor cross-check."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any


ERRORS = (0.0, 0.0, 0.0, 0.0, 0.35, -0.35, 0.65, -0.65)
RMSE_LIMIT = 0.15
MINIMUM_CORRECT_DIRECTIONS = 3
EXPECTED_SOURCE_SHA256 = (
    "b8d33eb3e2f1e5122a730cda82793d456f4a188c3e588e089e36c800061a902b"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    if capture.get("capture_schema") != "qsc-openquantum-job-capture-v1":
        raise ValueError("unexpected OpenQuantum capture schema")
    if capture["job"]["status"] != "Completed":
        raise ValueError("OpenQuantum job did not complete")
    if capture.get("signed_content_urls_serialized") is not False:
        raise ValueError("capture does not attest that signed URLs were removed")
    if capture["source_sha256"] != EXPECTED_SOURCE_SHA256:
        raise ValueError("cross-check source hash changed after freeze")
    counts = capture.get("output")
    if not isinstance(counts, dict) or not counts:
        raise ValueError("OpenQuantum output is not a counts mapping")
    shots = sum(int(value) for value in counts.values())
    if shots != 1024:
        raise ValueError(f"expected 1024 shots, received {shots}")
    if any(len(bits) != 8 or set(bits) - {"0", "1"} for bits in counts):
        raise ValueError("OpenQuantum counts contain an invalid bitstring")

    # OpenQASM count keys are c[7]...c[0], so reverse before indexing q_i.
    observed = [
        sum(int(count) for bits, count in counts.items() if bits[::-1][qubit] == "1")
        / shots
        for qubit in range(8)
    ]
    ideal = [(1.0 + math.sin(error)) / 2.0 for error in ERRORS]
    residual = [value - target for value, target in zip(observed, ideal)]
    rmse = math.sqrt(sum(value * value for value in residual) / len(residual))
    directions = [
        (observed[index] - 0.5) * ERRORS[index] > 0.0 for index in range(4, 8)
    ]
    correct_directions = sum(directions)

    selected_plan = next(
        plan
        for plan in capture["preparation"]["quote"]
        if plan["execution_plan_id"] == capture["job"]["execution_plan_id"]
    )
    selected_priority = next(
        priority
        for priority in selected_plan["queue_priorities"]
        if priority["queue_priority_id"] == capture["job"]["queue_priority_id"]
    )
    cost = float(selected_plan["price"]) + float(selected_priority["price_increase"])
    if selected_plan["name"] != "Public Plan" or cost > 2:
        raise ValueError("job violated the frozen public-compute cost policy")
    if float(capture["credit_balance_after"]["full_credits"]) != 0.0:
        raise ValueError("paid Full Credits must remain zero")

    passed = rmse <= RMSE_LIMIT and correct_directions >= MINIMUM_CORRECT_DIRECTIONS
    summary = {
        "schema_version": "qsc-openquantum-static-crosscheck-v1",
        "decision": "PASS" if passed else "FAIL",
        "provider": "OpenQuantum public compute",
        "backend": "Rigetti Cepheus-1-108Q",
        "job_id": capture["job"]["id"],
        "shots": shots,
        "source_sha256": capture["source_sha256"],
        "phase_offsets_radians": list(ERRORS),
        "ideal_one_marginals": ideal,
        "observed_one_marginals": observed,
        "marginal_residuals": residual,
        "marginal_rmse": rmse,
        "rmse_limit": RMSE_LIMIT,
        "shifted_channel_direction_checks": directions,
        "correct_shift_directions": correct_directions,
        "minimum_correct_shift_directions": MINIMUM_CORRECT_DIRECTIONS,
        "execution_plan": selected_plan["name"],
        "queue_priority": selected_priority["name"],
        "spark_credit_cost": cost,
        "credit_balance_after": capture["credit_balance_after"],
        "evidence_scope": (
            "Single-acquisition cross-provider component-observability and circuit-"
            "portability check; not adaptive control, convergence, drift hold, or scale."
        ),
        "publication_state": "local only; owner review required",
        "required_attribution": "https://www.openquantum.com/citation",
    }

    output = args.output_directory
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.capture, raw / "openquantum_job_capture.json")
    shutil.copy2(
        "configs/hardware/openquantum_static_crosscheck_v1.qasm",
        raw / "openquantum_static_crosscheck_v1.qasm",
    )
    shutil.copy2(
        "protocols/QSC_BENCH_OPENQUANTUM_STATIC_CROSSCHECK_V1.md",
        raw / "QSC_BENCH_OPENQUANTUM_STATIC_CROSSCHECK_V1.md",
    )
    _write_json(output / "OPENQUANTUM_STATIC_CROSSCHECK_SUMMARY.json", summary)
    report = "\n".join(
        [
            "# OpenQuantum static cross-provider check",
            "",
            f"Decision: **{summary['decision']}**.",
            "",
            f"The eight-channel marginal RMSE was {rmse:.5f} against a frozen limit of {RMSE_LIMIT:.2f}. All {correct_directions}/4 shifted channels moved in the expected direction.",
            "",
            f"The completed 1,024-shot public job cost {cost:g} Spark credit. The post-job balance was {capture['credit_balance_after']['spark_credits']:g} Spark and {capture['credit_balance_after']['full_credits']:g} paid Full credits.",
            "",
            summary["evidence_scope"],
            "",
            "Any public use must follow OpenQuantum's attribution guidance: https://www.openquantum.com/citation",
            "",
            "Nothing in this package has been uploaded to Metriq, pushed to GitHub, or published.",
            "",
        ]
    )
    (output / "OPENQUANTUM_STATIC_CROSSCHECK_REPORT.md").write_text(
        report, encoding="utf-8"
    )
    manifest = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "ARTIFACT_MANIFEST_SHA256.txt":
            manifest.append(f"{_sha256(path)}  {path.relative_to(output)}")
    (output / "ARTIFACT_MANIFEST_SHA256.txt").write_text(
        "\n".join(manifest) + "\n", encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
