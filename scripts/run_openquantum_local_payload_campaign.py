#!/usr/bin/env python3
"""Run the frozen 96-qubit local-payload QSC hardware confirmation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import numpy as np

from qsc_bench.openquantum_scale import CEPHEUS_BACKEND, cepheus_local_protocol

from run_openquantum_scale_campaign import Campaign, utc_now


CONFIRMATION_SEED = 298495185


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/hardware/openquantum_cepheus_96q_local_payload_v1.json"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("checkpoints/openquantum_cepheus_96q_local_payload_v1"),
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


class LocalPayloadCampaign(Campaign):
    def _validate_static_config(self) -> None:
        if self.config.get("schema_version") != "qsc-openquantum-cepheus-96q-local-payload-v1":
            raise ValueError("unexpected local-payload protocol schema")
        if self.config.get("backend_short_code") != CEPHEUS_BACKEND:
            raise ValueError("local-payload config selects an unexpected backend")
        if int(self.config.get("controlled_width", -1)) != 48:
            raise ValueError("local-payload width differs from the freeze")
        if int(self.config.get("physical_qubits", -1)) != 96:
            raise ValueError("local-payload physical width differs from the freeze")
        if self.config.get("arms") != ["retained_residual", "do_nothing"]:
            raise ValueError("local-payload arm matrix differs from the freeze")
        if int(self.config.get("confirmation_seed", -1)) != CONFIRMATION_SEED:
            raise ValueError("local-payload seed differs from the freeze")
        for key, expected in (
            ("shots_per_reference", 2048),
            ("shots_per_acquisition", 2048),
            ("acquisition_deadline", 4),
            ("required_consecutive_ordinary_acquisitions", 2),
            ("planned_main_spark_credits", 9),
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
        return {48: cepheus_local_protocol(48)}

    def _build_run_specs(self) -> list[dict[str, Any]]:
        return [
            {"width": 48, "arm": "retained_residual", "seed": CONFIRMATION_SEED},
            {"width": 48, "arm": "do_nothing", "seed": CONFIRMATION_SEED},
        ]

    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self.state["capture_schema"] = "qsc-openquantum-96q-local-payload-checkpoint-v1"
        self.state.setdefault("triggering_evidence", self.config["triggering_evidence"])
        self._save_state()

    def _post_reference_width(self) -> int:
        return 48

    def run(self) -> None:
        if self.state.get("complete"):
            print(f"QSC_OPENQ_LOCAL_ALREADY_COMPLETE checkpoint={self.checkpoint_path}", flush=True)
            return
        print(
            "QSC_OPENQ_LOCAL_START "
            f"commit={self.state['protocol_commit']} "
            f"spark={self.state['credit_balance_initial']['spark_credits']} "
            f"queue={self.state['backend_audit']['queue_depth']}",
            flush=True,
        )
        if not self.state["references"]:
            self._run_references()
        reference = self.state["references"]["48"]
        admissible = (
            int(reference["shots_done"]) == 2048
            and float(reference["payload_reference_bitwise_zero"]) >= 0.70
        )
        self.state["reference_admissible"] = admissible
        self._save_state()
        if not admissible:
            self.state["campaign_status"] = "BLOCKED_REFERENCE_BELOW_USABILITY_FLOOR"
            self.state["credit_balance_final"] = self._balance()
            self.state["completed_at"] = utc_now()
            self.state["complete"] = True
            self._save_state()
            print(
                "QSC_OPENQ_LOCAL_BLOCKED "
                f"payload_reference={reference['payload_reference_bitwise_zero']}",
                flush=True,
            )
            return
        self._event(
            "local_payload_reference_admissible",
            payload_reference=reference["payload_reference_bitwise_zero"],
            payload_threshold=reference["payload_threshold"],
        )
        self._run_adaptive_batches()
        self._run_post_reference_if_available()
        self.state["campaign_status"] = "COMPLETED"
        self.state["credit_balance_final"] = self._balance()
        self.state["completed_at"] = utc_now()
        self.state["complete"] = True
        self._save_state()
        print(
            "QSC_OPENQ_LOCAL_COMPLETE "
            f"spark_remaining={self.state['credit_balance_final']['spark_credits']}",
            flush=True,
        )


def main() -> None:
    args = parse_args()
    campaign = LocalPayloadCampaign(args)
    try:
        campaign.run()
    finally:
        campaign.close()


if __name__ == "__main__":
    main()
