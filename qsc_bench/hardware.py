"""Small-width hardware-transfer model for QSC-Bench.

The module deliberately separates the provider-neutral scientific protocol from
provider submission.  The controlled phase offsets are commanded benchmark
disturbances.  Native QPU error is additional and uncontrolled.  This is a
hardware-in-the-loop transfer test; it is not access to a provider's private
calibration registers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import time
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error

from .controllers import (
    CommissionedPI,
    DenseFiniteDifference,
    DiagonalSecant,
    DoNothing,
    RetainedResidual,
)

FloatArray = NDArray[np.float64]
HardwareArm = Literal[
    "retained_residual",
    "diagonal_secant",
    "commissioned_pi",
    "dense_fd",
    "do_nothing",
]
HARDWARE_ARMS: tuple[HardwareArm, ...] = (
    "retained_residual",
    "diagonal_secant",
    "commissioned_pi",
    "dense_fd",
    "do_nothing",
)


@dataclass(frozen=True)
class QIHardwareProtocol:
    """Frozen-design candidates for the Tuna-9 transfer track."""

    width: int = 4
    physical_qubits: int = 9
    monitor_qubits: tuple[int, ...] = (2, 4, 5, 7)
    payload_qubits: tuple[int, ...] = (0, 1, 3, 6)
    payload_edges: tuple[tuple[int, int], ...] = ((0, 1), (1, 3), (3, 6))
    payload_ry: tuple[float, ...] = (0.82, 0.94, 1.06, 0.76)
    payload_rx: tuple[float, ...] = (0.36, -0.58, 0.71, -0.43)
    shots: int = 4096
    reference_shots: int = 8192
    acquisitions: int = 5
    base_angle: float = math.pi / 2
    initial_shock_rms: float = 0.45
    gain_low: float = 0.85
    gain_high: float = 1.15
    monitor_tolerance: float = 0.08
    required_consecutive: int = 2
    payload_bitwise_zero_threshold: float = 0.70
    payload_reference_margin: float = 0.10
    payload_error_amplification: float = 1.25
    identification_cycles: int = 1
    identification_amplitude: float = 0.150
    eta: float = 0.65
    momentum: float = 0.15
    estimator_smoothing: float = 0.50
    gain_floor: float = 0.15
    command_low: float = -3.0
    command_high: float = 3.0

    def validate(self) -> None:
        if self.width != len(self.monitor_qubits) or self.width != len(self.payload_qubits):
            raise ValueError("logical width must match both physical-qubit maps")
        if self.width != len(self.payload_ry) or self.width != len(self.payload_rx):
            raise ValueError("payload angle vectors must match logical width")
        used = self.monitor_qubits + self.payload_qubits
        if len(set(used)) != len(used):
            raise ValueError("monitor and payload qubits must be disjoint")
        if min(used) < 0 or max(used) >= self.physical_qubits:
            raise ValueError("physical-qubit map is out of range")
        if 8 in used:
            raise ValueError("Tuna-9 Q8 is excluded because the provider reports a TLS issue")
        if self.acquisitions < self.required_consecutive:
            raise ValueError("acquisition budget cannot satisfy confirmation rule")
        if self.identification_cycles != 1:
            raise ValueError("the five-acquisition hardware profile uses one retained ID move")
        if self.reference_shots < self.shots:
            raise ValueError("reference acquisition must use at least the campaign shot count")

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["scope"] = (
            "hardware-in-the-loop commanded phase restoration; not provider calibration access"
        )
        result["flat_quantity"] = "sequential ordinary full-vector acquisitions only"
        return result


@dataclass(frozen=True)
class HardwareScenario:
    seed: int
    disturbance: tuple[float, ...]
    polarity: tuple[int, ...]
    gain: tuple[float, ...]
    identification_sign: tuple[int, ...]

    def validate(self, width: int) -> None:
        fields: Sequence[Sequence[float | int]] = (
            self.disturbance,
            self.polarity,
            self.gain,
            self.identification_sign,
        )
        if any(len(values) != width for values in fields):
            raise ValueError("scenario vector does not match protocol width")

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AcquisitionScores:
    monitor_response: tuple[float, ...]
    monitor_rmse: float
    payload_bitwise_zero: float
    payload_all_zero: float


@dataclass(frozen=True)
class HardwareAcquisitionRecord:
    acquisition: int
    acquisition_kind: str
    contract_eligible: bool
    command: tuple[float, ...]
    effective_phase_error: tuple[float, ...]
    monitor_response: tuple[float, ...]
    monitor_rmse: float
    payload_bitwise_zero: float
    payload_all_zero: float
    shots_done: int
    controller_update_seconds: float


def derive_hardware_scenario(seed: int, protocol: QIHardwareProtocol) -> HardwareScenario:
    protocol.validate()
    rng = np.random.default_rng(int(seed))
    shock = rng.normal(size=protocol.width)
    shock *= protocol.initial_shock_rms / float(np.sqrt(np.mean(np.square(shock))))
    polarity = rng.choice(np.array([-1, 1], dtype=np.int8), size=protocol.width)
    gain = np.exp(
        rng.uniform(math.log(protocol.gain_low), math.log(protocol.gain_high), size=protocol.width)
    )
    identification_sign = rng.choice(
        np.array([-1, 1], dtype=np.int8), size=protocol.width
    )
    scenario = HardwareScenario(
        seed=int(seed),
        disturbance=tuple(float(value) for value in shock),
        polarity=tuple(int(value) for value in polarity),
        gain=tuple(float(value) for value in gain),
        identification_sign=tuple(int(value) for value in identification_sign),
    )
    scenario.validate(protocol.width)
    return scenario


def effective_phase_error(command: Sequence[float], scenario: HardwareScenario) -> FloatArray:
    command_array = np.asarray(command, dtype=np.float64)
    disturbance = np.asarray(scenario.disturbance, dtype=np.float64)
    polarity = np.asarray(scenario.polarity, dtype=np.float64)
    gain = np.asarray(scenario.gain, dtype=np.float64)
    if command_array.shape != disturbance.shape:
        raise ValueError("command does not match scenario width")
    return disturbance + polarity * gain * command_array


def build_qi_acquisition_circuit(
    command: Sequence[float],
    scenario: HardwareScenario,
    protocol: QIHardwareProtocol,
) -> QuantumCircuit:
    """Build the local Qiskit equivalent of one Tuna-9 cQASM acquisition."""

    protocol.validate()
    scenario.validate(protocol.width)
    phase_error = effective_phase_error(command, scenario)
    # Quantum Inspire returns full physical-qubit bitstrings.  Use the same
    # q_i -> b_i convention locally so one parser covers both environments.
    circuit = QuantumCircuit(protocol.physical_qubits, protocol.physical_qubits)

    for qubit in protocol.monitor_qubits + protocol.payload_qubits:
        circuit.reset(qubit)

    for logical, qubit in enumerate(protocol.monitor_qubits):
        circuit.h(qubit)
        circuit.rz(protocol.base_angle + float(phase_error[logical]), qubit)
        circuit.h(qubit)

    for logical, qubit in enumerate(protocol.payload_qubits):
        circuit.ry(float(protocol.payload_ry[logical]), qubit)
    for left, right in protocol.payload_edges:
        circuit.cz(left, right)
    for logical, qubit in enumerate(protocol.payload_qubits):
        circuit.rx(float(protocol.payload_rx[logical]), qubit)
        circuit.rz(protocol.payload_error_amplification * float(phase_error[logical]), qubit)
        circuit.rx(-float(protocol.payload_rx[logical]), qubit)
    for left, right in reversed(protocol.payload_edges):
        circuit.cz(left, right)
    for logical, qubit in enumerate(protocol.payload_qubits):
        circuit.ry(-float(protocol.payload_ry[logical]), qubit)

    for logical, qubit in enumerate(protocol.monitor_qubits):
        circuit.measure(qubit, qubit)
    for logical, qubit in enumerate(protocol.payload_qubits):
        circuit.measure(qubit, qubit)
    return circuit


def build_qi_cqasm(
    command: Sequence[float],
    scenario: HardwareScenario,
    protocol: QIHardwareProtocol,
) -> str:
    """Generate cQASM 3.0 using only primitive Tuna-9 gates."""

    protocol.validate()
    phase_error = effective_phase_error(command, scenario)
    lines = [
        "version 3.0",
        "",
        f"qubit[{protocol.physical_qubits}] q",
        f"bit[{protocol.physical_qubits}] b",
        "",
    ]
    for qubit in protocol.monitor_qubits + protocol.payload_qubits:
        lines.append(f"init q[{qubit}]")
    for logical, qubit in enumerate(protocol.monitor_qubits):
        lines.extend(
            [
                f"H q[{qubit}]",
                f"Rz({protocol.base_angle + float(phase_error[logical]):.16g}) q[{qubit}]",
                f"H q[{qubit}]",
            ]
        )
    for logical, qubit in enumerate(protocol.payload_qubits):
        lines.append(f"Ry({protocol.payload_ry[logical]:.16g}) q[{qubit}]")
    for left, right in protocol.payload_edges:
        lines.append(f"CZ q[{left}], q[{right}]")
    for logical, qubit in enumerate(protocol.payload_qubits):
        angle = protocol.payload_error_amplification * float(phase_error[logical])
        lines.extend(
            [
                f"Rx({protocol.payload_rx[logical]:.16g}) q[{qubit}]",
                f"Rz({angle:.16g}) q[{qubit}]",
                f"Rx({-protocol.payload_rx[logical]:.16g}) q[{qubit}]",
            ]
        )
    for left, right in reversed(protocol.payload_edges):
        lines.append(f"CZ q[{left}], q[{right}]")
    for logical, qubit in enumerate(protocol.payload_qubits):
        lines.append(f"Ry({-protocol.payload_ry[logical]:.16g}) q[{qubit}]")
    for logical, qubit in enumerate(protocol.monitor_qubits):
        lines.append(f"b[{qubit}] = measure q[{qubit}]")
    for logical, qubit in enumerate(protocol.payload_qubits):
        lines.append(f"b[{qubit}] = measure q[{qubit}]")
    return "\n".join(lines) + "\n"


def _count_key_to_int(raw_key: str) -> int:
    key = str(raw_key).strip().replace(" ", "").replace("_", "")
    if key.startswith(("0x", "0X")):
        return int(key, 16)
    if key.startswith(("0b", "0B")):
        return int(key, 2)
    if key and set(key) <= {"0", "1"}:
        return int(key, 2)
    return int(key, 10)


def score_acquisition_counts(
    counts: Mapping[str, int],
    protocol: QIHardwareProtocol,
    monitor_target: Sequence[float] | None = None,
) -> AcquisitionScores:
    total = int(sum(int(count) for count in counts.values()))
    if total <= 0:
        raise ValueError("acquisition returned no shots")
    monitor_ones = np.zeros(protocol.width, dtype=np.float64)
    payload_zero = 0
    payload_all_zero = 0
    for raw_key, raw_count in counts.items():
        value = _count_key_to_int(raw_key)
        count = int(raw_count)
        for logical, qubit in enumerate(protocol.monitor_qubits):
            monitor_ones[logical] += count * ((value >> qubit) & 1)
        payload_bits = [
            (value >> qubit) & 1 for qubit in protocol.payload_qubits
        ]
        payload_zero += count * payload_bits.count(0)
        if not any(payload_bits):
            payload_all_zero += count
    monitor_response = monitor_ones / total
    target = (
        np.full(protocol.width, 0.5, dtype=np.float64)
        if monitor_target is None
        else np.asarray(monitor_target, dtype=np.float64)
    )
    if target.shape != (protocol.width,):
        raise ValueError("monitor target does not match protocol width")
    monitor_rmse = float(np.sqrt(np.mean(np.square(monitor_response - target))))
    return AcquisitionScores(
        monitor_response=tuple(float(value) for value in monitor_response),
        monitor_rmse=monitor_rmse,
        payload_bitwise_zero=payload_zero / (total * protocol.width),
        payload_all_zero=payload_all_zero / total,
    )


def hardware_contract_met(
    trace: Sequence[AcquisitionScores], protocol: QIHardwareProtocol
) -> bool:
    if len(trace) < protocol.required_consecutive:
        return False
    tail = trace[-protocol.required_consecutive :]
    return all(
        row.monitor_rmse <= protocol.monitor_tolerance
        and row.payload_bitwise_zero >= protocol.payload_bitwise_zero_threshold
        for row in tail
    )


def make_hardware_noise_model(
    *,
    one_qubit_depolarizing: float = 0.004,
    two_qubit_depolarizing: float = 0.020,
    readout_flip: float = 0.025,
) -> NoiseModel:
    model = NoiseModel()
    if one_qubit_depolarizing:
        one = depolarizing_error(one_qubit_depolarizing, 1)
        model.add_all_qubit_quantum_error(one, ["h", "rx", "ry", "rz"])
    if two_qubit_depolarizing:
        model.add_all_qubit_quantum_error(depolarizing_error(two_qubit_depolarizing, 2), ["cz"])
    if readout_flip:
        p = readout_flip
        model.add_all_qubit_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]))
    return model


def reference_hardware_scenario(protocol: QIHardwareProtocol) -> HardwareScenario:
    """Return the fixed no-disturbance scenario used to establish the QPU target."""

    protocol.validate()
    return HardwareScenario(
        seed=0,
        disturbance=(0.0,) * protocol.width,
        polarity=(1,) * protocol.width,
        gain=(1.0,) * protocol.width,
        identification_sign=(1,) * protocol.width,
    )


def reference_payload_threshold(
    reference_bitwise_zero: float, protocol: QIHardwareProtocol
) -> float:
    """Apply the frozen absolute floor and relative-to-reference margin rule."""

    if not 0.0 <= reference_bitwise_zero <= 1.0:
        raise ValueError("reference payload score must be a probability")
    return max(
        protocol.payload_bitwise_zero_threshold,
        reference_bitwise_zero - protocol.payload_reference_margin,
    )


def _record_satisfies_contract(
    record: HardwareAcquisitionRecord,
    protocol: QIHardwareProtocol,
    payload_threshold: float,
) -> bool:
    return (
        record.contract_eligible
        and record.monitor_rmse <= protocol.monitor_tolerance
        and record.payload_bitwise_zero >= payload_threshold
    )


def hardware_contract_entry(
    trace: Sequence[HardwareAcquisitionRecord],
    protocol: QIHardwareProtocol,
    payload_threshold: float | None = None,
) -> int | None:
    """Return the one-indexed acquisition at first confirmed ordinary entry."""

    threshold = (
        protocol.payload_bitwise_zero_threshold
        if payload_threshold is None
        else float(payload_threshold)
    )
    required = protocol.required_consecutive
    for stop in range(required, len(trace) + 1):
        window = trace[stop - required : stop]
        if all(_record_satisfies_contract(row, protocol, threshold) for row in window):
            return stop
    return None


def hardware_contract_at_deadline(
    trace: Sequence[HardwareAcquisitionRecord],
    protocol: QIHardwareProtocol,
    payload_threshold: float | None = None,
) -> bool:
    threshold = (
        protocol.payload_bitwise_zero_threshold
        if payload_threshold is None
        else float(payload_threshold)
    )
    if len(trace) < protocol.required_consecutive:
        return False
    tail = trace[-protocol.required_consecutive :]
    return all(_record_satisfies_contract(row, protocol, threshold) for row in tail)


def _make_hardware_controller(
    arm: HardwareArm,
    seed: int,
    protocol: QIHardwareProtocol,
    scenario: HardwareScenario,
):
    common = {
        "n": protocol.width,
        "seed": seed + 10_000,
        "lo": protocol.command_low,
        "hi": protocol.command_high,
    }
    if arm == "retained_residual":
        controller = RetainedResidual(
            **common,
            eta=protocol.eta,
            momentum=protocol.momentum,
            estimator_smoothing=protocol.estimator_smoothing,
            gain_floor=protocol.gain_floor,
            identification_amplitude=protocol.identification_amplitude,
            identification_cycles=protocol.identification_cycles,
        )
        controller.id_sign[:] = np.asarray(scenario.identification_sign, dtype=np.int8)
        return controller
    if arm == "diagonal_secant":
        controller = DiagonalSecant(
            **common,
            identification_amplitude=protocol.identification_amplitude,
        )
        controller.id_sign[:] = np.asarray(scenario.identification_sign, dtype=np.int8)
        return controller
    if arm == "commissioned_pi":
        return CommissionedPI(**common)
    if arm == "dense_fd":
        return DenseFiniteDifference(**common)
    if arm == "do_nothing":
        return DoNothing(**common)
    raise ValueError(f"unsupported hardware arm: {arm}")


def _structural_minimum_to_confirm(arm: HardwareArm, protocol: QIHardwareProtocol) -> int:
    if arm == "commissioned_pi":
        return 2 + protocol.required_consecutive
    if arm == "dense_fd":
        return protocol.width + 1 + protocol.required_consecutive
    return protocol.required_consecutive


def run_hardware_dry_run(
    *,
    arm: HardwareArm,
    seed: int,
    protocol: QIHardwareProtocol | None = None,
    noise_model: NoiseModel | None = None,
    monitor_target: Sequence[float] | None = None,
    payload_threshold: float | None = None,
) -> dict[str, Any]:
    """Run the exact five-acquisition hardware protocol locally in Aer."""

    protocol = protocol or QIHardwareProtocol()
    protocol.validate()
    if arm not in HARDWARE_ARMS:
        raise ValueError(f"unsupported hardware arm: {arm}")
    scenario = derive_hardware_scenario(seed, protocol)
    controller = _make_hardware_controller(arm, seed, protocol, scenario)
    backend = AerSimulator(method="density_matrix", noise_model=noise_model)
    target = (
        np.full(protocol.width, 0.5, dtype=np.float64)
        if monitor_target is None
        else np.asarray(monitor_target, dtype=np.float64)
    )
    if target.shape != (protocol.width,):
        raise ValueError("monitor target does not match protocol width")
    threshold = (
        protocol.payload_bitwise_zero_threshold
        if payload_threshold is None
        else float(payload_threshold)
    )
    trace: list[HardwareAcquisitionRecord] = []
    pi_code = np.asarray(scenario.identification_sign, dtype=np.float64)
    pi_minus: FloatArray | None = None
    dense_base: FloatArray | None = None
    dense_probes: list[FloatArray] = []

    for acquisition in range(protocol.acquisitions):
        if arm == "commissioned_pi" and acquisition == 0:
            command = -protocol.identification_amplitude * pi_code
            kind = "coded_probe_minus"
            eligible = False
        elif arm == "commissioned_pi" and acquisition == 1:
            command = protocol.identification_amplitude * pi_code
            kind = "coded_probe_plus"
            eligible = False
        elif arm == "dense_fd" and acquisition == 0:
            command = np.zeros(protocol.width, dtype=np.float64)
            kind = "dense_base"
            eligible = False
        elif arm == "dense_fd":
            command = np.zeros(protocol.width, dtype=np.float64)
            command[acquisition - 1] = protocol.identification_amplitude
            kind = f"dense_probe_{acquisition - 1}"
            eligible = False
        else:
            command = np.asarray(controller.u, dtype=np.float64).copy()
            kind = "ordinary"
            eligible = True

        circuit = build_qi_acquisition_circuit(command, scenario, protocol)
        counts = backend.run(
            circuit,
            shots=protocol.shots,
            seed_simulator=int(seed * 100 + acquisition),
        ).result().get_counts()
        scores = score_acquisition_counts(counts, protocol, target)
        response = np.asarray(scores.monitor_response, dtype=np.float64)
        started = time.perf_counter()
        if arm == "commissioned_pi":
            if acquisition == 0:
                pi_minus = response.copy()
            elif acquisition == 1:
                if pi_minus is None:
                    raise RuntimeError("missing commissioned-PI minus probe")
                controller.set_commissioning(
                    pi_minus,
                    response,
                    pi_code,
                    protocol.identification_amplitude,
                )
                controller.update(0.5 * (pi_minus + response), target)
            else:
                controller.update(response, target)
        elif arm == "dense_fd":
            if acquisition == 0:
                dense_base = response.copy()
            else:
                dense_probes.append(response.copy())
                if acquisition == protocol.width:
                    if dense_base is None:
                        raise RuntimeError("missing dense finite-difference base frame")
                    controller.set_commissioning(
                        dense_base,
                        dense_probes,
                        protocol.identification_amplitude,
                    )
                    controller.update(dense_base, target)
        else:
            controller.update(response, target)
        update_seconds = time.perf_counter() - started
        trace.append(
            HardwareAcquisitionRecord(
                acquisition=acquisition + 1,
                acquisition_kind=kind,
                contract_eligible=eligible,
                command=tuple(float(value) for value in command),
                effective_phase_error=tuple(
                    float(value) for value in effective_phase_error(command, scenario)
                ),
                monitor_response=scores.monitor_response,
                monitor_rmse=scores.monitor_rmse,
                payload_bitwise_zero=scores.payload_bitwise_zero,
                payload_all_zero=scores.payload_all_zero,
                shots_done=protocol.shots,
                controller_update_seconds=update_seconds,
            )
        )

    entry = hardware_contract_entry(trace, protocol, threshold)
    return {
        "schema_version": "qsc-hardware-transfer-v1-development",
        "arm": arm,
        "seed": int(seed),
        "protocol": protocol.public_dict(),
        "scenario": scenario.public_dict(),
        "scenario_sha256": hashlib.sha256(
            json.dumps(scenario.public_dict(), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "monitor_target": [float(value) for value in target],
        "payload_threshold": threshold,
        "contract_entry_acquisition": entry,
        "contract_success": entry is not None,
        "contract_at_deadline": hardware_contract_at_deadline(trace, protocol, threshold),
        "structural_minimum_acquisitions_to_confirm": _structural_minimum_to_confirm(
            arm, protocol
        ),
        "ordinary_acquisitions": sum(row.contract_eligible for row in trace),
        "discarded_probe_acquisitions": sum(not row.contract_eligible for row in trace),
        "controller_metadata": asdict(controller.metadata),
        "trace": [asdict(row) for row in trace],
        "final_command": [float(value) for value in controller.u],
        "total_controller_update_seconds": sum(
            row.controller_update_seconds for row in trace
        ),
    }


def run_retained_hardware_dry_run(
    *,
    seed: int,
    protocol: QIHardwareProtocol | None = None,
    noise_model: NoiseModel | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for the retained-residual development arm."""

    return run_hardware_dry_run(
        arm="retained_residual",
        seed=seed,
        protocol=protocol,
        noise_model=noise_model,
    )
