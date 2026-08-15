#!/usr/bin/env python3
"""Validate hardware export envelopes against the installed QSC Metriq result model."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from metriq_gym.benchmarks.qsc_bench import QSCColdStartResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("records", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = json.loads(args.records.read_text(encoding="utf-8"))
    if not isinstance(records, list) or len(records) != 15:
        raise ValueError("expected the complete 15-record hardware matrix")
    for envelope in records:
        if envelope.get("job_type") != "QSC-Bench Cold Start":
            raise ValueError("unexpected Metriq job type")
        payload = dict(envelope["results"])
        serialized_score = payload.pop("score")
        result = QSCColdStartResult.model_validate(payload)
        computed = result.score
        if computed is None or not math.isclose(
            computed.value, float(serialized_score["value"]), abs_tol=1e-15
        ):
            raise ValueError("serialized and computed Metriq scores disagree")
        if envelope["platform"]["device_metadata"].get("simulator") is not False:
            raise ValueError("hardware record is mislabeled as a simulator")
    print(f"METRIQ_HARDWARE_RECORDS_VALID records={len(records)}")


if __name__ == "__main__":
    main()
