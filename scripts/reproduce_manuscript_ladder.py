#!/usr/bin/env python3
"""Re-run the recovered manuscript ladder without rewriting its source.

The recovered runner uses the originally registered eight-neighbour, c=0.30
plant.  This differs from the current supplement's radius-one, c=0.20 prose and
is therefore reported as an executed-protocol reproduction, not as validation
of the mismatched prose description.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = PROJECT_ROOT / "evidence" / "manuscript_scale_ladder_original"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_original(width: int, seed: int, arm: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "ladder.py", str(width), str(seed), arm],
        cwd=EVIDENCE,
        text=True,
        capture_output=True,
        check=True,
    )
    record = json.loads(completed.stdout)
    record["usable_acquisition_one_based"] = (
        int(record["usable_at"]) + 1 if record["usable_at"] is not None else None
    )
    record["legacy_usable_index_zero_based"] = record.pop("usable_at")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--widths", type=int, nargs="+", default=[100_000])
    parser.add_argument("--seeds", type=int, nargs="+", default=[31, 32, 33])
    parser.add_argument("--arms", nargs="+", default=["ref", "broyden", "nothing"])
    args = parser.parse_args()
    if any(width < 1 or width > 10_000_000 for width in args.widths):
        raise ValueError("this wrapper permits recovered in-memory runner widths 1..10,000,000")

    preregistration_hash = sha256(EVIDENCE / "PREREG_SCALE_LADDER.md")
    expected_preregistration_hash = "f128dae481b8bd0951117fd6179f666c8088dd6d2f6dd68925039d16aa6778d5"
    if preregistration_hash != expected_preregistration_hash:
        raise RuntimeError("recovered preregistration hash does not match the provenance anchor")

    records = [
        run_original(width, seed, arm)
        for width in args.widths
        for seed in args.seeds
        for arm in args.arms
    ]
    expected = json.loads((EVIDENCE / "ladder_results.json").read_text(encoding="utf-8"))
    comparisons = []
    for width in args.widths:
        expected_width = expected.get(str(width))
        if expected_width is None:
            comparisons.append(
                {"width": width, "status": "NO_RECOVERED_AGGREGATE_FOR_WIDTH"}
            )
            continue
        arm_rows = []
        for arm in args.arms:
            group = [r for r in records if r["n"] == width and r["arm"] == arm]
            mean_floor = sum(float(r["floor"]) for r in group) / len(group)
            observed_usable = sorted(
                {r["legacy_usable_index_zero_based"] for r in group},
                key=lambda value: -1 if value is None else value,
            )
            expected_row = expected_width[arm]
            floor_match = round(mean_floor, 4) == round(float(expected_row["floor"]), 4)
            usable_match = observed_usable == [expected_row["usable_at"]]
            arm_rows.append(
                {
                    "arm": arm,
                    "fresh_mean_floor": mean_floor,
                    "recovered_aggregate_floor": expected_row["floor"],
                    "floor_matches_to_four_decimals": floor_match,
                    "fresh_legacy_zero_based_usable_indices": observed_usable,
                    "fresh_one_based_usable_acquisitions": [
                        value + 1 for value in observed_usable if value is not None
                    ],
                    "recovered_legacy_zero_based_usable_index": expected_row["usable_at"],
                    "usable_index_matches": usable_match,
                    "passed": floor_match and usable_match,
                }
            )
        comparisons.append(
            {
                "width": width,
                "status": "PASS" if all(row["passed"] for row in arm_rows) else "FAIL",
                "arms": arm_rows,
            }
        )

    result = {
        "artifact": "Fresh reproduction of recovered manuscript scale-ladder runner",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_run": True,
        "source_class": "byte-preserved recovered original runner",
        "source_hashes": {
            path.name: sha256(path)
            for path in sorted(EVIDENCE.iterdir())
            if path.is_file()
        },
        "preregistration_sha256": preregistration_hash,
        "executed_protocol": {
            "coupling_topology": "eight-neighbour circular mean (+/-1..4)",
            "coupling_strength": 0.30,
            "drift_per_acquisition": 0.05,
            "cycles": 24,
            "read_noise_standard_deviation": 0.003,
        },
        "known_manuscript_mismatch": (
            "The current TC_SUBMIT supplement says radius-one coupling at c=0.20. "
            "The registered and recovered executed ladder uses eight neighbours at c=0.30."
        ),
        "records": records,
        "comparisons": comparisons,
        "passed": all(row.get("status") == "PASS" for row in comparisons),
        "claim_boundary": (
            "This is a controlled classical plant-model reproduction. It is not a quantum "
            "simulation, physical-device result, or proof of constant end-to-end wall time."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"passed": result["passed"], "comparisons": comparisons}, indent=2))
    print(f"JSON: {args.output}")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
