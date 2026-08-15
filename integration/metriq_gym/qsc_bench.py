"""QSC-Bench draft adapter for Metriq Gym's local Aer provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from metriq_gym.benchmarks.benchmark import Benchmark, BenchmarkData, BenchmarkResult, BenchmarkScore

from qsc_bench.config import BenchmarkConfig, ContractConfig, ControllerConfig
from qsc_bench.runner import run_controller


@dataclass
class QSCColdStartData(BenchmarkData):
    result_payload: dict[str, Any]


class QSCColdStartResult(BenchmarkResult):
    width: int
    contract_success: bool
    acquisitions_to_contract: int
    total_quantum_executions_to_usable: int
    payload_quality: float
    monitor_values_per_acquisition: int
    local_monitor_plus_actuation_values_per_cycle: int
    traffic_scalars_to_contract: int
    controller_mutable_state_bytes: int
    controller_float_words_per_channel: float
    minimal_sufficient_cold_start_candidate: bool
    projected_acquisition_latency_seconds: float
    projected_time_to_contract_seconds: float
    simulator_runtime_seconds: float
    host_update_seconds: float
    qsc_git_worktree_dirty: bool
    qsc_code_commit: str

    def compute_score(self) -> BenchmarkScore:
        score = 0.0
        if self.contract_success and self.acquisitions_to_contract > 0:
            score = 1.0 / self.acquisitions_to_contract
        return BenchmarkScore(value=score, uncertainty=None)


class QSCColdStartBenchmark(Benchmark[QSCColdStartData, QSCColdStartResult]):
    def dispatch_handler(self, device) -> QSCColdStartData:
        device_id = str(getattr(device, "id", ""))
        if "aer" not in device_id.lower():
            raise RuntimeError(
                "QSC-Bench's draft adapter is local-Aer-only; adaptive remote "
                "dispatch requires a Metriq orchestration extension"
            )
        params = self.params
        config = BenchmarkConfig(
            development_run=True,
            widths=(int(params.width),),
            seeds=(int(params.seed),),
            shots=int(params.shots),
            reference_shots=int(params.reference_shots),
            latency_seconds=(float(params.projected_acquisition_latency_seconds),),
            contract=ContractConfig(
                monitor_rmse_tolerance=float(params.monitor_rmse_tolerance),
                consecutive_acquisitions=int(params.consecutive_acquisitions),
                payload_drop_tolerance=float(params.payload_drop_tolerance),
                max_monitor_acquisitions=int(params.max_monitor_acquisitions),
            ),
            controllers=ControllerConfig(names=(str(params.controller),)),
        )
        result = run_controller(
            config,
            n=int(params.width),
            seed=int(params.seed),
            controller_name=str(params.controller),
        )
        return QSCColdStartData(provider_job_ids=[], result_payload=result)

    def poll_handler(self, job_data, result_data, quantum_jobs) -> QSCColdStartResult:
        payload = job_data.result_payload
        success = bool(payload["contract_success"])
        acquisitions = int(payload["acquisitions_to_contract"] or 0)
        latency = float(self.params.projected_acquisition_latency_seconds)
        metadata = payload["controller_metadata"]
        return QSCColdStartResult(
            width=int(payload["width"]),
            contract_success=success,
            acquisitions_to_contract=acquisitions,
            total_quantum_executions_to_usable=int(
                payload["total_quantum_executions_to_usable"] or 0
            ),
            payload_quality=float(payload["payload_bitwise_zero_probability_at_entry"] or 0.0),
            monitor_values_per_acquisition=int(payload["width"]),
            local_monitor_plus_actuation_values_per_cycle=2 * int(payload["width"]),
            traffic_scalars_to_contract=int(payload["traffic_scalars"]),
            controller_mutable_state_bytes=int(payload["controller_mutable_state_bytes"]),
            controller_float_words_per_channel=float(
                payload["controller_mutable_float_words_per_channel"]
            ),
            minimal_sufficient_cold_start_candidate=bool(
                metadata["minimal_sufficient_cold_start_candidate"]
            ),
            projected_acquisition_latency_seconds=latency,
            projected_time_to_contract_seconds=(
                acquisitions * latency + float(payload["host_update_seconds"])
                if success
                else 0.0
            ),
            simulator_runtime_seconds=float(payload["simulator_runtime_seconds"]),
            host_update_seconds=float(payload["host_update_seconds"]),
            qsc_git_worktree_dirty=bool(payload["qsc_git_worktree_dirty"]),
            qsc_code_commit=str(payload["qsc_git_commit"] or "uncommitted"),
        )

    def estimate_resources_handler(self, device):
        raise NotImplementedError("adaptive resource estimation is not yet implemented")
