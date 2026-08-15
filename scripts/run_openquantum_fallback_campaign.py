#!/usr/bin/env python3
"""Run the frozen largest-executable-width Cepheus fallback campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from qsc_bench.openquantum_scale import (
    CEPHEUS_BACKEND,
    cepheus_protocol,
    reference_payload_threshold,
    render_openquantum_reference_qasm,
    score_openquantum_counts,
)

from run_openquantum_scale_campaign import (
    Campaign,
    TERMINAL,
    is_verified_transient_execution_failure,
    utc_now,
)


CANDIDATE_WIDTHS = (48, 42, 36, 30, 24)
WIDTH_SEEDS = {
    18: 1592645915,
    24: 1825850902,
    30: 1477536578,
    36: 391740083,
    42: 1414821560,
    48: 1971211535,
}
HIGH_ARMS = (
    "retained_residual",
    "diagonal_secant",
    "commissioned_pi",
    "do_nothing",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/hardware/openquantum_cepheus_executable_width_v1.json"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("checkpoints/openquantum_cepheus_executable_width_v1"),
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


class ExecutableWidthCampaign(Campaign):
    def _validate_static_config(self) -> None:
        if self.config.get("schema_version") != "qsc-openquantum-cepheus-executable-width-v1":
            raise ValueError("unexpected executable-width protocol schema")
        if self.config.get("backend_short_code") != CEPHEUS_BACKEND:
            raise ValueError("fallback config selects an unexpected backend")
        if self.config.get("candidate_high_widths") != list(CANDIDATE_WIDTHS):
            raise ValueError("candidate-width ladder differs from the freeze")
        if self.config.get("width_seeds") != {
            str(width): seed for width, seed in WIDTH_SEEDS.items()
        }:
            raise ValueError("fallback confirmation seeds differ from the freeze")
        if self.config.get("selected_high_width_arms") != list(HIGH_ARMS):
            raise ValueError("high-width arm matrix differs from the freeze")
        for key, expected in (
            ("shots_per_reference", 2048),
            ("shots_per_acquisition", 2048),
            ("acquisition_deadline", 4),
            ("required_consecutive_ordinary_acquisitions", 2),
            ("planned_main_spark_credits", 21),
            ("reserved_spark_credits", 1),
            ("maximum_quote_per_job_spark_credits", 1),
            ("paid_full_credits_authorized", 0),
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

    def _build_protocols(self) -> dict[int, Any]:
        return {
            width: cepheus_protocol(width)
            for width in (18, *CANDIDATE_WIDTHS)
        }

    def _build_run_specs(self) -> list[dict[str, Any]]:
        return []

    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self.state["capture_schema"] = "qsc-openquantum-executable-width-checkpoint-v1"
        self.state.setdefault("triggering_evidence", self.config["triggering_evidence"])
        self._configure_run_specs()
        self._save_state()

    def _configure_run_specs(self) -> None:
        selected = self.state.get("selected_high_width")
        if selected is None:
            self.run_specs = []
            return
        high = int(selected)
        if high == 18:
            self.run_specs = [
                {"width": 18, "arm": arm, "seed": WIDTH_SEEDS[18]}
                for arm in HIGH_ARMS
            ]
            return
        self.run_specs = [
            {"width": 18, "arm": "retained_residual", "seed": WIDTH_SEEDS[18]},
            *[
                {"width": high, "arm": arm, "seed": WIDTH_SEEDS[high]}
                for arm in HIGH_ARMS
            ],
        ]

    def _import_low_reference(self) -> None:
        if "18" in self.state["references"]:
            return
        source_state_path = self.root / self.config["low_width_reference_source"]
        source_state = json.loads(source_state_path.read_text(encoding="utf-8"))
        record = source_state["logical_jobs"]["ref_w18"]
        completed = [
            attempt
            for attempt in record["attempts"]
            if attempt.get("job", {}).get("status") == "Completed" and "output" in attempt
        ]
        if len(completed) != 1:
            raise RuntimeError("imported width-18 reference is not uniquely complete")
        expected_source = render_openquantum_reference_qasm(self.protocols[18])
        expected_hash = hashlib.sha256(expected_source.encode("utf-8")).hexdigest()
        if record.get("qasm_sha256") != expected_hash:
            raise RuntimeError("imported width-18 reference QASM differs from this protocol")
        scores = score_openquantum_counts(completed[0]["output"], self.protocols[18])
        self.state["references"]["18"] = {
            "imported_from": str(source_state_path.relative_to(self.root)),
            "logical_id": "ref_w18",
            "job_id": completed[0]["job"]["id"],
            "qasm_sha256": expected_hash,
            "monitor_target": list(scores.monitor_response),
            "payload_reference_bitwise_zero": scores.payload_bitwise_zero,
            "payload_reference_all_zero": scores.payload_all_zero,
            "payload_threshold": reference_payload_threshold(
                scores.payload_bitwise_zero, self.protocols[18]
            ),
            "shots_done": scores.shots_done,
        }
        self._event("width_18_reference_imported")

    def _record_refunded_candidate_failure(
        self, logical_id: str, attempt: Mapping[str, Any]
    ) -> None:
        if not is_verified_transient_execution_failure(attempt):
            raise RuntimeError(
                f"candidate {logical_id} failed outside the frozen provider-execution class"
            )
        before = attempt["credit_balance_before"]
        after = attempt["credit_balance_after_terminal"]
        if float(before["spark_credits"]) != float(after["spark_credits"]):
            raise RuntimeError("failed capability candidate was not refunded")
        if float(after["full_credits"]) != 0.0:
            raise RuntimeError("paid Full-credit balance changed during capability selection")
        record = self.state["logical_jobs"][logical_id]
        if not record.get("refund_accounted"):
            quote = int(attempt["selected_quote"]["total_spark_credits"])
            self.state["main_logical_jobs_submitted"] = (
                int(self.state["main_logical_jobs_submitted"]) - quote
            )
            record["refund_accounted"] = True
            record["capability_interpretation"] = (
                "provider execution unavailable at this width; no controller observation"
            )
            self._event(
                "capability_candidate_failed_and_refunded",
                logical_id=logical_id,
                job_id=attempt["job"]["id"],
                provider_message=attempt["job"].get("message"),
            )

    def _select_high_reference(self) -> None:
        if self.state.get("selected_high_width") is not None:
            return
        for width in CANDIDATE_WIDTHS:
            logical_id = f"candidate_ref_w{width}"
            completed = self._completed_attempt(logical_id)
            if completed is None:
                record = self.state["logical_jobs"].get(logical_id)
                if record and record["attempts"]:
                    attempt = record["attempts"][-1]
                    if attempt.get("job", {}).get("status") in TERMINAL:
                        self._record_refunded_candidate_failure(logical_id, attempt)
                        continue
                protocol = self.protocols[width]
                self._submit_attempt(
                    logical_id,
                    qasm=render_openquantum_reference_qasm(protocol),
                    shots=protocol.reference_shots,
                    width=width,
                    arm=None,
                    acquisition=None,
                    stage="executable_width_reference",
                    main_logical_job=True,
                )
                self._poll_logical_batch([logical_id])
                completed = self._completed_attempt(logical_id)
            if completed is None:
                attempt = self._latest_attempt(logical_id)
                self._record_refunded_candidate_failure(logical_id, attempt)
                continue
            protocol = self.protocols[width]
            scores = score_openquantum_counts(completed["output"], protocol)
            self.state["references"][str(width)] = {
                "logical_id": logical_id,
                "job_id": completed["job"]["id"],
                "qasm_sha256": self.state["logical_jobs"][logical_id]["qasm_sha256"],
                "monitor_target": list(scores.monitor_response),
                "payload_reference_bitwise_zero": scores.payload_bitwise_zero,
                "payload_reference_all_zero": scores.payload_all_zero,
                "payload_threshold": reference_payload_threshold(
                    scores.payload_bitwise_zero, protocol
                ),
                "shots_done": scores.shots_done,
            }
            self.state["selected_high_width"] = width
            self.state["selected_high_physical_qubits"] = 2 * width
            self._event(
                "executable_high_width_selected",
                width=width,
                physical_qubits=2 * width,
                job_id=completed["job"]["id"],
            )
            return
        self.state["selected_high_width"] = 18
        self.state["selected_high_physical_qubits"] = 36
        self._event(
            "no_fallback_candidate_executed",
            fallback_to_completed_width=18,
        )

    def _run_references(self) -> None:
        self._import_low_reference()
        self._select_high_reference()
        self._configure_run_specs()
        self._event(
            "references_ready",
            selected_high_width=self.state["selected_high_width"],
        )

    def _post_reference_width(self) -> int:
        return int(self.state["selected_high_width"])

    def run(self) -> None:
        if self.state.get("complete"):
            print(f"QSC_OPENQ_FALLBACK_ALREADY_COMPLETE checkpoint={self.checkpoint_path}", flush=True)
            return
        print(
            "QSC_OPENQ_FALLBACK_START "
            f"commit={self.state['protocol_commit']} "
            f"spark={self.state['credit_balance_initial']['spark_credits']} "
            f"queue={self.state['backend_audit']['queue_depth']}",
            flush=True,
        )
        if self.state.get("selected_high_width") is None:
            self._run_references()
        self._configure_run_specs()
        self._run_adaptive_batches()
        self._run_post_reference_if_available()
        self.state["credit_balance_final"] = self._balance()
        self.state["completed_at"] = utc_now()
        self.state["complete"] = True
        self._save_state()
        print(
            "QSC_OPENQ_FALLBACK_COMPLETE "
            f"selected_width={self.state['selected_high_width']} "
            f"physical_qubits={self.state['selected_high_physical_qubits']} "
            f"spark_remaining={self.state['credit_balance_final']['spark_credits']}",
            flush=True,
        )


def main() -> None:
    args = parse_args()
    campaign = ExecutableWidthCampaign(args)
    try:
        campaign.run()
    finally:
        campaign.close()


if __name__ == "__main__":
    main()
