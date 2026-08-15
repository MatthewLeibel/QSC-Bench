#!/usr/bin/env python3
"""Run the frozen 96-qubit native-mirror OpenQuantum confirmation."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np

from qsc_bench.openquantum_scale import (
    CEPHEUS_BACKEND,
    cepheus_native_mirror_protocol,
)

from run_openquantum_scale_campaign import Campaign, utc_now


CONFIRMATION_SEED = 1971365805


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/hardware/openquantum_cepheus_96q_native_mirror_v2.json"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("checkpoints/openquantum_cepheus_96q_native_mirror_v2"),
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


class NativeMirrorCampaign(Campaign):
    def _validate_static_config(self) -> None:
        if (
            self.config.get("schema_version")
            != "qsc-openquantum-cepheus-96q-native-mirror-v2"
        ):
            raise ValueError("unexpected native-mirror protocol schema")
        if self.config.get("backend_short_code") != CEPHEUS_BACKEND:
            raise ValueError("native-mirror config selects an unexpected backend")
        if int(self.config.get("controlled_width", -1)) != 48:
            raise ValueError("native-mirror controlled width differs from the freeze")
        if int(self.config.get("physical_qubits", -1)) != 96:
            raise ValueError("native-mirror physical width differs from the freeze")
        if self.config.get("arms") != ["retained_residual", "do_nothing"]:
            raise ValueError("native-mirror arm matrix differs from the freeze")
        if int(self.config.get("confirmation_seed", -1)) != CONFIRMATION_SEED:
            raise ValueError("native-mirror seed differs from the freeze")
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
            ("reserved_spark_credits", 1),
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
        protocol = cepheus_native_mirror_protocol()
        if self.config.get("monitor_qubit_indices") != list(protocol.monitor_qubits):
            raise ValueError("monitor mapping differs from the executable protocol")

    def _build_protocols(self) -> dict[int, Any]:
        return {48: cepheus_native_mirror_protocol()}

    def _build_run_specs(self) -> list[dict[str, Any]]:
        return [
            {"width": 48, "arm": "retained_residual", "seed": CONFIRMATION_SEED},
            {"width": 48, "arm": "do_nothing", "seed": CONFIRMATION_SEED},
        ]

    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self.state["capture_schema"] = "qsc-openquantum-96q-native-mirror-checkpoint-v2"
        self.state.setdefault("characterization", self.config["characterization"])
        self._save_state()

    def _post_reference_width(self) -> int:
        return 48

    def run(self) -> None:
        if self.state.get("complete"):
            print(
                f"QSC_OPENQ_NATIVE_ALREADY_COMPLETE checkpoint={self.checkpoint_path}",
                flush=True,
            )
            return
        print(
            "QSC_OPENQ_NATIVE_START "
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
                "QSC_OPENQ_NATIVE_BLOCKED "
                f"payload_reference={reference['payload_reference_bitwise_zero']} "
                f"monitor_min={np.min(targets)} monitor_max={np.max(targets)}",
                flush=True,
            )
            return
        self._event(
            "native_mirror_reference_admissible",
            payload_reference=reference["payload_reference_bitwise_zero"],
            payload_threshold=reference["payload_threshold"],
            monitor_minimum=float(np.min(targets)),
            monitor_maximum=float(np.max(targets)),
        )
        self._run_adaptive_batches()
        self.state["post_reference"] = {
            "status": "not_run",
            "reason": "one Spark credit retained solely for verified infrastructure retry",
        }
        self.state["campaign_status"] = "COMPLETED"
        self.state["credit_balance_final"] = self._balance()
        self.state["completed_at"] = utc_now()
        self.state["complete"] = True
        self._save_state()
        print(
            "QSC_OPENQ_NATIVE_COMPLETE "
            f"spark_remaining={self.state['credit_balance_final']['spark_credits']}",
            flush=True,
        )


def main() -> None:
    args = parse_args()
    campaign = NativeMirrorCampaign(args)
    try:
        campaign.run()
    finally:
        campaign.close()


if __name__ == "__main__":
    main()
