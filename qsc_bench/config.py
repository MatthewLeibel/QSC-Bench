"""Validated configuration objects for QSC-Bench."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NoiseConfig:
    one_qubit_depolarizing: float = 2.0e-4
    two_qubit_depolarizing: float = 1.0e-3
    readout_flip: float = 5.0e-3

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not 0.0 <= value < 1.0:
                raise ValueError(f"noise.{name} must be in [0, 1), got {value}")


@dataclass(frozen=True)
class DriftConfig:
    initial_shock_rms: float = 0.45
    fast_sigma: float = 2.0e-3
    fast_reversion: float = 0.05
    slow_sigma: float = 5.0e-4
    common_mode_fraction: float = 0.0

    def validate(self) -> None:
        if self.initial_shock_rms < 0 or self.fast_sigma < 0 or self.slow_sigma < 0:
            raise ValueError("drift amplitudes must be non-negative")
        if not 0.0 <= self.fast_reversion <= 1.0:
            raise ValueError("drift.fast_reversion must be in [0, 1]")
        if not 0.0 <= self.common_mode_fraction <= 1.0:
            raise ValueError("drift.common_mode_fraction must be in [0, 1]")


@dataclass(frozen=True)
class PlantConfig:
    backend: str = "aer"
    coupling_radians: float = 0.15
    nominal_angle_low: float = 1.30
    nominal_angle_high: float = 1.80
    analysis_tilt_radians: float = 0.40
    gain_low: float = 0.50
    gain_high: float = 1.20
    simulator_method: str = "density_matrix"
    payload_kind: str = "entangled_mirror"
    payload_error_amplification: float = 3.0
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    drift: DriftConfig = field(default_factory=DriftConfig)

    def validate(self) -> None:
        if self.backend not in {"aer", "analytic_ring"}:
            raise ValueError(f"unsupported plant backend: {self.backend}")
        if self.coupling_radians < 0:
            raise ValueError("plant.coupling_radians must be non-negative")
        if not 0 < self.analysis_tilt_radians < math.pi:
            raise ValueError("analysis_tilt_radians must be in (0, pi)")
        if not self.nominal_angle_low < self.nominal_angle_high:
            raise ValueError("nominal_angle_low must be less than nominal_angle_high")
        if not 0 < self.gain_low <= self.gain_high:
            raise ValueError("plant gains must satisfy 0 < gain_low <= gain_high")
        if self.simulator_method not in {
            "automatic",
            "statevector",
            "density_matrix",
            "matrix_product_state",
        }:
            raise ValueError(f"unsupported simulator method: {self.simulator_method}")
        if self.payload_kind not in {"entangled_mirror", "local_mirror"}:
            raise ValueError(f"unsupported payload kind: {self.payload_kind}")
        if self.payload_error_amplification <= 0:
            raise ValueError("payload_error_amplification must be positive")
        self.noise.validate()
        self.drift.validate()
        if self.backend == "analytic_ring" and (
            self.noise.one_qubit_depolarizing > 0
            or self.noise.two_qubit_depolarizing > 0
        ):
            raise ValueError(
                "analytic_ring supports finite-shot and symmetric readout noise exactly; "
                "its depolarizing rates must be zero"
            )
        if self.backend == "analytic_ring" and self.payload_kind != "local_mirror":
            raise ValueError("analytic_ring requires payload_kind='local_mirror'")


@dataclass(frozen=True)
class ContractConfig:
    monitor_rmse_tolerance: float = 0.025
    consecutive_acquisitions: int = 3
    payload_drop_tolerance: float = 0.03
    max_monitor_acquisitions: int = 24

    def validate(self) -> None:
        if self.monitor_rmse_tolerance <= 0:
            raise ValueError("contract.monitor_rmse_tolerance must be positive")
        if self.consecutive_acquisitions < 1:
            raise ValueError("contract.consecutive_acquisitions must be >= 1")
        if not 0 <= self.payload_drop_tolerance < 1:
            raise ValueError("contract.payload_drop_tolerance must be in [0, 1)")
        if self.max_monitor_acquisitions < self.consecutive_acquisitions:
            raise ValueError("max_monitor_acquisitions is shorter than confirmation streak")


@dataclass(frozen=True)
class ControllerConfig:
    names: tuple[str, ...] = (
        "do_nothing",
        "retained_residual",
        "diagonal_secant",
        "anderson_residual",
        "full_broyden",
        "spsa",
        "commissioned_pi",
        "dense_fd",
        "oracle",
    )
    include_oracle_in_ranking: bool = False

    def validate(self) -> None:
        allowed = {
            "do_nothing",
            "retained_residual",
            "diagonal_secant",
            "anderson_residual",
            "full_broyden",
            "spsa",
            "commissioned_pi",
            "dense_fd",
            "oracle",
        }
        unknown = set(self.names) - allowed
        if unknown:
            raise ValueError(f"unknown controllers: {sorted(unknown)}")
        if len(set(self.names)) != len(self.names):
            raise ValueError("controller names must be unique")


@dataclass(frozen=True)
class BenchmarkConfig:
    benchmark_name: str = "QSC-Bench Cold Start"
    protocol_version: str = "0.1.0-draft"
    development_run: bool = True
    widths: tuple[int, ...] = (4, 8)
    seeds: tuple[int, ...] = (20260813, 20260814)
    shots: int = 1024
    reference_shots: int = 8192
    latency_seconds: tuple[float, ...] = (1e-6, 1e-5, 1e-4, 1e-3, 1e-1)
    plant: PlantConfig = field(default_factory=PlantConfig)
    contract: ContractConfig = field(default_factory=ContractConfig)
    controllers: ControllerConfig = field(default_factory=ControllerConfig)

    def validate(self) -> None:
        if self.benchmark_name != "QSC-Bench Cold Start":
            raise ValueError("this implementation supports QSC-Bench Cold Start only")
        if not self.widths or any(n < 1 for n in self.widths):
            raise ValueError("widths must contain positive integers")
        if not self.seeds or any(seed < 0 for seed in self.seeds):
            raise ValueError("seeds must contain non-negative integers")
        if self.shots < 1 or self.reference_shots < self.shots:
            raise ValueError("reference_shots must be >= shots >= 1")
        if not self.latency_seconds or any(tau <= 0 for tau in self.latency_seconds):
            raise ValueError("latency_seconds must contain positive values")
        self.plant.validate()
        self.contract.validate()
        self.controllers.validate()
        dense_names = {"dense_fd", "full_broyden"}.intersection(
            self.controllers.names
        )
        if dense_names and max(self.widths) > 512:
            raise ValueError(
                "dense_fd and full_broyden are executable only through width 512; "
                "use structural resource projections above that ceiling"
            )
        if "dense_fd" in self.controllers.names:
            minimum_budget = max(self.widths) + 1 + self.contract.consecutive_acquisitions
            if self.contract.max_monitor_acquisitions < minimum_budget:
                raise ValueError(
                    "dense_fd requires n+1 charged commissioning acquisitions plus "
                    "the declared confirmation streak; increase max_monitor_acquisitions"
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def config_from_dict(data: dict[str, Any]) -> BenchmarkConfig:
    plant_data = _section(data, "plant")
    noise = NoiseConfig(**_section(plant_data, "noise"))
    drift = DriftConfig(**_section(plant_data, "drift"))
    plant = PlantConfig(
        **{k: v for k, v in plant_data.items() if k not in {"noise", "drift"}},
        noise=noise,
        drift=drift,
    )
    contract = ContractConfig(**_section(data, "contract"))
    controller_data = _section(data, "controllers")
    if "names" in controller_data:
        controller_data = {**controller_data, "names": tuple(controller_data["names"])}
    controllers = ControllerConfig(**controller_data)
    config = BenchmarkConfig(
        **{
            k: v
            for k, v in data.items()
            if k not in {"plant", "contract", "controllers", "widths", "seeds", "latency_seconds"}
        },
        widths=tuple(data.get("widths", BenchmarkConfig.widths)),
        seeds=tuple(data.get("seeds", BenchmarkConfig.seeds)),
        latency_seconds=tuple(data.get("latency_seconds", BenchmarkConfig.latency_seconds)),
        plant=plant,
        contract=contract,
        controllers=controllers,
    )
    config.validate()
    return config


def load_config(path: str | Path) -> BenchmarkConfig:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("benchmark configuration must be a JSON object")
    return config_from_dict(data)
