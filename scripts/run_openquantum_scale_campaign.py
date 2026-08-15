#!/usr/bin/env python3
"""Run the frozen QSC-Bench Cepheus scale campaign with hard spend guards.

The runner uses low-level OpenQuantum preparation and creation calls so every
quote is inspected before a job is created.  It is resumable and never blindly
repeats a create call after an ambiguous network failure.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping

import numpy as np

from qsc_bench.openquantum_scale import (
    CEPHEUS_BACKEND,
    OpenQuantumAdaptiveRun,
    cepheus_protocol,
    reference_payload_threshold,
    render_openquantum_reference_qasm,
    score_openquantum_counts,
)


TERMINAL = {"Completed", "Failed", "Cancelled", "Canceled"}
TRANSIENT_FAILURE_WORDS = (
    "infrastructure",
    "internal",
    "temporar",
    "timeout",
    "unavailable",
    "service",
)
ALLOWED_POST_FREEZE_ORCHESTRATION_PATHS = {
    "configs/hardware/openquantum_iqm_emerald_command_effect_v1.json",
    "configs/hardware/openquantum_iqm_emerald_command_effect_v1.qasm",
    "protocols/QSC_BENCH_OPENQUANTUM_IQM_EMERALD_COMMAND_EFFECT_V1.md",
    "scripts/run_openquantum_emerald_command_effect.py",
    "scripts/run_openquantum_scale_campaign.py",
    "scripts/run_openquantum_fallback_campaign.py",
    "scripts/run_openquantum_local_payload_campaign.py",
    "scripts/run_openquantum_native_mirror_campaign.py",
    "scripts/run_openquantum_single_rx_campaign.py",
    "tests/test_openquantum_scale.py",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/hardware/openquantum_cepheus_scale_v1.json"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("checkpoints/openquantum_cepheus_scale_v1"),
    )
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
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--preparation-timeout-seconds", type=float, default=300.0)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_value(*args: str) -> str:
    return subprocess.run(
        ("git", *args), check=True, text=True, capture_output=True
    ).stdout.strip()


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


def public_quote(result: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": plan.name,
            "price": int(plan.price),
            "execution_plan_id": plan.execution_plan_id,
            "queue_priorities": [asdict(priority) for priority in plan.queue_priorities],
        }
        for plan in result.quote
    ]


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_verified_transient_execution_failure(attempt: Mapping[str, Any]) -> bool:
    """Classify retryable provider execution failures without hiding compile errors."""

    if attempt.get("preparation", {}).get("status") != "Completed":
        return False
    job = attempt.get("job", {})
    if job.get("status") != "Failed" or "output" in attempt:
        return False
    message = str(job.get("message") or "").lower()
    return (
        any(word in message for word in TRANSIENT_FAILURE_WORDS)
        or (message.startswith("execution failed after ") and message.endswith(" attempts"))
    )


class Campaign:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        if not 1.0 <= args.poll_seconds <= 60.0:
            raise ValueError("poll interval must be in [1, 60] seconds")
        self.root = Path.cwd().resolve()
        self.config_path = args.config.resolve()
        self.workspace = args.workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.sources = self.workspace / "sources"
        self.sources.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.workspace / "CAMPAIGN_CHECKPOINT.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self._validate_static_config()

        from openquantum_sdk.auth import ClientCredentials, ClientCredentialsAuth
        from openquantum_sdk.clients import ManagementClient, SchedulerClient

        raw_credentials = json.loads(args.sdk_key.read_text(encoding="utf-8"))
        auth = ClientCredentialsAuth(
            creds=ClientCredentials(
                client_id=raw_credentials["client_id"],
                client_secret=raw_credentials["client_secret"],
            )
        )
        self.management = ManagementClient(auth=auth)
        self.scheduler = SchedulerClient(auth=auth)
        organizations = self.management.list_user_organizations(limit=20).organizations
        if len(organizations) != 1:
            raise RuntimeError("campaign requires one unambiguous OpenQuantum organization")
        self.organization_id = str(organizations[0].id)
        self.protocols = self._build_protocols()
        self.run_specs = self._build_run_specs()
        self.state = self._load_or_initialize_state()

    def _build_protocols(self) -> dict[int, Any]:
        return {width: cepheus_protocol(width) for width in (18, 54)}

    def _build_run_specs(self) -> list[dict[str, Any]]:
        return [
            {"width": 18, "arm": "retained_residual", "seed": 1784722507},
            {"width": 54, "arm": "retained_residual", "seed": 169583711},
            {"width": 54, "arm": "diagonal_secant", "seed": 169583711},
            {"width": 54, "arm": "commissioned_pi", "seed": 169583711},
            {"width": 54, "arm": "do_nothing", "seed": 169583711},
        ]

    def close(self) -> None:
        self.scheduler.close()
        self.management.close()

    def _validate_static_config(self) -> None:
        if self.config.get("schema_version") != "qsc-openquantum-cepheus-scale-protocol-v1":
            raise ValueError("unexpected scale-protocol schema")
        if self.config.get("backend_short_code") != CEPHEUS_BACKEND:
            raise ValueError("config selects an unexpected backend")
        if int(self.config.get("planned_main_spark_credits", -1)) != 22:
            raise ValueError("frozen main budget must be 22 Spark credits")
        if int(self.config.get("reserved_spark_credits", -1)) != 1:
            raise ValueError("frozen reserve must be one Spark credit")
        if int(self.config.get("paid_full_credits_authorized", -1)) != 0:
            raise ValueError("paid Full credits are not authorized")
        if self.config.get("width_seeds") != {"18": 1784722507, "54": 169583711}:
            raise ValueError("confirmation seeds differ from the frozen derivation")
        expected_tracks = [
            {
                "width": 18,
                "physical_qubits": 36,
                "arms": ["retained_residual"],
            },
            {
                "width": 54,
                "physical_qubits": 108,
                "arms": [
                    "retained_residual",
                    "diagonal_secant",
                    "commissioned_pi",
                    "do_nothing",
                ],
            },
        ]
        if self.config.get("tracks") != expected_tracks:
            raise ValueError("track matrix differs from the frozen campaign")
        for key, expected in (
            ("shots_per_reference", 2048),
            ("shots_per_acquisition", 2048),
            ("acquisition_deadline", 4),
            ("required_consecutive_ordinary_acquisitions", 2),
        ):
            if int(self.config.get(key, -1)) != expected:
                raise ValueError(f"{key} differs from the executable protocol")
        for key, expected in (
            ("monitor_rmse_tolerance", 0.08),
            ("payload_bitwise_zero_absolute_floor", 0.70),
            ("payload_reference_margin", 0.10),
            ("initial_commanded_shock_rms_radians", 0.45),
            ("identification_amplitude_radians", 0.15),
        ):
            if not np.isclose(float(self.config.get(key, float("nan"))), expected):
                raise ValueError(f"{key} differs from the executable protocol")

    def _load_or_initialize_state(self) -> dict[str, Any]:
        config_hash = sha256_file(self.config_path)
        protocol_path = self.root / self.config.get(
            "protocol_path",
            "protocols/QSC_BENCH_OPENQUANTUM_CEPHEUS_SCALE_V1.md",
        )
        protocol_hash = sha256_file(protocol_path)
        commit = git_value("rev-parse", "HEAD")
        dirty = bool(git_value("status", "--porcelain"))
        if dirty:
            raise RuntimeError("hardware confirmation requires a clean, frozen git worktree")
        if self.checkpoint_path.exists():
            state = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            if state.get("config_sha256") != config_hash:
                raise RuntimeError("resume config hash mismatch")
            if state.get("protocol_sha256") != protocol_hash:
                raise RuntimeError("resume protocol hash mismatch")
            if state.get("protocol_commit") != commit:
                changed = set(
                    git_value(
                        "diff",
                        "--name-only",
                        f"{state['protocol_commit']}..{commit}",
                    ).splitlines()
                )
                disallowed = changed - ALLOWED_POST_FREEZE_ORCHESTRATION_PATHS
                if disallowed:
                    raise RuntimeError(
                        "resume commit changes scientific or non-orchestration paths: "
                        f"{sorted(disallowed)}"
                    )
                resumes = state.setdefault("orchestration_resume_commits", [])
                if not any(row.get("commit") == commit for row in resumes):
                    resumes.append(
                        {
                            "at": utc_now(),
                            "commit": commit,
                            "changed_paths_from_protocol_freeze": sorted(changed),
                            "reason": (
                                "post-freeze orchestration-only change; scientific config, "
                                "seed, controller, plant, thresholds, and protocol hash unchanged"
                            ),
                        }
                    )
                    self._save_state(state)
            return state
        balance = self._balance()
        if float(balance["full_credits"]) != 0.0:
            raise RuntimeError("Full paid-credit balance must remain zero for this campaign")
        required = int(self.config["planned_main_spark_credits"]) + int(
            self.config["reserved_spark_credits"]
        )
        if float(balance["spark_credits"]) < required:
            raise RuntimeError(f"campaign requires {required} Spark credits before launch")
        backend_audit = self._backend_audit()
        state = {
            "capture_schema": "qsc-openquantum-cepheus-scale-checkpoint-v1",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "config_path": str(self.config_path.relative_to(self.root)),
            "config_sha256": config_hash,
            "protocol_sha256": protocol_hash,
            "protocol_commit": commit,
            "git_worktree_clean_at_freeze": True,
            "backend_audit": backend_audit,
            "credit_balance_initial": balance,
            "main_logical_jobs_submitted": 0,
            "reserve_used": False,
            "reserve_purpose": None,
            "logical_jobs": {},
            "references": {},
            "run_results": {},
            "events": [],
            "complete": False,
            "signed_content_urls_serialized": False,
        }
        self._save_state(state)
        return state

    def _save_state(self, state: dict[str, Any] | None = None) -> None:
        if state is not None:
            self.state = state
        self.state["updated_at"] = utc_now()
        temporary = self.checkpoint_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.state, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.checkpoint_path)

    def _event(self, kind: str, **fields: Any) -> None:
        self.state["events"].append({"at": utc_now(), "kind": kind, **fields})
        self._save_state()

    def _balance(self) -> dict[str, float]:
        balance = self.management.get_credit_balance(self.organization_id)
        return {
            "spark_credits": float(balance.spark_credits),
            "full_credits": float(balance.full_credits),
        }

    def _backend_audit(self) -> dict[str, Any]:
        listing = self.management.list_backend_classes(limit=100).backend_classes
        matches = [backend for backend in listing if backend.short_code == CEPHEUS_BACKEND]
        if len(matches) != 1:
            raise RuntimeError("Cepheus backend is absent or ambiguous")
        listed = matches[0]
        details = self.scheduler.get_backend_class(CEPHEUS_BACKEND)
        constraints = details["constraint_data"]
        if str(listed.status) != "Online" or not bool(listed.accepting_jobs):
            raise RuntimeError("Cepheus is not online and accepting jobs")
        if int(constraints["limits"]["max_qubits_per_job"]) != 108:
            raise RuntimeError("live backend no longer exposes the frozen 108-qubit limit")
        live_edges = {
            tuple(sorted((int(left), int(right))))
            for left, right in constraints["topology"]["coupling_map"]
        }
        for width, protocol in self.protocols.items():
            missing = [
                edge
                for edge in protocol.payload_edges
                if tuple(sorted(edge)) not in live_edges
            ]
            if missing:
                raise RuntimeError(
                    f"width-{width} frozen payload matching is absent from live topology: {missing}"
                )
        return {
            "captured_at": utc_now(),
            "id": str(listed.id),
            "short_code": listed.short_code,
            "name": listed.name,
            "status": str(listed.status),
            "accepting_jobs": bool(listed.accepting_jobs),
            "queue_depth": int(listed.queue_depth),
            "n_qubits": int(constraints["n_qubits"]),
            "max_shots": int(constraints["limits"]["max_shots"]),
            "native_ops": constraints["native_ops"],
            "frozen_payload_edges_verified": {
                str(width): len(protocol.payload_edges)
                for width, protocol in self.protocols.items()
            },
            "constraint_data_sha256": sha256_bytes(
                json.dumps(constraints, sort_keys=True).encode("utf-8")
            ),
        }

    def _safe_source(self, logical_id: str, qasm: str) -> tuple[Path, str]:
        digest = sha256_bytes(qasm.encode("utf-8"))
        path = self.sources / f"{logical_id}_{digest[:12]}.qasm"
        if path.exists() and path.read_text(encoding="utf-8") != qasm:
            raise RuntimeError("existing QASM artifact does not match its logical source")
        if not path.exists():
            path.write_text(qasm, encoding="utf-8")
        return path, digest

    def _poll_preparation(self, preparation_id: str) -> Any:
        deadline = time.monotonic() + self.args.preparation_timeout_seconds
        while True:
            result = self.scheduler.get_preparation_result(preparation_id)
            if str(result.status) in {"Completed", "Failed"}:
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError(f"preparation {preparation_id} did not finish")
            time.sleep(1.0)

    @staticmethod
    def _select_public_standard(result: Any) -> tuple[Any, Any, int]:
        public = [plan for plan in result.quote if str(plan.name) == "Public Plan"]
        if len(public) != 1:
            raise RuntimeError("quote does not contain one unambiguous Public Plan")
        standard = [
            priority
            for priority in public[0].queue_priorities
            if str(priority.name) == "Standard Queue"
        ]
        if len(standard) != 1:
            raise RuntimeError("quote does not contain one unambiguous Standard Queue")
        total = int(public[0].price) + int(standard[0].price_increase)
        return public[0], standard[0], total

    def _reconcile_creation(self, name: str, preparation_id: str) -> Any | None:
        for _ in range(6):
            page = self.scheduler.list_jobs(
                organization_id=self.organization_id, limit=100
            )
            matching = [job for job in page.jobs if str(job.name) == name]
            verified = []
            for candidate in matching:
                job = self.scheduler.get_job(str(candidate.id))
                if str(job.job_preparation_id) == preparation_id:
                    verified.append(job)
            if len(verified) == 1:
                return verified[0]
            if len(verified) > 1:
                raise RuntimeError("ambiguous duplicate jobs found during reconciliation")
            time.sleep(5.0)
        return None

    def _submit_attempt(
        self,
        logical_id: str,
        *,
        qasm: str,
        shots: int,
        width: int,
        arm: str | None,
        acquisition: int | None,
        stage: str,
        main_logical_job: bool,
        reserve_purpose: str | None = None,
    ) -> None:
        from openquantum_sdk.models import JobCreate, JobPreparationCreate

        record = self.state["logical_jobs"].setdefault(
            logical_id,
            {
                "logical_id": logical_id,
                "stage": stage,
                "width": width,
                "arm": arm,
                "acquisition": acquisition,
                "shots": int(shots),
                "attempts": [],
            },
        )
        if any(attempt.get("job", {}).get("status") == "Completed" for attempt in record["attempts"]):
            return
        active = [
            attempt
            for attempt in record["attempts"]
            if attempt.get("job") and attempt["job"].get("status") not in TERMINAL
        ]
        if active:
            return
        if record["attempts"] and reserve_purpose is None:
            raise RuntimeError("a failed logical job cannot be repeated outside the reserve rule")

        source_path, source_hash = self._safe_source(logical_id, qasm)
        if record.get("qasm_sha256") not in (None, source_hash):
            raise RuntimeError("adaptive QASM changed across an attempted replacement")
        record["qasm_path"] = str(source_path.relative_to(self.root))
        record["qasm_sha256"] = source_hash
        attempt_index = len(record["attempts"]) + 1
        name = f"QSCv1 {logical_id} a{attempt_index} {source_hash[:8]}"
        upload_id = self.scheduler.upload_job_input(file_content=qasm.encode("utf-8"))
        preparation = self.scheduler.prepare_job(
            JobPreparationCreate(
                organization_id=self.organization_id,
                backend_class_id=CEPHEUS_BACKEND,
                name=name,
                upload_endpoint_id=upload_id,
                job_subcategory_id="oth:oth",
                shots=int(shots),
                configuration_data={"shots": int(shots)},
                submitted_with="sdk",
                input_format="qasm",
            )
        )
        result = self._poll_preparation(str(preparation.id))
        if str(result.status) != "Completed":
            raise RuntimeError(f"job preparation failed: {result.message}")
        plan, priority, quote_total = self._select_public_standard(result)
        maximum = int(self.config["maximum_quote_per_job_spark_credits"])
        if quote_total > maximum:
            raise RuntimeError(f"quote {quote_total} exceeds frozen {maximum}-credit cap")
        balance_before = self._balance()
        if balance_before["full_credits"] != 0.0:
            raise RuntimeError("paid Full-credit balance is nonzero; submission stopped")
        if main_logical_job:
            submitted = int(self.state["main_logical_jobs_submitted"])
            effective_plan = int(
                self.state.get(
                    "effective_planned_main_spark_credits",
                    self.config["planned_main_spark_credits"],
                )
            )
            frozen_plan = int(self.config["planned_main_spark_credits"])
            if effective_plan > frozen_plan:
                raise RuntimeError("effective main-job budget exceeds the frozen plan")
            remaining_including_this = effective_plan - submitted
            if remaining_including_this <= 0:
                raise RuntimeError("effective main-job budget is already exhausted")
            reserve_total = int(self.config["reserved_spark_credits"])
            reserve_remaining = 0 if self.state["reserve_used"] else reserve_total
            if balance_before["spark_credits"] < remaining_including_this + reserve_remaining:
                raise RuntimeError("Spark balance cannot cover remaining main jobs plus reserve")
        else:
            reserve_total = int(self.config["reserved_spark_credits"])
            if (
                reserve_purpose is None
                or self.state["reserve_used"]
                or reserve_total < quote_total
            ):
                raise RuntimeError("reserve job is unauthorized or the reserve is already used")
            if balance_before["spark_credits"] < quote_total:
                raise RuntimeError("Spark balance cannot cover the reserve job")

        attempt = {
            "attempt": attempt_index,
            "name": name,
            "prepared_at": utc_now(),
            "preparation": {
                "id": str(preparation.id),
                "status": str(result.status),
                "backend_class_id": str(result.backend_class_id),
                "shots": result.shots,
                "configuration_data": result.configuration_data,
                "input_format": result.input_format,
                "quote": public_quote(result),
            },
            "selected_quote": {
                "plan": plan.name,
                "plan_price": int(plan.price),
                "priority": priority.name,
                "priority_price_increase": int(priority.price_increase),
                "total_spark_credits": quote_total,
            },
            "credit_balance_before": balance_before,
            "creation_intent_at": utc_now(),
            "status_observations": [],
        }
        record["attempts"].append(attempt)
        self._save_state()
        try:
            job = self.scheduler.create_job(
                JobCreate(
                    job_preparation_id=str(preparation.id),
                    execution_plan_id=str(plan.execution_plan_id),
                    queue_priority_id=str(priority.queue_priority_id),
                    organization_id=self.organization_id,
                )
            )
        except Exception:
            job = self._reconcile_creation(name, str(preparation.id))
            if job is None:
                self._event(
                    "ambiguous_create_stopped",
                    logical_id=logical_id,
                    preparation_id=str(preparation.id),
                )
                raise RuntimeError(
                    "job creation response was ambiguous and no unique server job could be "
                    "reconciled; stopped without blind retry"
                )
            attempt["creation_reconciled_after_exception"] = True
        attempt["job"] = public_job(job)
        attempt["status_observations"].append(
            {"at": utc_now(), "status": str(job.status)}
        )
        attempt["credit_balance_after_creation"] = self._balance()
        if main_logical_job:
            self.state["main_logical_jobs_submitted"] = (
                int(self.state["main_logical_jobs_submitted"]) + quote_total
            )
        else:
            self.state["reserve_used"] = True
            self.state["reserve_purpose"] = reserve_purpose
        self._event(
            "job_submitted",
            logical_id=logical_id,
            job_id=str(job.id),
            quote_spark_credits=quote_total,
            stage=stage,
        )
        print(
            f"QSC_OPENQ_SUBMITTED logical={logical_id} job={job.id} "
            f"quote={quote_total} status={job.status}",
            flush=True,
        )

    def _latest_attempt(self, logical_id: str) -> dict[str, Any]:
        attempts = self.state["logical_jobs"][logical_id]["attempts"]
        if not attempts:
            raise RuntimeError("logical job has no submitted attempt")
        return attempts[-1]

    def _poll_logical_batch(self, logical_ids: list[str]) -> None:
        last_heartbeat = 0.0
        while True:
            active = 0
            statuses: dict[str, str] = {}
            for logical_id in logical_ids:
                attempt = self._latest_attempt(logical_id)
                job_data = attempt.get("job")
                if not job_data:
                    raise RuntimeError("submitted attempt is missing its job record")
                if job_data["status"] in TERMINAL and "terminal_observed_at" in attempt:
                    statuses[logical_id] = job_data["status"]
                    continue
                job = self.scheduler.get_job(str(job_data["id"]))
                status = str(job.status)
                statuses[logical_id] = status
                previous = str(job_data["status"])
                if status != previous:
                    attempt["status_observations"].append({"at": utc_now(), "status": status})
                    attempt["job"] = public_job(job)
                    self._save_state()
                    print(
                        f"QSC_OPENQ_STATUS logical={logical_id} job={job.id} status={status}",
                        flush=True,
                    )
                if status not in TERMINAL:
                    active += 1
                    continue
                if "terminal_observed_at" not in attempt:
                    attempt["job"] = public_job(job)
                    attempt["terminal_observed_at"] = utc_now()
                    submitted = job.submitted_at
                    if submitted:
                        attempt["submitted_to_terminal_observation_seconds"] = (
                            parse_iso(attempt["terminal_observed_at"]) - parse_iso(submitted)
                        ).total_seconds()
                    if status == "Completed":
                        output = self.scheduler.download_job_output(job)
                        if not isinstance(output, dict) or not output:
                            raise RuntimeError("completed OpenQuantum job has no counts mapping")
                        shots_done = sum(int(value) for value in output.values())
                        if shots_done != int(self.state["logical_jobs"][logical_id]["shots"]):
                            raise RuntimeError("completed OpenQuantum job returned incomplete shots")
                        attempt["output"] = {str(key): int(value) for key, value in output.items()}
                    attempt["credit_balance_after_terminal"] = self._balance()
                    self._save_state()
            if active == 0:
                return
            now = time.monotonic()
            if now - last_heartbeat >= 60.0:
                summary = ",".join(f"{key}:{value}" for key, value in sorted(statuses.items()))
                print(f"QSC_OPENQ_HEARTBEAT active={active} {summary}", flush=True)
                last_heartbeat = now
            time.sleep(self.args.poll_seconds)

    def _completed_attempt(self, logical_id: str) -> dict[str, Any] | None:
        record = self.state["logical_jobs"].get(logical_id)
        if not record:
            return None
        completed = [
            attempt
            for attempt in record["attempts"]
            if attempt.get("job", {}).get("status") == "Completed" and "output" in attempt
        ]
        if len(completed) > 1:
            raise RuntimeError("logical job has multiple completed attempts")
        return None if not completed else completed[0]

    def _is_transient_failure(self, attempt: Mapping[str, Any]) -> bool:
        return is_verified_transient_execution_failure(attempt)

    def _replace_one_transient_failure(self, logical_ids: list[str]) -> None:
        failed = [logical_id for logical_id in logical_ids if self._completed_attempt(logical_id) is None]
        if not failed:
            return
        if len(failed) != 1:
            raise RuntimeError("more than one hardware job failed; one-credit reserve is insufficient")
        logical_id = failed[0]
        attempt = self._latest_attempt(logical_id)
        if not self._is_transient_failure(attempt):
            raise RuntimeError(
                f"job {logical_id} failed without a verified transient-infrastructure message"
            )
        record = self.state["logical_jobs"][logical_id]
        source = (self.root / record["qasm_path"]).read_text(encoding="utf-8")
        self._submit_attempt(
            logical_id,
            qasm=source,
            shots=int(record["shots"]),
            width=int(record["width"]),
            arm=record.get("arm"),
            acquisition=record.get("acquisition"),
            stage=str(record["stage"]),
            main_logical_job=False,
            reserve_purpose="verified_transient_infrastructure_retry",
        )
        self._poll_logical_batch([logical_id])
        if self._completed_attempt(logical_id) is None:
            raise RuntimeError("reserved infrastructure retry also failed")

    def _submit_and_complete_batch(self, requests: list[dict[str, Any]]) -> None:
        logical_ids = []
        for request in requests:
            logical_id = str(request["logical_id"])
            logical_ids.append(logical_id)
            if self._completed_attempt(logical_id) is None:
                record = self.state["logical_jobs"].get(logical_id)
                active = bool(
                    record
                    and record["attempts"]
                    and record["attempts"][-1].get("job", {}).get("status") not in TERMINAL
                )
                terminal_failure = bool(
                    record
                    and record["attempts"]
                    and record["attempts"][-1].get("job", {}).get("status") in TERMINAL
                )
                if not active and not terminal_failure:
                    self._submit_attempt(
                        logical_id,
                        qasm=request["qasm"],
                        shots=int(request["shots"]),
                        width=int(request["width"]),
                        arm=request.get("arm"),
                        acquisition=request.get("acquisition"),
                        stage=str(request["stage"]),
                        main_logical_job=True,
                    )
        pending = [logical_id for logical_id in logical_ids if self._completed_attempt(logical_id) is None]
        if pending:
            self._poll_logical_batch(pending)
            self._replace_one_transient_failure(pending)
        missing = [logical_id for logical_id in logical_ids if self._completed_attempt(logical_id) is None]
        if missing:
            raise RuntimeError(f"batch did not complete: {missing}")

    def _run_references(self) -> None:
        requests = []
        for width, protocol in self.protocols.items():
            logical_id = f"ref_w{width}"
            requests.append(
                {
                    "logical_id": logical_id,
                    "qasm": render_openquantum_reference_qasm(protocol),
                    "shots": protocol.reference_shots,
                    "width": width,
                    "arm": None,
                    "acquisition": None,
                    "stage": "pre_campaign_reference",
                }
            )
        self._submit_and_complete_batch(requests)
        for width, protocol in self.protocols.items():
            logical_id = f"ref_w{width}"
            attempt = self._completed_attempt(logical_id)
            assert attempt is not None
            scores = score_openquantum_counts(attempt["output"], protocol)
            self.state["references"][str(width)] = {
                "logical_id": logical_id,
                "job_id": attempt["job"]["id"],
                "monitor_target": list(scores.monitor_response),
                "payload_reference_bitwise_zero": scores.payload_bitwise_zero,
                "payload_reference_all_zero": scores.payload_all_zero,
                "payload_threshold": reference_payload_threshold(
                    scores.payload_bitwise_zero, protocol
                ),
                "shots_done": scores.shots_done,
            }
        self._event("references_completed")

    @staticmethod
    def _run_id(spec: Mapping[str, Any]) -> str:
        return f"w{spec['width']}_{spec['arm']}_s{spec['seed']}"

    def _rebuild_run(self, spec: Mapping[str, Any]) -> OpenQuantumAdaptiveRun:
        width = int(spec["width"])
        reference = self.state["references"][str(width)]
        run = OpenQuantumAdaptiveRun(
            arm=str(spec["arm"]),
            seed=int(spec["seed"]),
            monitor_target=reference["monitor_target"],
            payload_reference_bitwise_zero=float(reference["payload_reference_bitwise_zero"]),
            protocol=self.protocols[width],
        )
        run_id = self._run_id(spec)
        for acquisition in range(1, self.protocols[width].acquisitions + 1):
            logical_id = f"{run_id}_q{acquisition:02d}"
            completed = self._completed_attempt(logical_id)
            if completed is None:
                break
            record = self.state["logical_jobs"][logical_id]
            row = record.get("acquisition_row")
            replay = run.consume(
                completed["output"],
                job_metadata=self._job_metadata(completed),
                controller_update_seconds_override=(
                    None if row is None else float(row["controller_update_seconds"])
                ),
            )
            if replay["qasm_sha256"] != record["qasm_sha256"]:
                raise RuntimeError("replayed adaptive command does not match submitted QASM")
            if row is None:
                record["acquisition_row"] = replay
                self._save_state()
            else:
                for key in (
                    "acquisition",
                    "acquisition_kind",
                    "contract_eligible",
                    "command",
                    "effective_phase_error",
                    "monitor_response",
                    "monitor_rmse",
                    "payload_bitwise_zero",
                    "shots_done",
                ):
                    if replay[key] != row[key]:
                        raise RuntimeError(f"replayed acquisition differs at field {key}")
        return run

    @staticmethod
    def _job_metadata(attempt: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": attempt["job"]["id"],
            "status": attempt["job"]["status"],
            "submitted_at": attempt["job"].get("submitted_at"),
            "terminal_observed_at": attempt.get("terminal_observed_at"),
            "submitted_to_terminal_observation_seconds": attempt.get(
                "submitted_to_terminal_observation_seconds"
            ),
            "quote_spark_credits": attempt["selected_quote"]["total_spark_credits"],
            "provider_execution_seconds": None,
            "provider_execution_timing_note": (
                "OpenQuantum SDK supplied no execution-duration field; cloud wall time includes queue"
            ),
        }

    def _run_adaptive_batches(self) -> None:
        for acquisition in range(1, 5):
            requests = []
            sessions: dict[str, OpenQuantumAdaptiveRun] = {}
            for spec in self.run_specs:
                run_id = self._run_id(spec)
                session = self._rebuild_run(spec)
                sessions[run_id] = session
                if len(session.trace) >= acquisition:
                    continue
                request = session.next_request()
                if request.acquisition != acquisition:
                    raise RuntimeError("adaptive runs lost acquisition-batch alignment")
                logical_id = f"{run_id}_q{acquisition:02d}"
                requests.append(
                    {
                        "logical_id": logical_id,
                        "qasm": request.qasm,
                        "shots": session.protocol.shots,
                        "width": session.protocol.width,
                        "arm": session.arm,
                        "acquisition": acquisition,
                        "stage": "adaptive_confirmation",
                    }
                )
            if requests:
                self._submit_and_complete_batch(requests)
            for spec in self.run_specs:
                run_id = self._run_id(spec)
                session = self._rebuild_run(spec)
                if len(session.trace) < acquisition:
                    raise RuntimeError("completed batch did not advance an adaptive run")
            self._event("adaptive_batch_completed", acquisition=acquisition)

        for spec in self.run_specs:
            run_id = self._run_id(spec)
            result = self._rebuild_run(spec).result()
            self.state["run_results"][run_id] = result
        self._event("adaptive_campaign_completed")

    def _run_post_reference_if_available(self) -> None:
        if self.state["reserve_used"]:
            self.state["post_reference"] = {
                "status": "not_run",
                "reason": "reserve_used_for_infrastructure_retry",
            }
            self._save_state()
            return
        width = self._post_reference_width()
        protocol = self.protocols[width]
        logical_id = f"post_ref_w{width}"
        if self._completed_attempt(logical_id) is None:
            self._submit_attempt(
                logical_id,
                qasm=render_openquantum_reference_qasm(protocol),
                shots=protocol.reference_shots,
                width=width,
                arm=None,
                acquisition=None,
                stage="post_campaign_reference",
                main_logical_job=False,
                reserve_purpose="post_campaign_width_54_reference",
            )
            self._poll_logical_batch([logical_id])
        attempt = self._completed_attempt(logical_id)
        if attempt is None:
            self.state["post_reference"] = {
                "status": "failed",
                "job": self._latest_attempt(logical_id).get("job"),
            }
            self._save_state()
            return
        scores = score_openquantum_counts(attempt["output"], protocol)
        pre = self.state["references"][str(width)]
        pre_target = np.asarray(pre["monitor_target"], dtype=np.float64)
        post_target = np.asarray(scores.monitor_response, dtype=np.float64)
        self.state["post_reference"] = {
            "status": "completed",
            "logical_id": logical_id,
            "job_id": attempt["job"]["id"],
            "monitor_response": list(scores.monitor_response),
            "monitor_rmse_from_pre_reference": float(
                np.sqrt(np.mean(np.square(post_target - pre_target)))
            ),
            "payload_bitwise_zero": scores.payload_bitwise_zero,
            "payload_bitwise_zero_delta": (
                scores.payload_bitwise_zero - float(pre["payload_reference_bitwise_zero"])
            ),
            "shots_done": scores.shots_done,
        }
        self._event("post_reference_completed")

    def _post_reference_width(self) -> int:
        return 54

    def run(self) -> None:
        if self.state.get("complete"):
            print(f"QSC_OPENQ_ALREADY_COMPLETE checkpoint={self.checkpoint_path}", flush=True)
            return
        print(
            "QSC_OPENQ_START "
            f"commit={self.state['protocol_commit']} "
            f"spark={self.state['credit_balance_initial']['spark_credits']} "
            f"queue={self.state['backend_audit']['queue_depth']}",
            flush=True,
        )
        if not self.state["references"]:
            self._run_references()
        self._run_adaptive_batches()
        self._run_post_reference_if_available()
        self.state["credit_balance_final"] = self._balance()
        self.state["completed_at"] = utc_now()
        self.state["complete"] = True
        self._save_state()
        print(
            f"QSC_OPENQ_CAMPAIGN_COMPLETE checkpoint={self.checkpoint_path} "
            f"spark_remaining={self.state['credit_balance_final']['spark_credits']}",
            flush=True,
        )


def main() -> None:
    args = parse_args()
    campaign = Campaign(args)
    try:
        campaign.run()
    finally:
        campaign.close()


if __name__ == "__main__":
    main()
