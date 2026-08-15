#!/usr/bin/env python3
"""Collect a Quantum Inspire job into one machine-readable evidence file.

Run this script with the Python interpreter belonging to the authenticated
``quantuminspire`` CLI environment.  It records provider job metadata and
results but never reads or serializes authentication configuration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id", type=int)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from quantuminspire.api import Api

    api = Api()
    job = api.get_job(job_id=args.job_id)
    results = api.get_results(job_id=args.job_id)
    final_result = api.get_final_result(job_id=args.job_id)
    payload = {
        "capture_schema": "qsc-quantum-inspire-job-capture-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "job": job.model_dump(mode="json"),
        "results": [result.model_dump(mode="json") for result in results],
        "final_result": (
            None if final_result is None else final_result.model_dump(mode="json")
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)


if __name__ == "__main__":
    main()
