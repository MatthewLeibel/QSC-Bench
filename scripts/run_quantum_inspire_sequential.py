#!/usr/bin/env python3
"""Run a frozen QI hybrid artifact as sequential direct hardware jobs.

This is the fallback for a provider hybrid-runtime failure.  The generated
controller artifact is executed unchanged, but each ``execute_circuit`` call is
implemented as an individually recorded direct job.  Queue latency therefore
appears between acquisitions and is kept distinct from the provider's measured
execution time.

Run with the authenticated Quantum Inspire CLI interpreter, for example::

    ~/.local/pipx/venvs/quantuminspire/bin/python \
      scripts/run_quantum_inspire_sequential.py SOURCE.py OUTPUT.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import time
from typing import Any


TERMINAL = {"completed", "failed", "cancelled"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend-type-id", type=int, default=6)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--max-infrastructure-retries", type=int, default=1)
    parser.add_argument("--max-network-retries", type=int, default=360)
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument(
        "--resume-job-id",
        action="append",
        default=[],
        metavar="ACQUISITION:JOB_ID",
        help="Reuse an already-submitted job missing from an older checkpoint.",
    )
    return parser.parse_args()


def _model_json(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _parse_resume_job_ids(values: list[str]) -> dict[int, int]:
    result: dict[int, int] = {}
    for value in values:
        acquisition_text, separator, job_text = value.partition(":")
        if not separator:
            raise ValueError("resume job IDs must use ACQUISITION:JOB_ID")
        acquisition = int(acquisition_text)
        job_id = int(job_text)
        if acquisition < 1 or job_id < 1 or acquisition in result:
            raise ValueError("invalid or duplicate resume job mapping")
        result[acquisition] = job_id
    return result


class SequentialDirectQuantumInterface:
    def __init__(
        self,
        *,
        api: Any,
        backend_type_id: int,
        session_directory: Path,
        poll_seconds: float,
        max_infrastructure_retries: int,
        max_network_retries: int,
        source_sha256: str,
        existing_calls: list[dict[str, Any]] | None = None,
        resume_job_ids: dict[int, int] | None = None,
    ):
        self.api = api
        self.backend_type_id = backend_type_id
        self.session_directory = session_directory
        self.poll_seconds = poll_seconds
        self.max_infrastructure_retries = max_infrastructure_retries
        self.max_network_retries = max_network_retries
        self.source_sha256 = source_sha256
        self.resume_job_ids = resume_job_ids or {}
        self.results: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = existing_calls or []
        self.logical_call_index = 0
        self.network_retry_count = 0
        self.resume_events: list[dict[str, Any]] = []

    def _read_with_retries(self, label: str, function: Any, *args: Any, **kwargs: Any) -> Any:
        for retry in range(self.max_network_retries + 1):
            try:
                return function(*args, **kwargs)
            except Exception as exc:
                if retry >= self.max_network_retries:
                    raise
                self.network_retry_count += 1
                print(
                    "QSC_QI_NETWORK_RETRY "
                    f"operation={label} retry={retry + 1} "
                    f"error_type={type(exc).__name__}",
                    flush=True,
                )
                time.sleep(self.poll_seconds)
        raise AssertionError("unreachable network retry state")

    def _capture(self, job_id: int) -> dict[str, Any]:
        job = self._read_with_retries("get_job_capture", self.api.get_job, job_id=job_id)
        results = self._read_with_retries(
            "get_results_capture", self.api.get_results, job_id=job_id
        )
        final_result = self._read_with_retries(
            "get_final_result_capture", self.api.get_final_result, job_id=job_id
        )
        return {
            "capture_schema": "qsc-quantum-inspire-job-capture-v1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "job": _model_json(job),
            "results": [_model_json(result) for result in results],
            "final_result": None if final_result is None else _model_json(final_result),
        }

    def _checkpoint(self) -> None:
        path = self.session_directory / "SEQUENTIAL_SESSION_CHECKPOINT.json"
        path.write_text(
            json.dumps(
                {
                    "capture_schema": "qsc-qi-sequential-session-checkpoint-v1",
                    "source_sha256": self.source_sha256,
                    "calls": self.calls,
                    "network_retry_count": self.network_retry_count,
                    "resume_events": self.resume_events,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def execute_circuit(
        self, circuit: str, number_of_shots: int, raw_data_enabled: bool = False
    ) -> SimpleNamespace:
        self.logical_call_index += 1
        call_index = self.logical_call_index
        circuit_digest = hashlib.sha256(circuit.encode("utf-8")).hexdigest()
        circuit_path = self.session_directory / f"acquisition_{call_index:02d}_{circuit_digest[:12]}.cq"
        circuit_path.write_text(circuit, encoding="utf-8")
        if call_index <= len(self.calls):
            call_record = self.calls[call_index - 1]
            if int(call_record.get("acquisition", -1)) != call_index:
                raise RuntimeError("resume checkpoint acquisition index mismatch")
            if call_record.get("circuit_sha256") != circuit_digest:
                raise RuntimeError("resume checkpoint circuit hash mismatch")
            if int(call_record.get("shots_requested", -1)) != int(number_of_shots):
                raise RuntimeError("resume checkpoint shot count mismatch")
        else:
            call_record = {
                "acquisition": call_index,
                "circuit_sha256": circuit_digest,
                "shots_requested": int(number_of_shots),
                "attempts": [],
            }
            self.calls.append(call_record)
            self._checkpoint()

        selected_job_id = call_record.get("selected_job_id")
        if selected_job_id is not None:
            selected_captures = [
                capture
                for capture in call_record.get("attempts", [])
                if int(capture["job"]["id"]) == int(selected_job_id)
            ]
            if len(selected_captures) != 1:
                raise RuntimeError("resume checkpoint has no unique selected capture")
            selected_results = selected_captures[0].get("results", [])
            if len(selected_results) != 1:
                raise RuntimeError("resume checkpoint selected capture is incomplete")
            selected = selected_results[0]
            self.results.append({"results": selected["results"]})
            self.resume_events.append(
                {
                    "acquisition": call_index,
                    "action": "replayed_completed_result",
                    "job_id": int(selected_job_id),
                }
            )
            print(
                f"QSC_QI_REPLAYED acquisition={call_index} job_id={selected_job_id}",
                flush=True,
            )
            return SimpleNamespace(
                results=selected["results"],
                raw_data=selected.get("raw_data"),
                shots_requested=int(selected["shots_requested"]),
                shots_done=int(selected["shots_done"]),
            )

        attempts = call_record.setdefault("attempts", [])
        pending_job_id = call_record.get("submitted_job_id")
        if pending_job_id is None and call_index in self.resume_job_ids:
            pending_job_id = self.resume_job_ids[call_index]
            call_record["submitted_job_id"] = int(pending_job_id)
            self.resume_events.append(
                {
                    "acquisition": call_index,
                    "action": "attached_existing_job",
                    "job_id": int(pending_job_id),
                }
            )
            self._checkpoint()
            print(
                f"QSC_QI_ATTACHED acquisition={call_index} job_id={pending_job_id}",
                flush=True,
            )

        while len(attempts) < self.max_infrastructure_retries + 1:
            if pending_job_id is None:
                # Submission is intentionally not auto-retried.  A connection
                # loss after server acceptance could otherwise duplicate a job.
                submitted = self.api.execute_algorithm(
                    file_path=circuit_path,
                    backend_type_id=self.backend_type_id,
                    num_shots=int(number_of_shots),
                    store_raw_data=bool(raw_data_enabled),
                    persist=False,
                )
                pending_job_id = int(submitted.job_id)
                call_record["submitted_job_id"] = pending_job_id
                self._checkpoint()
                print(
                    "QSC_QI_SUBMITTED "
                    f"acquisition={call_index} attempt={len(attempts) + 1} "
                    f"job_id={pending_job_id}",
                    flush=True,
                )
            job_id = int(pending_job_id)
            last_status = None
            while True:
                job = self._read_with_retries(
                    "get_job_poll", self.api.get_job, job_id=job_id
                )
                status = str(job.status.value)
                if status != last_status:
                    print(
                        f"QSC_QI_STATUS acquisition={call_index} job_id={job_id} status={status}",
                        flush=True,
                    )
                    last_status = status
                if status in TERMINAL:
                    break
                time.sleep(self.poll_seconds)

            capture = self._capture(job_id)
            attempts.append(capture)
            call_record.pop("submitted_job_id", None)
            self._checkpoint()
            if status != "completed":
                print(
                    f"QSC_QI_INFRASTRUCTURE_FAILURE acquisition={call_index} job_id={job_id}",
                    flush=True,
                )
                pending_job_id = None
                continue
            results = capture["results"]
            if len(results) != 1 or not isinstance(results[0].get("results"), dict):
                print(
                    f"QSC_QI_MISSING_RESULT acquisition={call_index} job_id={job_id}",
                    flush=True,
                )
                pending_job_id = None
                continue
            selected = results[0]
            if int(selected["shots_done"]) != int(selected["shots_requested"]):
                print(
                    f"QSC_QI_INCOMPLETE_SHOTS acquisition={call_index} job_id={job_id}",
                    flush=True,
                )
                pending_job_id = None
                continue
            call_record["selected_job_id"] = job_id
            call_record["provider_execution_time_in_seconds"] = float(
                selected["execution_time_in_seconds"]
            )
            self.results.append({"results": selected["results"]})
            self._checkpoint()
            print(
                "QSC_QI_COMPLETED "
                f"acquisition={call_index} job_id={job_id} "
                f"shots={selected['shots_done']} "
                f"provider_execution_seconds={selected['execution_time_in_seconds']}",
                flush=True,
            )
            return SimpleNamespace(
                results=selected["results"],
                raw_data=selected.get("raw_data"),
                shots_requested=int(selected["shots_requested"]),
                shots_done=int(selected["shots_done"]),
            )
        raise RuntimeError(
            f"acquisition {call_index} exhausted infrastructure retries without a valid result"
        )


def main() -> None:
    args = parse_args()
    if args.poll_seconds <= 0.0 or args.poll_seconds > 60.0:
        raise ValueError("poll interval must be in (0, 60] seconds")
    if args.max_infrastructure_retries < 0:
        raise ValueError("max infrastructure retries cannot be negative")
    if args.max_network_retries < 0:
        raise ValueError("max network retries cannot be negative")
    from quantuminspire.api import Api

    args.output.parent.mkdir(parents=True, exist_ok=True)
    session_directory = args.output.parent / (args.output.stem + "_artifacts")
    session_directory.mkdir(parents=True, exist_ok=True)
    source_bytes = args.source.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    existing_calls: list[dict[str, Any]] = []
    if args.resume_checkpoint is not None:
        checkpoint = json.loads(args.resume_checkpoint.read_text(encoding="utf-8"))
        if checkpoint.get("capture_schema") != "qsc-qi-sequential-session-checkpoint-v1":
            raise ValueError("unexpected resume-checkpoint schema")
        checkpoint_source = checkpoint.get("source_sha256")
        if checkpoint_source is not None and checkpoint_source != source_sha256:
            raise ValueError("resume-checkpoint source hash mismatch")
        existing_calls = list(checkpoint.get("calls", []))
    resume_job_ids = _parse_resume_job_ids(args.resume_job_id)
    spec = importlib.util.spec_from_file_location("qsc_frozen_qi_program", args.source)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not import frozen Quantum Inspire program")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    interface = SequentialDirectQuantumInterface(
        api=Api(),
        backend_type_id=args.backend_type_id,
        session_directory=session_directory,
        poll_seconds=args.poll_seconds,
        max_infrastructure_retries=args.max_infrastructure_retries,
        max_network_retries=args.max_network_retries,
        source_sha256=source_sha256,
        existing_calls=existing_calls,
        resume_job_ids=resume_job_ids,
    )
    started = datetime.now(timezone.utc)
    module.execute(interface)
    final = module.finalize(interface.results)
    final["execution_mode"] = "client_orchestrated_sequential_direct_qpu_jobs"
    final["timing_note"] = (
        "each trace execute-call duration includes queue and API time; use the direct "
        "provider result durations in sequential_calls for acquisition-only timing"
    )
    completed = datetime.now(timezone.utc)
    payload = {
        "capture_schema": "qsc-qi-sequential-hardware-run-v1",
        "source_path": str(args.source),
        "source_sha256": source_sha256,
        "backend_type_id": args.backend_type_id,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "client_wall_seconds": (completed - started).total_seconds(),
        "orchestration_resumed": args.resume_checkpoint is not None,
        "network_retry_count": interface.network_retry_count,
        "resume_events": interface.resume_events,
        "sequential_calls": interface.calls,
        "final_result": final,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"QSC_QI_SESSION_COMPLETE output={args.output}", flush=True)


if __name__ == "__main__":
    main()
