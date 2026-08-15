#!/usr/bin/env python3
"""Collect one OpenQuantum job without serializing credentials or signed URLs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


TERMINAL = {"Completed", "Failed", "Cancelled", "Canceled"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--sdk-key",
        type=Path,
        default=Path(
            os.environ.get(
                "OPENQUANTUM_SDK_KEY",
                str(Path.home() / ".config" / "openquantum" / "sdk-key.json"),
            )
        ),
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _public_job(job: Any) -> dict[str, Any]:
    """Remove presigned content URLs while retaining provider provenance."""

    return {
        "id": job.id,
        "status": str(job.status),
        "job_preparation_id": job.job_preparation_id,
        "execution_plan_id": job.execution_plan_id,
        "queue_priority_id": job.queue_priority_id,
        "message": job.message,
        "transaction_id": job.transaction_id,
        "submitted_at": job.submitted_at,
    }


def main() -> None:
    args = parse_args()
    from openquantum_sdk.auth import ClientCredentials, ClientCredentialsAuth
    from openquantum_sdk.clients import ManagementClient, SchedulerClient

    raw_credentials = json.loads(args.sdk_key.read_text(encoding="utf-8"))
    auth = ClientCredentialsAuth(
        creds=ClientCredentials(
            client_id=raw_credentials["client_id"],
            client_secret=raw_credentials["client_secret"],
        )
    )
    management = ManagementClient(auth=auth)
    scheduler = SchedulerClient(auth=auth)
    try:
        job = scheduler.get_job(args.job_id)
        if str(job.status) not in TERMINAL:
            raise RuntimeError(f"job is not terminal: {job.status}")
        preparation = scheduler.get_preparation_result(job.job_preparation_id)
        organizations = management.list_user_organizations(limit=20).organizations
        if len(organizations) != 1:
            raise RuntimeError("collector requires an unambiguous single organization")
        balance = management.get_credit_balance(str(organizations[0].id))
        output_payload = (
            scheduler.download_job_output(job) if str(job.status) == "Completed" else None
        )
        calibration_payload = None
        if str(job.status) == "Completed" and job.calibration_data_url:
            calibration_payload = scheduler.download_job_calibration(job)
        quote = []
        for plan in preparation.quote:
            quote.append(
                {
                    "name": plan.name,
                    "price": plan.price,
                    "execution_plan_id": plan.execution_plan_id,
                    "queue_priorities": [asdict(value) for value in plan.queue_priorities],
                }
            )
        payload = {
            "capture_schema": "qsc-openquantum-job-capture-v1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_path": str(args.source),
            "source_sha256": _sha256(args.source),
            "job": _public_job(job),
            "preparation": {
                "status": str(preparation.status),
                "name": preparation.name,
                "backend_class_id": preparation.backend_class_id,
                "shots": preparation.shots,
                "configuration_data": preparation.configuration_data,
                "input_format": preparation.input_format,
                "quote": quote,
            },
            "credit_balance_after": {
                "spark_credits": balance.spark_credits,
                "full_credits": balance.full_credits,
            },
            "output": output_payload,
            "calibration": calibration_payload,
            "signed_content_urls_serialized": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(args.output)
    finally:
        scheduler.close()
        management.close()


if __name__ == "__main__":
    main()
