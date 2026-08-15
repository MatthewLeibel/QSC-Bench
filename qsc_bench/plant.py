"""Finite-shot quantum plant used by QSC-Bench.

The controller sees only component-resolved monitor measurements and the public
target. Hidden gains, polarities, phase offsets, drift state, and ideal-state
diagnostics remain evaluator-only.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time

import numpy as np
from numpy.typing import NDArray
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error

from .config import PlantConfig

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class MonitorAcquisition:
    response: FloatArray
    phase_error_before_acquisition: FloatArray
    shots: int
    simulator_seconds: float
    circuit_depth: int
    circuit_two_qubit_gates: int
    seed_simulator: int


@dataclass(frozen=True)
class PayloadAcquisition:
    bitwise_zero_probability: float
    all_zero_probability: float
    phase_error_before_acquisition: FloatArray
    shots: int
    simulator_seconds: float
    circuit_depth: int
    circuit_two_qubit_gates: int
    seed_simulator: int


@dataclass(frozen=True)
class PlantDiagnostics:
    jacobian: FloatArray | None
    minimum_diagonal_magnitude: float
    maximum_row_offdiag_to_diag_ratio: float
    spectral_norm: float


def _ring_edges(n: int) -> list[tuple[int, int]]:
    if n < 2:
        return []
    if n == 2:
        return [(0, 1)]
    return [(i, (i + 1) % n) for i in range(n)]


def _seed32(*parts: int) -> int:
    return int(np.random.SeedSequence(parts).generate_state(1, dtype=np.uint32)[0])


def _counts_to_component_probabilities(counts: dict[str, int], n: int) -> FloatArray:
    total = int(sum(counts.values()))
    if total <= 0:
        raise RuntimeError("simulator returned no measurement shots")
    ones = np.zeros(n, dtype=np.float64)
    for raw_bits, count in counts.items():
        bits = raw_bits.replace(" ", "").zfill(n)
        if len(bits) != n or any(bit not in "01" for bit in bits):
            raise ValueError(f"unexpected count key {raw_bits!r} for {n} qubits")
        for qubit, bit in enumerate(reversed(bits)):
            if bit == "1":
                ones[qubit] += count
    return ones / total


def _payload_scores(counts: dict[str, int], n: int) -> tuple[float, float]:
    total = int(sum(counts.values()))
    if total <= 0:
        raise RuntimeError("simulator returned no payload shots")
    zero_count = 0
    all_zero = 0
    for raw_bits, count in counts.items():
        bits = raw_bits.replace(" ", "").zfill(n)
        zero_count += count * bits.count("0")
        if bits == "0" * n:
            all_zero += count
    return zero_count / (total * n), all_zero / total


class _BaseStabilityPlant:
    """Shared hidden state and drift process for both plant backends."""

    def __init__(self, n: int, seed: int, config: PlantConfig):
        if n < 1:
            raise ValueError("plant width must be positive")
        config.validate()
        self.n = n
        self.seed = int(seed)
        self.config = config

        parameter_rng = np.random.default_rng(_seed32(seed, 101))
        self.nominal_angles = parameter_rng.uniform(
            config.nominal_angle_low, config.nominal_angle_high, size=n
        ).astype(np.float64)
        self.polarities = parameter_rng.choice(np.array([-1.0, 1.0]), size=n)
        self.gains = np.exp(
            parameter_rng.uniform(math.log(config.gain_low), math.log(config.gain_high), size=n)
        ).astype(np.float64)

        self._drift_rng = np.random.default_rng(_seed32(seed, 202))
        shock = self._correlated_normal()
        shock_rms = float(np.sqrt(np.mean(np.square(shock))))
        if config.drift.initial_shock_rms > 0 and shock_rms > 0:
            shock *= config.drift.initial_shock_rms / shock_rms
        else:
            shock.fill(0.0)
        self.fast_drift = np.zeros(n, dtype=np.float64)
        self.slow_drift = shock
        self._monitor_index = 0
        self._payload_index = 0

        payload_rng = np.random.default_rng(_seed32(seed, 303))
        self._payload_angles = payload_rng.uniform(-math.pi, math.pi, size=(3, n))
        # Keep every local-mirror channel away from a low-sensitivity basis.
        self._payload_basis_tilts = payload_rng.uniform(0.80, 1.30, size=n)

    @property
    def drift(self) -> FloatArray:
        return self.fast_drift + self.slow_drift

    def effective_phase_error(self, command: FloatArray) -> FloatArray:
        command = self._validate_command(command)
        return self.polarities * self.gains * command + self.drift

    def _validate_command(self, command: FloatArray) -> FloatArray:
        command = np.asarray(command, dtype=np.float64)
        if command.shape != (self.n,):
            raise ValueError(f"command must have shape ({self.n},), got {command.shape}")
        if not np.all(np.isfinite(command)):
            raise ValueError("command contains non-finite values")
        return command

    def _correlated_normal(self) -> FloatArray:
        rho = self.config.drift.common_mode_fraction
        independent = self._drift_rng.normal(size=self.n)
        common = self._drift_rng.normal()
        return np.sqrt(1.0 - rho) * independent + np.sqrt(rho) * common

    def _advance_drift(self) -> None:
        drift_cfg = self.config.drift
        self.fast_drift = (
            (1.0 - drift_cfg.fast_reversion) * self.fast_drift
            + drift_cfg.fast_sigma * self._correlated_normal()
        )
        self.slow_drift = self.slow_drift + drift_cfg.slow_sigma * self._correlated_normal()


class QuantumStabilityPlant(_BaseStabilityPlant):
    """A drifting, locally component-observable quantum circuit.

    Each actuator command ``u_i`` changes a hidden physical phase through an
    unknown polarity ``s_i`` and gain ``g_i``. A monitor acquisition runs one
    noisy circuit and returns every marginal response in parallel. Sparse RZZ
    interactions make the response genuinely coupled while preserving a weakly
    diagonally dominant main track.
    """

    def __init__(self, n: int, seed: int, config: PlantConfig):
        super().__init__(n=n, seed=seed, config=config)
        self._noise_model = self._build_noise_model()
        self._backend = AerSimulator(
            method=config.simulator_method,
            noise_model=self._noise_model,
        )

    def _build_noise_model(self) -> NoiseModel:
        cfg = self.config.noise
        model = NoiseModel()
        if cfg.one_qubit_depolarizing > 0:
            error_1q = depolarizing_error(cfg.one_qubit_depolarizing, 1)
            model.add_all_qubit_quantum_error(error_1q, ["h", "rx", "ry", "rz"])
        if cfg.two_qubit_depolarizing > 0:
            error_2q = depolarizing_error(cfg.two_qubit_depolarizing, 2)
            model.add_all_qubit_quantum_error(error_2q, ["rzz"])
        if cfg.readout_flip > 0:
            p = cfg.readout_flip
            model.add_all_qubit_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]))
        return model

    def _monitor_circuit(self, phase_error: FloatArray, *, measure: bool) -> QuantumCircuit:
        angles = self.nominal_angles + phase_error
        circuit = QuantumCircuit(self.n, self.n if measure else 0)
        for i in range(self.n):
            circuit.h(i)
            circuit.rz(float(angles[i]), i)
            circuit.ry(self.config.analysis_tilt_radians, i)
        for left, right in _ring_edges(self.n):
            circuit.rzz(self.config.coupling_radians, left, right)
        for i in range(self.n):
            circuit.h(i)
        if measure:
            circuit.measure(range(self.n), range(self.n))
        return circuit

    def _payload_unitary(self) -> QuantumCircuit:
        unitary = QuantumCircuit(self.n)
        for i in range(self.n):
            unitary.ry(float(self._payload_angles[0, i]), i)
            unitary.rz(float(self._payload_angles[1, i]), i)
        for left, right in _ring_edges(self.n):
            unitary.rzz(0.13, left, right)
        for i in range(self.n):
            unitary.rx(float(self._payload_angles[2, i]), i)
        return unitary

    def _payload_circuit(self, phase_error: FloatArray) -> QuantumCircuit:
        if self.config.payload_kind == "local_mirror":
            circuit = QuantumCircuit(self.n, self.n)
            for i in range(self.n):
                basis = float(self._payload_basis_tilts[i])
                circuit.ry(basis, i)
                circuit.rz(
                    float(self.config.payload_error_amplification * phase_error[i]), i
                )
                circuit.ry(-basis, i)
            circuit.measure(range(self.n), range(self.n))
            return circuit

        unitary = self._payload_unitary()
        circuit = QuantumCircuit(self.n, self.n)
        circuit.compose(unitary, inplace=True)
        for i in range(self.n):
            circuit.rz(float(self.config.payload_error_amplification * phase_error[i]), i)
        circuit.compose(unitary.inverse(), inplace=True)
        circuit.measure(range(self.n), range(self.n))
        return circuit

    @staticmethod
    def _two_qubit_gate_count(circuit: QuantumCircuit) -> int:
        return sum(1 for item in circuit.data if len(item.qubits) == 2)

    def _run_counts(
        self, circuit: QuantumCircuit, *, shots: int, seed_simulator: int
    ) -> tuple[dict[str, int], float]:
        start = time.perf_counter()
        result = self._backend.run(
            circuit,
            shots=shots,
            seed_simulator=seed_simulator,
        ).result()
        elapsed = time.perf_counter() - start
        counts = result.get_counts()
        return counts, elapsed

    def reference_monitor_target(self, shots: int) -> FloatArray:
        circuit = self._monitor_circuit(np.zeros(self.n), measure=True)
        counts, _ = self._run_counts(
            circuit, shots=shots, seed_simulator=_seed32(self.seed, 401, shots)
        )
        return _counts_to_component_probabilities(counts, self.n)

    def reference_payload_quality(self, shots: int) -> tuple[float, float]:
        circuit = self._payload_circuit(np.zeros(self.n))
        counts, _ = self._run_counts(
            circuit, shots=shots, seed_simulator=_seed32(self.seed, 402, shots)
        )
        return _payload_scores(counts, self.n)

    def acquire_monitor(self, command: FloatArray, shots: int) -> MonitorAcquisition:
        phase_error = self.effective_phase_error(command).copy()
        circuit = self._monitor_circuit(phase_error, measure=True)
        seed_simulator = _seed32(self.seed, 501, self._monitor_index, shots)
        counts, elapsed = self._run_counts(
            circuit, shots=shots, seed_simulator=seed_simulator
        )
        acquisition = MonitorAcquisition(
            response=_counts_to_component_probabilities(counts, self.n),
            phase_error_before_acquisition=phase_error,
            shots=shots,
            simulator_seconds=elapsed,
            circuit_depth=circuit.depth(),
            circuit_two_qubit_gates=self._two_qubit_gate_count(circuit),
            seed_simulator=seed_simulator,
        )
        self._monitor_index += 1
        self._advance_drift()
        return acquisition

    def acquire_payload(self, command: FloatArray, shots: int) -> PayloadAcquisition:
        phase_error = self.effective_phase_error(command).copy()
        circuit = self._payload_circuit(phase_error)
        seed_simulator = _seed32(self.seed, 601, self._payload_index, shots)
        counts, elapsed = self._run_counts(
            circuit, shots=shots, seed_simulator=seed_simulator
        )
        bitwise_zero, all_zero = _payload_scores(counts, self.n)
        acquisition = PayloadAcquisition(
            bitwise_zero_probability=bitwise_zero,
            all_zero_probability=all_zero,
            phase_error_before_acquisition=phase_error,
            shots=shots,
            simulator_seconds=elapsed,
            circuit_depth=circuit.depth(),
            circuit_two_qubit_gates=self._two_qubit_gate_count(circuit),
            seed_simulator=seed_simulator,
        )
        self._payload_index += 1
        self._advance_drift()
        return acquisition

    def ideal_monitor_response(self, phase_error: FloatArray) -> FloatArray:
        """Evaluator-only shot-free response; never passed to a controller."""
        phase_error = np.asarray(phase_error, dtype=np.float64)
        if phase_error.shape != (self.n,):
            raise ValueError("phase_error has the wrong shape")
        state = Statevector.from_instruction(self._monitor_circuit(phase_error, measure=False))
        return np.asarray([state.probabilities([i])[1] for i in range(self.n)])

    def local_jacobian_diagnostics(self, step: float = 1e-5) -> PlantDiagnostics:
        """Evaluator-only numerical check of local informativeness and coupling."""
        base_error = np.zeros(self.n, dtype=np.float64)
        base = self.ideal_monitor_response(base_error)
        jacobian = np.empty((self.n, self.n), dtype=np.float64)
        for j in range(self.n):
            perturbed = base_error.copy()
            perturbed[j] += step
            jacobian[:, j] = (self.ideal_monitor_response(perturbed) - base) / step
        diagonal = np.abs(np.diag(jacobian))
        offdiag = np.sum(np.abs(jacobian), axis=1) - diagonal
        ratios = np.divide(
            offdiag,
            diagonal,
            out=np.full_like(offdiag, np.inf),
            where=diagonal > 0,
        )
        return PlantDiagnostics(
            jacobian=jacobian,
            minimum_diagonal_magnitude=float(np.min(diagonal)),
            maximum_row_offdiag_to_diag_ratio=float(np.max(ratios)),
            spectral_norm=float(np.linalg.norm(jacobian, ord=2)),
        )


class AnalyticRingPlant(_BaseStabilityPlant):
    """Marginal-exact reduced backend for the shallow ring monitor.

    The ideal component probabilities are the closed-form marginals of the
    same H-RZ-RY-RZZ-H circuit used by :class:`QuantumStabilityPlant`.
    Symmetric readout noise is applied analytically and each marginal is then
    sampled from its exact binomial distribution.  Joint shot covariance is
    not reproduced, so this backend is a validated scale extension rather than
    a replacement for overlapping Aer runs.  The local-mirror payload is a
    separate product quantum circuit with an exact closed form.
    """

    def _ideal_monitor_probabilities(self, phase_error: FloatArray) -> FloatArray:
        phase_error = np.asarray(phase_error, dtype=np.float64)
        if phase_error.shape != (self.n,):
            raise ValueError("phase_error has the wrong shape")
        theta = self.nominal_angles + phase_error
        tilt = self.config.analysis_tilt_radians
        chi = self.config.coupling_radians
        x = np.cos(tilt) * np.cos(theta)
        y = np.sin(theta)
        z = -np.sin(tilt) * np.cos(theta)
        coherence = x + 1j * y
        cosine = np.cos(chi)
        sine = np.sin(chi)
        if self.n == 1:
            x_after = x
        elif self.n == 2:
            x_after = np.real(coherence * (cosine + 1j * z[::-1] * sine))
        else:
            x_after = np.real(
                coherence
                * (cosine + 1j * np.roll(z, 1) * sine)
                * (cosine + 1j * np.roll(z, -1) * sine)
            )
        return np.clip((1.0 - x_after) / 2.0, 0.0, 1.0)

    def _readout_probabilities(self, probabilities_one: FloatArray) -> FloatArray:
        flip = self.config.noise.readout_flip
        return flip + (1.0 - 2.0 * flip) * probabilities_one

    @staticmethod
    def _sample_marginals(
        probabilities: FloatArray, shots: int, seed_simulator: int
    ) -> FloatArray:
        rng = np.random.default_rng(seed_simulator)
        return rng.binomial(shots, probabilities).astype(np.float64) / shots

    def _local_payload_zero_probabilities(self, phase_error: FloatArray) -> FloatArray:
        delta = self.config.payload_error_amplification * phase_error
        ideal = 1.0 - np.sin(self._payload_basis_tilts) ** 2 * np.sin(delta / 2.0) ** 2
        flip = self.config.noise.readout_flip
        return np.clip(flip + (1.0 - 2.0 * flip) * ideal, 0.0, 1.0)

    def reference_monitor_target(self, shots: int) -> FloatArray:
        probabilities = self._readout_probabilities(
            self._ideal_monitor_probabilities(np.zeros(self.n, dtype=np.float64))
        )
        return self._sample_marginals(
            probabilities, shots, _seed32(self.seed, 401, shots)
        )

    def reference_payload_quality(self, shots: int) -> tuple[float, float]:
        probabilities_zero = self._local_payload_zero_probabilities(
            np.zeros(self.n, dtype=np.float64)
        )
        seed_simulator = _seed32(self.seed, 402, shots)
        sampled = self._sample_marginals(probabilities_zero, shots, seed_simulator)
        log_all_zero = float(np.sum(np.log(np.maximum(probabilities_zero, 1e-300))))
        expected_all_zero = 0.0 if log_all_zero < -745 else math.exp(log_all_zero)
        rng = np.random.default_rng(_seed32(seed_simulator, 1))
        sampled_all_zero = float(rng.binomial(shots, expected_all_zero) / shots)
        return float(np.mean(sampled)), sampled_all_zero

    def acquire_monitor(self, command: FloatArray, shots: int) -> MonitorAcquisition:
        start = time.perf_counter()
        phase_error = self.effective_phase_error(command).copy()
        probabilities = self._readout_probabilities(
            self._ideal_monitor_probabilities(phase_error)
        )
        seed_simulator = _seed32(self.seed, 501, self._monitor_index, shots)
        response = self._sample_marginals(probabilities, shots, seed_simulator)
        elapsed = time.perf_counter() - start
        edge_count = len(_ring_edges(self.n))
        acquisition = MonitorAcquisition(
            response=response,
            phase_error_before_acquisition=phase_error,
            shots=shots,
            simulator_seconds=elapsed,
            circuit_depth=5 if edge_count else 4,
            circuit_two_qubit_gates=edge_count,
            seed_simulator=seed_simulator,
        )
        self._monitor_index += 1
        self._advance_drift()
        return acquisition

    def acquire_payload(self, command: FloatArray, shots: int) -> PayloadAcquisition:
        start = time.perf_counter()
        phase_error = self.effective_phase_error(command).copy()
        probabilities_zero = self._local_payload_zero_probabilities(phase_error)
        seed_simulator = _seed32(self.seed, 601, self._payload_index, shots)
        sampled = self._sample_marginals(probabilities_zero, shots, seed_simulator)
        log_all_zero = float(np.sum(np.log(np.maximum(probabilities_zero, 1e-300))))
        expected_all_zero = 0.0 if log_all_zero < -745 else math.exp(log_all_zero)
        rng = np.random.default_rng(_seed32(seed_simulator, 1))
        all_zero = float(rng.binomial(shots, expected_all_zero) / shots)
        elapsed = time.perf_counter() - start
        acquisition = PayloadAcquisition(
            bitwise_zero_probability=float(np.mean(sampled)),
            all_zero_probability=all_zero,
            phase_error_before_acquisition=phase_error,
            shots=shots,
            simulator_seconds=elapsed,
            circuit_depth=3,
            circuit_two_qubit_gates=0,
            seed_simulator=seed_simulator,
        )
        self._payload_index += 1
        self._advance_drift()
        return acquisition

    def ideal_monitor_response(self, phase_error: FloatArray) -> FloatArray:
        return self._ideal_monitor_probabilities(phase_error)

    def _jacobian_bands(self) -> tuple[FloatArray, FloatArray, FloatArray]:
        theta = self.nominal_angles
        tilt = self.config.analysis_tilt_radians
        chi = self.config.coupling_radians
        x = np.cos(tilt) * np.cos(theta)
        y = np.sin(theta)
        z = -np.sin(tilt) * np.cos(theta)
        coherence = x + 1j * y
        dcoherence = -np.cos(tilt) * np.sin(theta) + 1j * np.cos(theta)
        dz = np.sin(tilt) * np.sin(theta)
        cosine = np.cos(chi)
        sine = np.sin(chi)
        readout_scale = 1.0 - 2.0 * self.config.noise.readout_flip

        diagonal = np.empty(self.n, dtype=np.float64)
        left = np.zeros(self.n, dtype=np.float64)
        right = np.zeros(self.n, dtype=np.float64)
        if self.n == 1:
            diagonal[:] = -0.5 * readout_scale * np.real(dcoherence)
        elif self.n == 2:
            factor = cosine + 1j * z[::-1] * sine
            diagonal[:] = -0.5 * readout_scale * np.real(dcoherence * factor)
            other_dz = dz[::-1]
            left[:] = -0.5 * readout_scale * np.real(
                coherence * (1j * sine * other_dz)
            )
        else:
            factor_left = cosine + 1j * np.roll(z, 1) * sine
            factor_right = cosine + 1j * np.roll(z, -1) * sine
            diagonal[:] = -0.5 * readout_scale * np.real(
                dcoherence * factor_left * factor_right
            )
            left[:] = -0.5 * readout_scale * np.real(
                coherence
                * (1j * sine * np.roll(dz, 1))
                * factor_right
            )
            right[:] = -0.5 * readout_scale * np.real(
                coherence
                * factor_left
                * (1j * sine * np.roll(dz, -1))
            )
        return diagonal, left, right

    def local_jacobian_diagnostics(self, step: float = 1e-5) -> PlantDiagnostics:
        del step
        diagonal, left, right = self._jacobian_bands()
        offdiag = np.abs(left) + np.abs(right)
        ratios = np.divide(
            offdiag,
            np.abs(diagonal),
            out=np.full_like(offdiag, np.inf),
            where=np.abs(diagonal) > 0,
        )

        dense: FloatArray | None = None
        if self.n <= 64:
            dense = np.zeros((self.n, self.n), dtype=np.float64)
            np.fill_diagonal(dense, diagonal)
            if self.n == 2:
                dense[0, 1] = left[0]
                dense[1, 0] = left[1]
            elif self.n > 2:
                rows = np.arange(self.n)
                dense[rows, (rows - 1) % self.n] = left
                dense[rows, (rows + 1) % self.n] = right

        def multiply(vector: FloatArray) -> FloatArray:
            if self.n == 1:
                return diagonal * vector
            if self.n == 2:
                return diagonal * vector + left * vector[::-1]
            return (
                diagonal * vector
                + left * np.roll(vector, 1)
                + right * np.roll(vector, -1)
            )

        def transpose_multiply(vector: FloatArray) -> FloatArray:
            if self.n == 1:
                return diagonal * vector
            if self.n == 2:
                return diagonal * vector + left[::-1] * vector[::-1]
            return (
                diagonal * vector
                + np.roll(left, -1) * np.roll(vector, -1)
                + np.roll(right, 1) * np.roll(vector, 1)
            )

        vector = np.full(self.n, 1.0 / math.sqrt(self.n), dtype=np.float64)
        for _ in range(24):
            candidate = transpose_multiply(multiply(vector))
            norm = float(np.linalg.norm(candidate))
            if norm == 0:
                break
            vector = candidate / norm
        spectral_norm = float(np.linalg.norm(multiply(vector)))
        return PlantDiagnostics(
            jacobian=dense,
            minimum_diagonal_magnitude=float(np.min(np.abs(diagonal))),
            maximum_row_offdiag_to_diag_ratio=float(np.max(ratios)),
            spectral_norm=spectral_norm,
        )


def make_plant(n: int, seed: int, config: PlantConfig) -> _BaseStabilityPlant:
    if config.backend == "aer":
        return QuantumStabilityPlant(n=n, seed=seed, config=config)
    if config.backend == "analytic_ring":
        return AnalyticRingPlant(n=n, seed=seed, config=config)
    raise ValueError(f"unsupported plant backend: {config.backend}")
