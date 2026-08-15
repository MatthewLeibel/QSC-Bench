#!/usr/bin/env python3
"""Run the frozen 96-qubit single-Rx OpenQuantum confirmation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from qsc_bench.openquantum_scale import CEPHEUS_BACKEND, cepheus_single_rx_protocol

from run_openquantum_scale_campaign import Campaign, utc_now


CONFIRMATION_SEED = 881723051


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/hardware/openquantum_cepheus_96q_single_rx_v3.json"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("checkpoints/openquantum_cepheus_96q_single_rx_v3"),
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


class SingleRxCampaign(Campaign):
    def _validate_static_config(self) -> None:
        if self.config.get("schema_version") != "qsc-openquantum-cepheus-96q-single-rx-v3":
            raise ValueError("unexpected single-Rx protocol schema")
        if self.config.get("backend_short_code") != CEPHEUS_BACKEND:
            raise ValueError("single-Rx config selects an unexpected backend")
        if int(self.config.get("controlled_width", -1)) != 48:
            raise ValueError("single-Rx controlled width differs from the freeze")
        if int(self.config.get("physical_qubits", -1)) != 96:
            raise ValueError("single-Rx physical width differs from the freeze")
        if self.config.get("arms") != ["retained_residual", "do_nothing"]:
            raise ValueError("single-Rx arm matrix differs from the freeze")
        if int(self.config.get("confirmation_seed", -1)) != CONFIRMATION_SEED:
            raise ValueError("single-Rx seed differs from the freeze")
        phrase = str(self.config.get("confirmation_seed_phrase", ""))
        digest = hashlib.sha256(phrase.encode("utf-8")).hexdigest()
        if digest != self.config.get("confirmation_seed_phrase_sha256"):
            raise ValueError("confirmation seed phrase hash differs from the freeze")
        if int(digest[:16], 16) % (2**31 - 1) != CONFIRMATION_SEED:
            raise ValueError("confirmation seed derivation differs from the freeze")
        if self.config.get("confirmation_seed_evaluated_before_freeze") is not False:
            raise ValueError("confirmation seed must remain unseen before freeze")
        for key, expected in (
            ("shots_per_reference", 2048),
            ("shots_per_acquisition", 2048),
            ("acquisition_deadline", 4),
            ("required_consecutive_ordinary_acquisitions", 2),
            ("planned_main_spark_credits", 9),
            ("reserved_spark_credits", 0),
            ("maximum_quote_per_job_spark_credits", 1),
            ("paid_full_credits_authorized", 0),
        ):
            if int(self.config.get(key, -1)) != expected:
                raise ValueError(f"{key} differs from the executable protocol")
        for key, expected in (
            ("monitor_rmse_tolerance", 0.08),
            ("payload_bitwise_zero_absolute_floor", 0.80),
            ("payload_reference_margin", 0.10),
            ("initial_commanded_shock_rms_radians", 0.45),
            ("identification_amplitude_radians", 0.15),
            ("payload_phase_amplification", 3.0),
        ):
            if not np.isclose(float(self.config.get(key, float("nan"))), expected):
                raise ValueError(f"{key} differs from the executable protocol")
        protocol = cepheus_single_rx_protocol()
        if self.config.get("monitor_qubit_indices") != list(protocol.monitor_qubits):
            raise ValueError("monitor mapping differs from the executable protocol")

    def _build_protocols(self) -> dict[int, Any]:
        return {48: cepheus_single_rx_protocol()}

    def _build_run_specs(self) -> list[dict[str, Any]]:
        return [
            {"width": 48, "arm": "retained_residual", "seed": CONFIRMATION_SEED},
            {"width": 48, "arm": "do_nothing", "seed": CONFIRMATION_SEED},
        ]

    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self.state["capture_schema"] = "qsc-openquantum-96q-single-rx-checkpoint-v3"
        self.state.setdefault("characterization", self.config["characterization"])
        self._save_state()

    @staticmethod
    def _frame_passes(session: Any, row: dict[str, Any]) -> bool:
        return bool(
            row["contract_eligible"]
            and row["monitor_rmse"] <= session.protocol.monitor_tolerance
            and row["payload_bitwise_zero"] >= session.payload_threshold
        )

    def _futility_result(self, session: Any) -> dict[str, Any]:
        if session.arm != "do_nothing" or len(session.trace) != 3:
            raise RuntimeError("futility result requires the three-frame do-nothing arm")
        if self._frame_passes(session, session.trace[-1]):
            raise RuntimeError("a passing acquisition 3 cannot be stopped for futility")
        return {
            "schema_version": "qsc-openquantum-scale-run-futility-censored-v1",
            "arm": session.arm,
            "seed": session.seed,
            "protocol": session.protocol.public_dict(),
            "scenario": session.scenario.public_dict(),
            "scenario_sha256": hashlib.sha256(
                json.dumps(session.scenario.public_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "monitor_target": [float(value) for value in session.monitor_target],
            "payload_reference_bitwise_zero": session.payload_reference_bitwise_zero,
            "payload_threshold": session.payload_threshold,
            "contract_entry_acquisition": None,
            "contract_success": False,
            "contract_at_deadline": False,
            "outcome_determined_after_acquisition": 3,
            "not_executed_acquisitions": [4],
            "futility_reason": (
                "Acquisition 3 failed the contract. With two consecutive passing "
                "frames required, entry by acquisition 4 became mathematically impossible."
            ),
            "protocol_deviation": (
                "Acquisition 4 was omitted after its binary deadline outcome became "
                "invariant. This early-stop rule was added after observing acquisition 3."
            ),
            "structural_minimum_acquisitions_to_confirm": 2,
            "dense_fd_structural_minimum_acquisitions_to_confirm": (
                session.protocol.width + 1 + session.protocol.required_consecutive
            ),
            "controller_metadata": asdict(session.controller.metadata),
            "controller_mutable_state_bytes": session.controller.mutable_state_bytes(),
            "controller_float_words_per_channel": (
                session.controller.mutable_float_words_per_channel()
            ),
            "trace": list(session.trace),
            "final_command": [float(value) for value in session.controller.u],
            "total_controller_update_seconds": sum(
                float(row["controller_update_seconds"]) for row in session.trace
            ),
        }

    def _run_adaptive_batches(self) -> None:
        """Resume the frozen run with a disclosed outcome-invariant futility stop."""

        self.state.setdefault("futility_stops", {})
        for acquisition in range(1, 5):
            requests = []
            skipped: set[str] = set()
            for spec in self.run_specs:
                run_id = self._run_id(spec)
                session = self._rebuild_run(spec)
                if len(session.trace) >= acquisition:
                    continue
                if acquisition == 4 and session.arm == "do_nothing":
                    if len(session.trace) != 3:
                        raise RuntimeError("do-nothing futility check requires three frames")
                    if not self._frame_passes(session, session.trace[-1]):
                        skipped.add(run_id)
                        self.state["futility_stops"][run_id] = {
                            "decision_after_acquisition": 3,
                            "not_executed_acquisitions": [4],
                            "reason": (
                                "two consecutive passes are impossible by deadline after "
                                "acquisition 3 failed"
                            ),
                            "protocol_deviation_disclosed": True,
                        }
                        self.state["effective_planned_main_spark_credits"] = 8
                        self._save_state()
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
                expected = acquisition - 1 if run_id in skipped else acquisition
                if len(session.trace) < expected:
                    raise RuntimeError("completed batch did not advance an adaptive run")
            if not any(
                event.get("kind") == "adaptive_batch_completed"
                and int(event.get("acquisition", -1)) == acquisition
                for event in self.state["events"]
            ):
                self._event("adaptive_batch_completed", acquisition=acquisition)

        for spec in self.run_specs:
            run_id = self._run_id(spec)
            session = self._rebuild_run(spec)
            self.state["run_results"][run_id] = (
                session.result() if session.complete else self._futility_result(session)
            )
        self.state["main_jobs_avoided_by_outcome_invariant_futility"] = 1
        self._event(
            "adaptive_campaign_completed",
            protocol_deviation=(
                "do-nothing acquisition 4 omitted only after acquisition 3 made "
                "deadline entry mathematically impossible"
            ),
        )

    def run(self) -> None:
        if self.state.get("complete"):
            print(
                f"QSC_OPENQ_SINGLE_RX_ALREADY_COMPLETE checkpoint={self.checkpoint_path}",
                flush=True,
            )
            return
        print(
            "QSC_OPENQ_SINGLE_RX_START "
            f"commit={self.state['protocol_commit']} "
            f"spark={self.state['credit_balance_initial']['spark_credits']} "
            f"queue={self.state['backend_audit']['queue_depth']}",
            flush=True,
        )
        if not self.state["references"]:
            self._run_references()
        reference = self.state["references"]["48"]
        targets = np.asarray(reference["monitor_target"], dtype=np.float64)
        rule = self.config["reference_admissibility"]
        admissible = (
            int(reference["shots_done"]) == int(rule["shots_exactly"])
            and float(reference["payload_reference_bitwise_zero"])
            >= float(rule["payload_bitwise_zero_minimum"])
            and bool(np.all(targets >= float(rule["every_monitor_target_minimum"])))
            and bool(np.all(targets <= float(rule["every_monitor_target_maximum"])))
        )
        self.state["reference_admissible"] = admissible
        self.state["reference_monitor_minimum"] = float(np.min(targets))
        self.state["reference_monitor_maximum"] = float(np.max(targets))
        self._save_state()
        if not admissible:
            self.state["campaign_status"] = "BLOCKED_REFERENCE_ADMISSIBILITY"
            self.state["credit_balance_final"] = self._balance()
            self.state["completed_at"] = utc_now()
            self.state["complete"] = True
            self._save_state()
            print(
                "QSC_OPENQ_SINGLE_RX_BLOCKED "
                f"payload_reference={reference['payload_reference_bitwise_zero']} "
                f"monitor_min={np.min(targets)} monitor_max={np.max(targets)}",
                flush=True,
            )
            return
        self._event(
            "single_rx_reference_admissible",
            payload_reference=reference["payload_reference_bitwise_zero"],
            payload_threshold=reference["payload_threshold"],
            monitor_minimum=float(np.min(targets)),
            monitor_maximum=float(np.max(targets)),
        )
        self._run_adaptive_batches()
        self.state["post_reference"] = {
            "status": "not_run",
            "reason": "all remaining Spark credits allocated to the frozen comparison",
        }
        self.state["campaign_status"] = "COMPLETED"
        self.state["credit_balance_final"] = self._balance()
        self.state["completed_at"] = utc_now()
        self.state["complete"] = True
        self._save_state()
        print(
            "QSC_OPENQ_SINGLE_RX_COMPLETE "
            f"spark_remaining={self.state['credit_balance_final']['spark_credits']}",
            flush=True,
        )


def main() -> None:
    args = parse_args()
    campaign = SingleRxCampaign(args)
    try:
        campaign.run()
    finally:
        campaign.close()


if __name__ == "__main__":
    main()
