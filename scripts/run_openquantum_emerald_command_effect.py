#!/usr/bin/env python3
"""Submit and capture the frozen one-credit IQM Emerald diagnostic."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


BACKEND = "iqm:emerald"
TERMINAL = {"Completed", "Failed", "Cancelled", "Canceled"}
CONFIG = Path("configs/hardware/openquantum_iqm_emerald_command_effect_v1.json")
OUTPUT = Path("checkpoints/openquantum_iqm_emerald_command_effect_v1.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def key_to_int(raw: str) -> int:
    key = str(raw).strip().replace(" ", "").replace("_", "")
    if key.startswith(("0x", "0X")):
        return int(key, 16)
    if key.startswith(("0b", "0B")):
        return int(key, 2)
    if key and set(key) <= {"0", "1"}:
        return int(key, 2)
    return int(key, 10)


def public_job(job: Any) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "status": str(job.status),
        "job_preparation_id": str(job.job_preparation_id),
        "execution_plan_id": str(job.execution_plan_id),
        "queue_priority_id": str(job.queue_priority_id),
        "message": job.message,
        "transaction_id": job.transaction_id,
        "submitted_at": job.submitted_at,
        "calibration_available": bool(job.calibration_data_url),
        "signed_content_urls_serialized": False,
    }


def main() -> None:
    from openquantum_sdk.auth import ClientCredentials, ClientCredentialsAuth
    from openquantum_sdk.clients import ManagementClient, SchedulerClient
    from openquantum_sdk.models import JobCreate, JobPreparationCreate

    root = Path.cwd().resolve()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    source_path = Path(config["source_path"])
    source = source_path.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if config["schema_version"] != "qsc-openquantum-iqm-emerald-command-effect-v1":
        raise RuntimeError("unexpected Emerald protocol schema")
    if config["backend_short_code"] != BACKEND or int(config["shots"]) != 512:
        raise RuntimeError("Emerald backend or shot count differs from the freeze")
    if subprocess.run(
        ("git", "status", "--porcelain"), check=True, text=True, capture_output=True
    ).stdout.strip():
        raise RuntimeError("Emerald diagnostic requires a clean frozen worktree")
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"), check=True, text=True, capture_output=True
    ).stdout.strip()

    key_path = Path(
        os.environ.get(
            "OPENQUANTUM_SDK_KEY",
            str(Path.home() / ".config" / "openquantum" / "sdk-key.json"),
        )
    )
    raw = json.loads(key_path.read_text(encoding="utf-8"))
    auth = ClientCredentialsAuth(
        creds=ClientCredentials(
            client_id=raw["client_id"], client_secret=raw["client_secret"]
        )
    )
    management = ManagementClient(auth=auth)
    scheduler = SchedulerClient(auth=auth)
    capture: dict[str, Any] = {
        "capture_schema": "qsc-openquantum-emerald-command-effect-capture-v1",
        "created_at": utc_now(),
        "protocol_commit": commit,
        "config_path": str(CONFIG),
        "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256(
            Path(config["protocol_path"]).read_bytes()
        ).hexdigest(),
        "source_path": str(source_path),
        "source_sha256": source_hash,
        "signed_content_urls_serialized": False,
    }
    try:
        organizations = management.list_user_organizations(limit=20).organizations
        if len(organizations) != 1:
            raise RuntimeError("Emerald diagnostic requires one organization")
        organization_id = str(organizations[0].id)
        balance = management.get_credit_balance(organization_id)
        capture["credit_balance_before"] = {
            "spark_credits": float(balance.spark_credits),
            "full_credits": float(balance.full_credits),
        }
        if float(balance.full_credits) != 0.0:
            raise RuntimeError("paid Full credits are not authorized")
        if float(balance.spark_credits) < float(config["minimum_balance_before_submission"]):
            raise RuntimeError("insufficient Spark balance while preserving Cepheus credit")
        matches = [
            backend
            for backend in management.list_backend_classes(limit=100).backend_classes
            if backend.short_code == BACKEND
        ]
        if len(matches) != 1:
            raise RuntimeError("Emerald backend is absent or ambiguous")
        backend = matches[0]
        if str(backend.status) != "Online" or not bool(backend.accepting_jobs):
            raise RuntimeError("Emerald is not online and accepting jobs")
        details = scheduler.get_backend_class(BACKEND)["constraint_data"]
        if int(details["limits"]["max_qubits_per_job"]) != 54:
            raise RuntimeError("Emerald qubit limit differs from the freeze")
        capture["backend_audit"] = {
            "captured_at": utc_now(),
            "id": str(backend.id),
            "name": backend.name,
            "short_code": backend.short_code,
            "status": str(backend.status),
            "accepting_jobs": bool(backend.accepting_jobs),
            "queue_depth": int(backend.queue_depth),
            "n_qubits": int(details["n_qubits"]),
            "native_ops": details["native_ops"],
        }
        upload_id = scheduler.upload_job_input(file_content=source.encode("utf-8"))
        preparation = scheduler.prepare_job(
            JobPreparationCreate(
                organization_id=organization_id,
                backend_class_id=str(backend.id),
                name=f"QSC Emerald command-effect {source_hash[:8]}",
                upload_endpoint_id=upload_id,
                job_subcategory_id="oth:oth",
                shots=512,
                configuration_data={"shots": 512},
                submitted_with="sdk",
                input_format="qasm",
            )
        )
        for _ in range(300):
            prepared = scheduler.get_preparation_result(str(preparation.id))
            if str(prepared.status) in {"Completed", "Failed"}:
                break
            time.sleep(1)
        if str(prepared.status) != "Completed":
            raise RuntimeError(f"Emerald preparation failed: {prepared.message}")
        public = [plan for plan in prepared.quote if str(plan.name) == "Public Plan"]
        if len(public) != 1:
            raise RuntimeError("one Public Plan quote was not returned")
        standard = [
            priority
            for priority in public[0].queue_priorities
            if str(priority.name) == "Standard Queue"
        ]
        if len(standard) != 1:
            raise RuntimeError("one Standard Queue quote was not returned")
        quote_total = int(public[0].price) + int(standard[0].price_increase)
        if quote_total != int(config["maximum_quote_spark_credits"]):
            raise RuntimeError("Emerald quote differs from the frozen one-credit cap")
        capture["preparation"] = {
            "id": str(preparation.id),
            "status": str(prepared.status),
            "shots": int(prepared.shots),
            "quote": [
                {
                    "name": plan.name,
                    "price": int(plan.price),
                    "execution_plan_id": plan.execution_plan_id,
                    "queue_priorities": [asdict(value) for value in plan.queue_priorities],
                }
                for plan in prepared.quote
            ],
            "selected_plan": "Public Plan",
            "selected_priority": "Standard Queue",
            "selected_total_spark_credits": quote_total,
        }
        job = scheduler.create_job(
            JobCreate(
                job_preparation_id=str(preparation.id),
                execution_plan_id=str(public[0].execution_plan_id),
                queue_priority_id=str(standard[0].queue_priority_id),
                organization_id=organization_id,
            )
        )
        capture["job"] = public_job(job)
        capture["status_observations"] = [{"at": utc_now(), "status": str(job.status)}]
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        last = str(job.status)
        last_heartbeat = 0.0
        while str(job.status) not in TERMINAL:
            time.sleep(10)
            job = scheduler.get_job(str(job.id))
            if str(job.status) != last:
                capture["status_observations"].append(
                    {"at": utc_now(), "status": str(job.status)}
                )
                capture["job"] = public_job(job)
                OUTPUT.write_text(
                    json.dumps(capture, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                print(f"QSC_EMERALD_STATUS job={job.id} status={job.status}", flush=True)
                last = str(job.status)
            if time.monotonic() - last_heartbeat >= 60:
                print(f"QSC_EMERALD_HEARTBEAT job={job.id} status={job.status}", flush=True)
                last_heartbeat = time.monotonic()
        capture["terminal_observed_at"] = utc_now()
        capture["job"] = public_job(job)
        if str(job.status) == "Completed":
            counts = scheduler.download_job_output(job)
            total = sum(int(value) for value in counts.values())
            if total != 512:
                raise RuntimeError("Emerald returned an incomplete shot count")
            zero = []
            for qubit in range(54):
                ones = sum(
                    int(count) * ((key_to_int(key) >> qubit) & 1)
                    for key, count in counts.items()
                )
                zero.append(1.0 - ones / total)
            unmaintained = sum(zero[0::2]) / 27.0
            corrected = sum(zero[1::2]) / 27.0
            delta = corrected - unmaintained
            rule = config["decision_rule"]
            capture["output"] = {str(key): int(value) for key, value in counts.items()}
            capture["result"] = {
                "shots_done": total,
                "unmaintained_bitwise_zero": unmaintained,
                "corrected_bitwise_zero": corrected,
                "corrected_minus_unmaintained": delta,
                "per_pair_unmaintained_zero": zero[0::2],
                "per_pair_corrected_zero": zero[1::2],
                "decision": (
                    "PASS"
                    if corrected >= float(rule["minimum_corrected_bitwise_zero"])
                    and delta >= float(rule["minimum_corrected_minus_unmaintained"])
                    else "FAIL"
                ),
                "claim_boundary": config["claim_boundary"],
            }
        balance_after = management.get_credit_balance(organization_id)
        capture["credit_balance_after"] = {
            "spark_credits": float(balance_after.spark_credits),
            "full_credits": float(balance_after.full_credits),
        }
        if float(balance_after.spark_credits) < float(
            config["minimum_balance_after_submission"]
        ):
            raise RuntimeError("Emerald execution did not preserve the Cepheus credit")
        capture["completed_at"] = utc_now()
        OUTPUT.write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"QSC_EMERALD_COMPLETE status={job.status} "
            f"decision={capture.get('result', {}).get('decision')} "
            f"spark_remaining={balance_after.spark_credits}",
            flush=True,
        )
    finally:
        scheduler.close()
        management.close()


if __name__ == "__main__":
    main()
