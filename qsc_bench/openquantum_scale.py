"""High-width OpenQuantum hardware-transfer protocol for QSC-Bench.

This module specifies the scientific plant and controller state machine.  It
does not authenticate with or submit to OpenQuantum.  The controlled offsets
are explicit benchmark commands embedded in the circuit.  Native QPU error is
additional and uncontrolled; no provider-private calibration register is read
or written.

The largest paired-payload track uses every qubit of Rigetti Cepheus-1-108Q: 54 monitor
qubits and 54 disjoint payload qubits.  It therefore has 54 controlled
channels, not 108 controlled channels.
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

from .controllers import CommissionedPI, DiagonalSecant, DoNothing, RetainedResidual
from .hardware import HardwareScenario, effective_phase_error


FloatArray = NDArray[np.float64]
OpenQuantumArm = Literal[
    "retained_residual",
    "diagonal_secant",
    "commissioned_pi",
    "do_nothing",
]
OPENQUANTUM_ARMS: tuple[OpenQuantumArm, ...] = (
    "retained_residual",
    "diagonal_secant",
    "commissioned_pi",
    "do_nothing",
)

CEPHEUS_BACKEND = "rigetti:cepheus-1-108q"
CEPHEUS_MAX_QUBITS = 108

# Each pair is a published native CZ edge in the live backend constraint map.
_PAYLOAD_MATCHINGS: dict[int, tuple[tuple[int, int], ...]] = {
    18: (
        (35, 26),
        (18, 19),
        (27, 28),
        (34, 25),
        (33, 24),
        (32, 23),
        (20, 21),
        (29, 30),
        (22, 31),
    ),
    54: (
        (54, 55),
        (56, 57),
        (58, 59),
        (60, 61),
        (62, 71),
        (63, 64),
        (65, 66),
        (67, 68),
        (69, 70),
        (72, 73),
        (74, 75),
        (76, 77),
        (78, 79),
        (80, 89),
        (81, 82),
        (83, 84),
        (85, 86),
        (87, 88),
        (90, 91),
        (99, 100),
        (92, 93),
        (101, 102),
        (98, 97),
        (107, 106),
        (96, 95),
        (105, 104),
        (94, 103),
    ),
    48: (
        (48, 49),
        (50, 51),
        (52, 53),
        (54, 55),
        (56, 57),
        (58, 59),
        (60, 61),
        (62, 71),
        (63, 64),
        (65, 66),
        (67, 68),
        (69, 70),
        (72, 73),
        (74, 75),
        (76, 77),
        (78, 79),
        (80, 89),
        (88, 87),
        (81, 82),
        (90, 91),
        (83, 84),
        (92, 93),
        (94, 85),
        (86, 95),
    ),
    42: (
        (42, 43),
        (44, 53),
        (45, 46),
        (47, 48),
        (49, 50),
        (51, 52),
        (54, 55),
        (80, 71),
        (62, 61),
        (70, 69),
        (79, 78),
        (60, 59),
        (68, 67),
        (77, 76),
        (58, 57),
        (56, 65),
        (66, 75),
        (64, 63),
        (72, 73),
        (81, 82),
        (74, 83),
    ),
    36: (
        (36, 37),
        (38, 39),
        (40, 41),
        (42, 43),
        (44, 53),
        (71, 62),
        (70, 61),
        (52, 51),
        (69, 60),
        (68, 59),
        (50, 49),
        (67, 58),
        (66, 57),
        (48, 47),
        (65, 56),
        (64, 55),
        (46, 45),
        (54, 63),
    ),
    30: (
        (30, 31),
        (32, 33),
        (34, 35),
        (36, 37),
        (38, 39),
        (40, 41),
        (42, 43),
        (44, 53),
        (52, 51),
        (45, 46),
        (54, 55),
        (47, 48),
        (56, 57),
        (49, 50),
        (58, 59),
    ),
    24: (
        (24, 25),
        (26, 35),
        (44, 43),
        (34, 33),
        (42, 41),
        (32, 31),
        (40, 39),
        (30, 29),
        (38, 37),
        (47, 46),
        (28, 27),
        (36, 45),
    ),
}

_PAYLOAD_RY_CYCLE = (0.82, 0.94, 1.06, 0.76)
_PAYLOAD_RX_CYCLE = (0.36, -0.58, 0.71, -0.43)


@dataclass(frozen=True)
class OpenQuantumScaleProtocol:
    """Frozen high-width commanded-phase hardware-transfer protocol."""

    width: int
    physical_qubits: int
    monitor_qubits: tuple[int, ...]
    payload_qubits: tuple[int, ...]
    payload_edges: tuple[tuple[int, int], ...]
    payload_kind: str = "paired_cz_mirror"
    shots: int = 2048
    reference_shots: int = 2048
    acquisitions: int = 4
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

    @property
    def payload_ry(self) -> tuple[float, ...]:
        return tuple(_PAYLOAD_RY_CYCLE[i % len(_PAYLOAD_RY_CYCLE)] for i in range(self.width))

    @property
    def payload_rx(self) -> tuple[float, ...]:
        return tuple(_PAYLOAD_RX_CYCLE[i % len(_PAYLOAD_RX_CYCLE)] for i in range(self.width))

    def validate(self) -> None:
        if self.width not in _PAYLOAD_MATCHINGS:
            raise ValueError("width has no frozen native-edge payload matching")
        if self.physical_qubits != 2 * self.width:
            raise ValueError("physical width must equal monitor plus disjoint payload width")
        if self.physical_qubits > CEPHEUS_MAX_QUBITS:
            raise ValueError("protocol exceeds the live Cepheus qubit limit")
        if (
            len(self.monitor_qubits) != self.width
            or len(set(self.monitor_qubits)) != self.width
        ):
            raise ValueError("monitor map must contain one unique physical qubit per channel")
        if (
            len(self.payload_qubits) != self.width
            or len(set(self.payload_qubits)) != self.width
        ):
            raise ValueError("payload map must contain one unique physical qubit per channel")
        used = set(self.monitor_qubits) | set(self.payload_qubits)
        if set(self.monitor_qubits) & set(self.payload_qubits):
            raise ValueError("monitor and payload maps must be disjoint")
        if used != set(range(self.physical_qubits)):
            raise ValueError("monitor and payload maps must use every declared physical qubit")
        if self.payload_kind == "paired_cz_mirror":
            if self.monitor_qubits != tuple(range(self.width)):
                raise ValueError(
                    "paired-CZ monitor map differs from its frozen low-index block"
                )
            if self.payload_qubits != tuple(range(self.width, 2 * self.width)):
                raise ValueError(
                    "paired-CZ payload map differs from its frozen high-index block"
                )
            if self.payload_edges != _PAYLOAD_MATCHINGS[self.width]:
                raise ValueError("payload matching differs from the frozen native-edge map")
            flattened = tuple(qubit for edge in self.payload_edges for qubit in edge)
            if len(flattened) != self.width or set(flattened) != set(self.payload_qubits):
                raise ValueError("payload edges must be a disjoint perfect matching")
        elif self.payload_kind == "local_mirror":
            if self.monitor_qubits != tuple(range(self.width)):
                raise ValueError(
                    "local-mirror monitor map differs from its frozen low-index block"
                )
            if self.payload_qubits != tuple(range(self.width, 2 * self.width)):
                raise ValueError(
                    "local-mirror payload map differs from its frozen high-index block"
                )
            if self.payload_edges:
                raise ValueError("local-mirror payload must not contain two-qubit edges")
        elif self.payload_kind == "native_ramsey_mirror":
            if self.payload_edges:
                raise ValueError("native Ramsey mirror must not contain two-qubit edges")
        elif self.payload_kind == "native_single_rx":
            if self.payload_edges:
                raise ValueError("native single-Rx payload must not contain two-qubit edges")
        else:
            raise ValueError("unknown payload kind")
        if self.acquisitions != 4 or self.required_consecutive != 2:
            raise ValueError("the extension freezes a four-read, two-frame contract")
        if self.identification_cycles != 1:
            raise ValueError("the extension freezes one retained identification move")
        if self.reference_shots < self.shots:
            raise ValueError("reference shots must not be below campaign shots")

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["payload_ry"] = list(self.payload_ry)
        result["payload_rx"] = list(self.payload_rx)
        result["backend_short_code"] = CEPHEUS_BACKEND
        result["scope"] = (
            "hardware-in-the-loop commanded phase restoration under native QPU noise; "
            "not provider calibration access"
        )
        result["flat_quantity"] = "sequential full-vector acquisitions only"
        return result


def cepheus_protocol(width: int, *, shots: int = 2048, reference_shots: int = 2048) -> OpenQuantumScaleProtocol:
    """Construct one of the two frozen native-layout tracks."""

    if width not in _PAYLOAD_MATCHINGS:
        raise ValueError("width has no frozen native-edge payload matching")
    protocol = OpenQuantumScaleProtocol(
        width=width,
        physical_qubits=2 * width,
        monitor_qubits=tuple(range(width)),
        payload_qubits=tuple(range(width, 2 * width)),
        payload_edges=_PAYLOAD_MATCHINGS[width],
        shots=shots,
        reference_shots=reference_shots,
    )
    protocol.validate()
    return protocol


def cepheus_local_protocol(
    width: int, *, shots: int = 2048, reference_shots: int = 2048
) -> OpenQuantumScaleProtocol:
    """Construct a no-CZ local-mirror workload on disjoint monitor/payload qubits."""

    if width not in _PAYLOAD_MATCHINGS:
        raise ValueError("width has no frozen physical layout")
    protocol = OpenQuantumScaleProtocol(
        width=width,
        physical_qubits=2 * width,
        monitor_qubits=tuple(range(width)),
        payload_qubits=tuple(range(width, 2 * width)),
        payload_edges=(),
        payload_kind="local_mirror",
        shots=shots,
        reference_shots=reference_shots,
    )
    protocol.validate()
    return protocol


def cepheus_native_mirror_protocol(
    *, shots: int = 2048, reference_shots: int = 2048
) -> OpenQuantumScaleProtocol:
    """Construct the frozen 96-qubit informative-map native-mirror protocol.

    A completed pre-confirmation characterization placed physical monitor
    qubits 16, 40, and 43 at near-flat response extrema.  The mapping replaces
    those three monitor sites with the three strongest observed, disjoint
    payload-reference sites.  The excluded sites remain in the physical
    allocation as payload qubits, so the circuit still uses exactly 96 qubits.
    """

    excluded_monitors = {16, 40, 43}
    replacement_monitors = (71, 78, 85)
    monitor_qubits = tuple(
        [qubit for qubit in range(48) if qubit not in excluded_monitors]
        + list(replacement_monitors)
    )
    payload_qubits = tuple(
        qubit for qubit in range(96) if qubit not in set(monitor_qubits)
    )
    protocol = OpenQuantumScaleProtocol(
        width=48,
        physical_qubits=96,
        monitor_qubits=monitor_qubits,
        payload_qubits=payload_qubits,
        payload_edges=(),
        payload_kind="native_ramsey_mirror",
        shots=shots,
        reference_shots=reference_shots,
        payload_bitwise_zero_threshold=0.80,
        payload_reference_margin=0.10,
        payload_error_amplification=3.0,
    )
    protocol.validate()
    return protocol


def cepheus_single_rx_protocol(
    *, shots: int = 2048, reference_shots: int = 2048
) -> OpenQuantumScaleProtocol:
    """Construct the frozen 96-qubit informative-map single-Rx protocol."""

    base = cepheus_native_mirror_protocol(shots=shots, reference_shots=reference_shots)
    protocol = OpenQuantumScaleProtocol(
        width=base.width,
        physical_qubits=base.physical_qubits,
        monitor_qubits=base.monitor_qubits,
        payload_qubits=base.payload_qubits,
        payload_edges=(),
        payload_kind="native_single_rx",
        shots=shots,
        reference_shots=reference_shots,
        payload_bitwise_zero_threshold=0.80,
        payload_reference_margin=0.10,
        payload_error_amplification=3.0,
    )
    protocol.validate()
    return protocol


def derive_openquantum_scenario(seed: int, protocol: OpenQuantumScaleProtocol) -> HardwareScenario:
    protocol.validate()
    rng = np.random.default_rng(int(seed))
    shock = rng.normal(size=protocol.width)
    shock *= protocol.initial_shock_rms / float(np.sqrt(np.mean(np.square(shock))))
    polarity = rng.choice(np.array([-1, 1], dtype=np.int8), size=protocol.width)
    gain = np.exp(
        rng.uniform(math.log(protocol.gain_low), math.log(protocol.gain_high), size=protocol.width)
    )
    identification_sign = rng.choice(np.array([-1, 1], dtype=np.int8), size=protocol.width)
    scenario = HardwareScenario(
        seed=int(seed),
        disturbance=tuple(float(value) for value in shock),
        polarity=tuple(int(value) for value in polarity),
        gain=tuple(float(value) for value in gain),
        identification_sign=tuple(int(value) for value in identification_sign),
    )
    scenario.validate(protocol.width)
    return scenario


def reference_openquantum_scenario(protocol: OpenQuantumScaleProtocol) -> HardwareScenario:
    protocol.validate()
    return HardwareScenario(
        seed=0,
        disturbance=(0.0,) * protocol.width,
        polarity=(1,) * protocol.width,
        gain=(1.0,) * protocol.width,
        identification_sign=(1,) * protocol.width,
    )


def _qasm_angle(value: float) -> str:
    return f"{float(value):.16g}"


def build_openquantum_qasm(
    command: Sequence[float],
    scenario: HardwareScenario,
    protocol: OpenQuantumScaleProtocol,
) -> str:
    """Render one shallow OpenQASM 2.0 monitor-plus-payload acquisition."""

    protocol.validate()
    scenario.validate(protocol.width)
    phase_error = effective_phase_error(command, scenario)
    lines = [
        "OPENQASM 2.0;",
        'include "qelib1.inc";',
        "",
        f"qreg q[{protocol.physical_qubits}];",
        f"creg c[{protocol.physical_qubits}];",
        "",
        "// Component-resolved Ramsey monitor block.",
    ]
    for logical, qubit in enumerate(protocol.monitor_qubits):
        lines.extend(
            (
                f"h q[{qubit}];",
                f"rz({_qasm_angle(protocol.base_angle + phase_error[logical])}) q[{qubit}];",
                f"h q[{qubit}];",
            )
        )
    lines.append("")
    lines.append("// Disjoint shallow mirror payload block.")
    if protocol.payload_kind == "native_ramsey_mirror":
        for logical, qubit in enumerate(protocol.payload_qubits):
            lines.extend(
                (
                    f"rx({_qasm_angle(math.pi / 2.0)}) q[{qubit}];",
                    f"rz({_qasm_angle(protocol.payload_error_amplification * phase_error[logical])}) q[{qubit}];",
                    f"rx({_qasm_angle(-math.pi / 2.0)}) q[{qubit}];",
                )
            )
    elif protocol.payload_kind == "native_single_rx":
        for logical, qubit in enumerate(protocol.payload_qubits):
            lines.append(
                f"rx({_qasm_angle(protocol.payload_error_amplification * phase_error[logical])}) q[{qubit}];"
            )
    else:
        for logical, qubit in enumerate(protocol.payload_qubits):
            lines.append(f"ry({_qasm_angle(protocol.payload_ry[logical])}) q[{qubit}];")
        for left, right in protocol.payload_edges:
            lines.append(f"cz q[{left}],q[{right}];")
        for logical, qubit in enumerate(protocol.payload_qubits):
            lines.extend(
                (
                    f"rx({_qasm_angle(protocol.payload_rx[logical])}) q[{qubit}];",
                    f"rz({_qasm_angle(protocol.payload_error_amplification * phase_error[logical])}) q[{qubit}];",
                    f"rx({_qasm_angle(-protocol.payload_rx[logical])}) q[{qubit}];",
                )
            )
        for left, right in reversed(protocol.payload_edges):
            lines.append(f"cz q[{left}],q[{right}];")
        for logical, qubit in enumerate(protocol.payload_qubits):
            lines.append(f"ry({_qasm_angle(-protocol.payload_ry[logical])}) q[{qubit}];")
    lines.extend(("", "measure q -> c;", ""))
    return "\n".join(lines)


def render_openquantum_reference_qasm(protocol: OpenQuantumScaleProtocol) -> str:
    return build_openquantum_qasm(
        [0.0] * protocol.width,
        reference_openquantum_scenario(protocol),
        protocol,
    )


def _count_key_to_int(raw_key: str) -> int:
    key = str(raw_key).strip().replace(" ", "").replace("_", "")
    if key.startswith(("0x", "0X")):
        return int(key, 16)
    if key.startswith(("0b", "0B")):
        return int(key, 2)
    if key and set(key) <= {"0", "1"}:
        return int(key, 2)
    return int(key, 10)


@dataclass(frozen=True)
class OpenQuantumScores:
    monitor_response: tuple[float, ...]
    monitor_rmse: float
    payload_bitwise_zero: float
    payload_all_zero: float
    shots_done: int


def score_openquantum_counts(
    counts: Mapping[str, int],
    protocol: OpenQuantumScaleProtocol,
    monitor_target: Sequence[float] | None = None,
) -> OpenQuantumScores:
    protocol.validate()
    total = int(sum(int(value) for value in counts.values()))
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
        payload_bits = [(value >> qubit) & 1 for qubit in protocol.payload_qubits]
        payload_zero += count * payload_bits.count(0)
        if not any(payload_bits):
            payload_all_zero += count
    response = monitor_ones / total
    target = (
        np.full(protocol.width, 0.5, dtype=np.float64)
        if monitor_target is None
        else np.asarray(monitor_target, dtype=np.float64)
    )
    if target.shape != (protocol.width,):
        raise ValueError("monitor target does not match protocol width")
    return OpenQuantumScores(
        monitor_response=tuple(float(value) for value in response),
        monitor_rmse=float(np.sqrt(np.mean(np.square(response - target)))),
        payload_bitwise_zero=payload_zero / (total * protocol.width),
        payload_all_zero=payload_all_zero / total,
        shots_done=total,
    )


def reference_payload_threshold(reference_score: float, protocol: OpenQuantumScaleProtocol) -> float:
    if not 0.0 <= reference_score <= 1.0:
        raise ValueError("reference payload score must be a probability")
    return max(
        protocol.payload_bitwise_zero_threshold,
        float(reference_score) - protocol.payload_reference_margin,
    )


def _make_controller(
    arm: OpenQuantumArm,
    seed: int,
    scenario: HardwareScenario,
    protocol: OpenQuantumScaleProtocol,
):
    common = {
        "n": protocol.width,
        "seed": int(seed) + 10_000,
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
    if arm == "do_nothing":
        return DoNothing(**common)
    raise ValueError(f"unsupported OpenQuantum arm: {arm}")


@dataclass(frozen=True)
class AcquisitionRequest:
    acquisition: int
    acquisition_kind: str
    contract_eligible: bool
    command: tuple[float, ...]
    effective_phase_error: tuple[float, ...]
    qasm: str
    qasm_sha256: str


class OpenQuantumAdaptiveRun:
    """Pure controller state machine used by both rehearsal and live orchestration."""

    def __init__(
        self,
        *,
        arm: OpenQuantumArm,
        seed: int,
        monitor_target: Sequence[float],
        payload_reference_bitwise_zero: float,
        protocol: OpenQuantumScaleProtocol,
    ):
        if arm not in OPENQUANTUM_ARMS:
            raise ValueError(f"unsupported OpenQuantum arm: {arm}")
        protocol.validate()
        target = np.asarray(monitor_target, dtype=np.float64)
        if target.shape != (protocol.width,):
            raise ValueError("monitor target does not match protocol width")
        self.arm = arm
        self.seed = int(seed)
        self.protocol = protocol
        self.scenario = derive_openquantum_scenario(seed, protocol)
        self.controller = _make_controller(arm, seed, self.scenario, protocol)
        self.monitor_target = target
        self.payload_reference_bitwise_zero = float(payload_reference_bitwise_zero)
        self.payload_threshold = reference_payload_threshold(
            self.payload_reference_bitwise_zero, protocol
        )
        self.trace: list[dict[str, Any]] = []
        self._pi_code = np.asarray(self.scenario.identification_sign, dtype=np.float64)
        self._pi_minus: FloatArray | None = None

    @property
    def complete(self) -> bool:
        return len(self.trace) >= self.protocol.acquisitions

    def next_request(self) -> AcquisitionRequest:
        if self.complete:
            raise RuntimeError("adaptive run has already reached its acquisition budget")
        index = len(self.trace)
        if self.arm == "commissioned_pi" and index == 0:
            command = -self.protocol.identification_amplitude * self._pi_code
            kind = "coded_probe_minus"
            eligible = False
        elif self.arm == "commissioned_pi" and index == 1:
            command = self.protocol.identification_amplitude * self._pi_code
            kind = "coded_probe_plus"
            eligible = False
        else:
            command = np.asarray(self.controller.u, dtype=np.float64).copy()
            kind = "ordinary"
            eligible = True
        phase_error = effective_phase_error(command, self.scenario)
        qasm = build_openquantum_qasm(command, self.scenario, self.protocol)
        return AcquisitionRequest(
            acquisition=index + 1,
            acquisition_kind=kind,
            contract_eligible=eligible,
            command=tuple(float(value) for value in command),
            effective_phase_error=tuple(float(value) for value in phase_error),
            qasm=qasm,
            qasm_sha256=hashlib.sha256(qasm.encode("utf-8")).hexdigest(),
        )

    def consume(
        self,
        counts: Mapping[str, int],
        *,
        job_metadata: Mapping[str, Any] | None = None,
        controller_update_seconds_override: float | None = None,
    ) -> dict[str, Any]:
        request = self.next_request()
        scores = score_openquantum_counts(counts, self.protocol, self.monitor_target)
        response = np.asarray(scores.monitor_response, dtype=np.float64)
        started = time.perf_counter()
        index = request.acquisition - 1
        if self.arm == "commissioned_pi":
            if index == 0:
                self._pi_minus = response.copy()
            elif index == 1:
                if self._pi_minus is None:
                    raise RuntimeError("missing commissioned-PI minus probe")
                self.controller.set_commissioning(
                    self._pi_minus,
                    response,
                    self._pi_code,
                    self.protocol.identification_amplitude,
                )
                self.controller.update(0.5 * (self._pi_minus + response), self.monitor_target)
            else:
                self.controller.update(response, self.monitor_target)
        else:
            self.controller.update(response, self.monitor_target)
        measured_update = time.perf_counter() - started
        update_seconds = (
            measured_update
            if controller_update_seconds_override is None
            else float(controller_update_seconds_override)
        )
        row = {
            "acquisition": request.acquisition,
            "acquisition_kind": request.acquisition_kind,
            "contract_eligible": request.contract_eligible,
            "command": list(request.command),
            "effective_phase_error": list(request.effective_phase_error),
            "qasm_sha256": request.qasm_sha256,
            "monitor_response": list(scores.monitor_response),
            "monitor_rmse": scores.monitor_rmse,
            "payload_bitwise_zero": scores.payload_bitwise_zero,
            "payload_all_zero": scores.payload_all_zero,
            "shots_done": scores.shots_done,
            "controller_update_seconds": update_seconds,
            "job": dict(job_metadata or {}),
        }
        self.trace.append(row)
        return row

    def contract_entry(self) -> int | None:
        required = self.protocol.required_consecutive
        for stop in range(required, len(self.trace) + 1):
            window = self.trace[stop - required : stop]
            if all(
                row["contract_eligible"]
                and row["monitor_rmse"] <= self.protocol.monitor_tolerance
                and row["payload_bitwise_zero"] >= self.payload_threshold
                for row in window
            ):
                return stop
        return None

    def result(self) -> dict[str, Any]:
        if not self.complete:
            raise RuntimeError("cannot finalize an incomplete adaptive run")
        entry = self.contract_entry()
        return {
            "schema_version": "qsc-openquantum-scale-run-v1",
            "arm": self.arm,
            "seed": self.seed,
            "protocol": self.protocol.public_dict(),
            "scenario": self.scenario.public_dict(),
            "scenario_sha256": hashlib.sha256(
                json.dumps(self.scenario.public_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "monitor_target": [float(value) for value in self.monitor_target],
            "payload_reference_bitwise_zero": self.payload_reference_bitwise_zero,
            "payload_threshold": self.payload_threshold,
            "contract_entry_acquisition": entry,
            "contract_success": entry is not None,
            "contract_at_deadline": entry is not None and all(
                row["contract_eligible"]
                and row["monitor_rmse"] <= self.protocol.monitor_tolerance
                and row["payload_bitwise_zero"] >= self.payload_threshold
                for row in self.trace[-self.protocol.required_consecutive :]
            ),
            "structural_minimum_acquisitions_to_confirm": (
                2 + self.protocol.required_consecutive
                if self.arm == "commissioned_pi"
                else self.protocol.required_consecutive
            ),
            "dense_fd_structural_minimum_acquisitions_to_confirm": (
                self.protocol.width + 1 + self.protocol.required_consecutive
            ),
            "controller_metadata": asdict(self.controller.metadata),
            "controller_mutable_state_bytes": self.controller.mutable_state_bytes(),
            "controller_float_words_per_channel": self.controller.mutable_float_words_per_channel(),
            "trace": list(self.trace),
            "final_command": [float(value) for value in self.controller.u],
            "total_controller_update_seconds": sum(
                float(row["controller_update_seconds"]) for row in self.trace
            ),
        }


def _rotation_x(angle: float) -> np.ndarray:
    c = math.cos(angle / 2.0)
    s = math.sin(angle / 2.0)
    return np.asarray([[c, -1j * s], [-1j * s, c]], dtype=np.complex128)


def _rotation_y(angle: float) -> np.ndarray:
    c = math.cos(angle / 2.0)
    s = math.sin(angle / 2.0)
    return np.asarray([[c, -s], [s, c]], dtype=np.complex128)


def _rotation_z(angle: float) -> np.ndarray:
    return np.asarray(
        [[np.exp(-0.5j * angle), 0.0], [0.0, np.exp(0.5j * angle)]],
        dtype=np.complex128,
    )


def _apply_single(state: np.ndarray, gate: np.ndarray, qubit: int) -> np.ndarray:
    operator = np.kron(gate, np.eye(2)) if qubit == 0 else np.kron(np.eye(2), gate)
    return operator @ state


def _payload_pair_probabilities(
    logical_left: int,
    logical_right: int,
    errors: FloatArray,
    protocol: OpenQuantumScaleProtocol,
) -> tuple[float, float, float, float]:
    state = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.complex128)
    for qubit, logical in ((0, logical_left), (1, logical_right)):
        state = _apply_single(state, _rotation_y(protocol.payload_ry[logical]), qubit)
    state = np.diag([1.0, 1.0, 1.0, -1.0]) @ state
    for qubit, logical in ((0, logical_left), (1, logical_right)):
        state = _apply_single(state, _rotation_x(protocol.payload_rx[logical]), qubit)
        state = _apply_single(
            state,
            _rotation_z(protocol.payload_error_amplification * errors[logical]),
            qubit,
        )
        state = _apply_single(state, _rotation_x(-protocol.payload_rx[logical]), qubit)
    state = np.diag([1.0, 1.0, 1.0, -1.0]) @ state
    for qubit, logical in ((0, logical_left), (1, logical_right)):
        state = _apply_single(state, _rotation_y(-protocol.payload_ry[logical]), qubit)
    probabilities = np.square(np.abs(state))
    probabilities /= float(np.sum(probabilities))
    # Basis ordering is |q0 q1> in this small independent calculation.
    return tuple(float(value) for value in probabilities)


def _payload_local_one_probability(
    logical: int,
    error: float,
    protocol: OpenQuantumScaleProtocol,
) -> float:
    state = np.asarray([1.0, 0.0], dtype=np.complex128)
    state = _rotation_y(protocol.payload_ry[logical]) @ state
    state = _rotation_x(protocol.payload_rx[logical]) @ state
    state = _rotation_z(protocol.payload_error_amplification * error) @ state
    state = _rotation_x(-protocol.payload_rx[logical]) @ state
    state = _rotation_y(-protocol.payload_ry[logical]) @ state
    probabilities = np.square(np.abs(state))
    return float(probabilities[1] / np.sum(probabilities))


def _payload_native_ramsey_one_probability(
    error: float, protocol: OpenQuantumScaleProtocol
) -> float:
    state = np.asarray([1.0, 0.0], dtype=np.complex128)
    state = _rotation_x(math.pi / 2.0) @ state
    state = _rotation_z(protocol.payload_error_amplification * error) @ state
    state = _rotation_x(-math.pi / 2.0) @ state
    probabilities = np.square(np.abs(state))
    return float(probabilities[1] / np.sum(probabilities))


def simulate_openquantum_counts(
    request: AcquisitionRequest,
    protocol: OpenQuantumScaleProtocol,
    *,
    seed: int,
    shots: int | None = None,
    readout_flip: float = 0.035,
) -> dict[str, int]:
    """Memory-bounded exact-block rehearsal with finite-shot readout noise.

    The circuit factorizes into one-qubit monitors and independent two-qubit
    payload pairs.  This routine solves those blocks exactly, samples shots,
    and never allocates a 2**n statevector.
    """

    if not 0.0 <= readout_flip < 0.5:
        raise ValueError("readout flip probability must be in [0, 0.5)")
    sample_count = int(protocol.shots if shots is None else shots)
    rng = np.random.default_rng(int(seed))
    errors = np.asarray(request.effective_phase_error, dtype=np.float64)
    monitor_one = 0.5 * (1.0 + np.sin(errors))
    monitor_measured_one = readout_flip + (1.0 - 2.0 * readout_flip) * monitor_one
    bits = np.zeros((sample_count, protocol.physical_qubits), dtype=np.bool_)
    bits[:, protocol.monitor_qubits] = (
        rng.random((sample_count, protocol.width)) < monitor_measured_one
    )
    if protocol.payload_kind == "local_mirror":
        for logical, qubit in enumerate(protocol.payload_qubits):
            ideal_one = _payload_local_one_probability(
                logical, float(errors[logical]), protocol
            )
            measured_one = readout_flip + (1.0 - 2.0 * readout_flip) * ideal_one
            bits[:, qubit] = rng.random(sample_count) < measured_one
    elif protocol.payload_kind == "native_ramsey_mirror":
        for logical, qubit in enumerate(protocol.payload_qubits):
            ideal_one = _payload_native_ramsey_one_probability(
                float(errors[logical]), protocol
            )
            measured_one = readout_flip + (1.0 - 2.0 * readout_flip) * ideal_one
            bits[:, qubit] = rng.random(sample_count) < measured_one
    elif protocol.payload_kind == "native_single_rx":
        for logical, qubit in enumerate(protocol.payload_qubits):
            angle = protocol.payload_error_amplification * float(errors[logical])
            ideal_one = math.sin(angle / 2.0) ** 2
            measured_one = readout_flip + (1.0 - 2.0 * readout_flip) * ideal_one
            bits[:, qubit] = rng.random(sample_count) < measured_one
    else:
        physical_to_logical = {
            qubit: logical for logical, qubit in enumerate(protocol.payload_qubits)
        }
        for left, right in protocol.payload_edges:
            logical_left = physical_to_logical[left]
            logical_right = physical_to_logical[right]
            pair_probabilities = _payload_pair_probabilities(
                logical_left, logical_right, errors, protocol
            )
            pair_state = rng.choice(4, size=sample_count, p=pair_probabilities)
            first = pair_state >= 2
            second = (pair_state % 2) == 1
            first ^= rng.random(sample_count) < readout_flip
            second ^= rng.random(sample_count) < readout_flip
            bits[:, left] = first
            bits[:, right] = second
    counts: dict[str, int] = {}
    for row in bits:
        # OpenQASM count strings are c[n-1]...c[0].
        key = "".join("1" if value else "0" for value in row[::-1])
        counts[key] = counts.get(key, 0) + 1
    return counts


def run_openquantum_rehearsal(
    *,
    arm: OpenQuantumArm,
    seed: int,
    protocol: OpenQuantumScaleProtocol,
    readout_flip: float = 0.035,
) -> dict[str, Any]:
    """Run the frozen state machine against the memory-bounded block model."""

    reference_request = AcquisitionRequest(
        acquisition=0,
        acquisition_kind="reference",
        contract_eligible=False,
        command=(0.0,) * protocol.width,
        effective_phase_error=(0.0,) * protocol.width,
        qasm=render_openquantum_reference_qasm(protocol),
        qasm_sha256=hashlib.sha256(
            render_openquantum_reference_qasm(protocol).encode("utf-8")
        ).hexdigest(),
    )
    reference_counts = simulate_openquantum_counts(
        reference_request,
        protocol,
        seed=seed + 800_000,
        shots=protocol.reference_shots,
        readout_flip=readout_flip,
    )
    reference_scores = score_openquantum_counts(reference_counts, protocol)
    run = OpenQuantumAdaptiveRun(
        arm=arm,
        seed=seed,
        monitor_target=reference_scores.monitor_response,
        payload_reference_bitwise_zero=reference_scores.payload_bitwise_zero,
        protocol=protocol,
    )
    while not run.complete:
        request = run.next_request()
        counts = simulate_openquantum_counts(
            request,
            protocol,
            seed=seed * 100 + request.acquisition,
            readout_flip=readout_flip,
        )
        run.consume(counts)
    result = run.result()
    result["rehearsal_model"] = (
        "exact factorized one-/two-qubit blocks plus independent symmetric readout noise"
    )
    result["reference"] = asdict(reference_scores)
    return result
