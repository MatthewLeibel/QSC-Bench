"""Controllers used in QSC-Bench.

No ranked controller receives hidden drift, gains, polarities, statevectors, or
analytic gradients. The oracle is an explicitly unranked lower bound.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
MAX_DENSE_CONTROLLER_WIDTH = 512


@dataclass(frozen=True)
class ControllerMetadata:
    name: str
    information_access: str
    commissioned: bool
    ranked: bool
    retained_configuration: bool
    state_class: str
    acquisition_depth_class: str
    host_arithmetic_class: str
    host_state_class: str
    discarded_probe_acquisitions: bool
    minimal_sufficient_cold_start_candidate: bool
    resource_class_note: str


class Controller(ABC):
    metadata: ControllerMetadata

    def __init__(self, n: int, seed: int, lo: float = -3.0, hi: float = 3.0):
        self.n = n
        self.seed = int(seed)
        self.lo = float(lo)
        self.hi = float(hi)
        self.u = np.zeros(n, dtype=np.float64)
        self.update_count = 0

    @abstractmethod
    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        """Consume one ordinary component-resolved acquisition."""

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {"u": self.u}

    def mutable_float_words(self) -> int:
        return int(
            sum(array.size for array in self.mutable_state_arrays().values() if array.dtype.kind == "f")
        )

    def mutable_float_words_per_channel(self) -> float:
        return self.mutable_float_words() / self.n

    def mutable_state_bytes(self) -> int:
        return int(sum(array.nbytes for array in self.mutable_state_arrays().values()))

    def _check_observation(self, response: FloatArray, target: FloatArray) -> None:
        if response.shape != (self.n,) or target.shape != (self.n,):
            raise ValueError("response and target must match controller width")
        if not np.all(np.isfinite(response)) or not np.all(np.isfinite(target)):
            raise ValueError("response and target must be finite")


class DoNothing(Controller):
    metadata = ControllerMetadata(
        name="do_nothing",
        information_access="none after target publication",
        commissioned=False,
        ranked=True,
        retained_configuration=True,
        state_class="O(1) words/channel",
        acquisition_depth_class="O(1)",
        host_arithmetic_class="O(n)",
        host_state_class="O(n) total; O(1) per channel",
        discarded_probe_acquisitions=False,
        minimal_sufficient_cold_start_candidate=False,
        resource_class_note="Meets the resource ceilings but cannot discharge restoration.",
    )

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        self.update_count += 1
        return self.u


class RetainedResidual(Controller):
    """Independent manuscript-level implementation of the reference law.

    The six mutable floating-point words per channel are exactly ``u``,
    ``u_prev``, ``last_action``, ``last_response``, ``correlation``, and
    ``gain_hat``. The polarity estimate is derived from ``correlation`` rather
    than cached as a seventh floating-point vector. ``id_sign`` is immutable
    one-bit/channel identification metadata (stored as int8 in this code).
    """

    metadata = ControllerMetadata(
        name="retained_residual",
        information_access="one component-resolved vector/acquisition",
        commissioned=False,
        ranked=True,
        retained_configuration=True,
        state_class="six float words/channel plus immutable one-bit ID sign",
        acquisition_depth_class="O(1)",
        host_arithmetic_class="O(n)",
        host_state_class="O(n) total; O(1) per channel",
        discarded_probe_acquisitions=False,
        minimal_sufficient_cold_start_candidate=True,
        resource_class_note=(
            "Candidate member of the manuscript's minimal-sufficient class: "
            "one retained full-vector update, no separate commissioning sweep."
        ),
    )

    def __init__(
        self,
        n: int,
        seed: int,
        *,
        eta: float = 0.65,
        momentum: float = 0.15,
        estimator_smoothing: float = 0.50,
        gain_floor: float = 0.15,
        identification_amplitude: float = 0.150,
        identification_cycles: int = 3,
        lo: float = -3.0,
        hi: float = 3.0,
    ):
        super().__init__(n, seed, lo, hi)
        self.eta = eta
        self.momentum = momentum
        self.estimator_smoothing = estimator_smoothing
        self.gain_floor = gain_floor
        self.identification_amplitude = identification_amplitude
        self.identification_cycles = identification_cycles
        self.u_prev = np.zeros(n, dtype=np.float64)
        self.last_action = np.zeros(n, dtype=np.float64)
        self.last_response = np.zeros(n, dtype=np.float64)
        self.correlation = np.zeros(n, dtype=np.float64)
        self.gain_hat = np.full(n, gain_floor, dtype=np.float64)
        rng = np.random.default_rng(seed)
        self.id_sign = rng.choice(np.array([-1, 1], dtype=np.int8), size=n)
        self._has_last_response = False

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {
            "u": self.u,
            "u_prev": self.u_prev,
            "last_action": self.last_action,
            "last_response": self.last_response,
            "correlation": self.correlation,
            "gain_hat": self.gain_hat,
        }

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        response = np.asarray(response, dtype=np.float64)
        if self._has_last_response:
            delta_response = response - self.last_response
            active = np.abs(self.last_action) > 1e-9
            if np.any(active):
                observed_sign = np.sign(
                    delta_response[active] * self.last_action[active]
                )
                beta = self.estimator_smoothing
                self.correlation[active] = (
                    (1.0 - beta) * self.correlation[active] + beta * observed_sign
                )
                local_slope = np.abs(delta_response[active]) / np.maximum(
                    np.abs(self.last_action[active]), 1e-9
                )
                self.gain_hat[active] = (
                    (1.0 - beta) * self.gain_hat[active] + beta * local_slope
                )

        if self.update_count < self.identification_cycles:
            direction = 1.0 if self.update_count % 2 == 0 else -1.0
            action = self.identification_amplitude * self.id_sign.astype(np.float64) * direction
        else:
            polarity_hat = np.where(self.correlation == 0.0, 1.0, np.sign(self.correlation))
            diagonal_gain = (
                self.eta * polarity_hat / np.maximum(self.gain_hat, self.gain_floor)
            )
            action = diagonal_gain * (target - response) + self.momentum * (
                self.u - self.u_prev
            )

        new_u = np.clip(self.u + action, self.lo, self.hi)
        self.last_action[:] = new_u - self.u
        self.u_prev[:] = self.u
        self.u[:] = new_u
        self.last_response[:] = response
        self._has_last_response = True
        self.update_count += 1
        return self.u


class DiagonalSecant(Controller):
    """Retained diagonal secant/Broyden-style in-class baseline."""

    metadata = ControllerMetadata(
        name="diagonal_secant",
        information_access="one component-resolved vector/acquisition",
        commissioned=False,
        ranked=True,
        retained_configuration=True,
        state_class="four float words/channel plus immutable one-bit ID sign",
        acquisition_depth_class="O(1)",
        host_arithmetic_class="O(n)",
        host_state_class="O(n) total; O(1) per channel",
        discarded_probe_acquisitions=False,
        minimal_sufficient_cold_start_candidate=True,
        resource_class_note=(
            "In-class retained secant control under a locally informative diagonal map; "
            "a stronger control than controller-specific exclusivity."
        ),
    )

    def __init__(
        self,
        n: int,
        seed: int,
        *,
        eta: float = 0.80,
        smoothing: float = 0.50,
        slope_floor: float = 0.03,
        identification_amplitude: float = 0.150,
        trust_radius: float = 0.75,
        lo: float = -3.0,
        hi: float = 3.0,
    ):
        super().__init__(n, seed, lo, hi)
        self.eta = eta
        self.smoothing = smoothing
        self.slope_floor = slope_floor
        self.identification_amplitude = identification_amplitude
        self.trust_radius = trust_radius
        self.last_u = np.zeros(n, dtype=np.float64)
        self.last_response = np.zeros(n, dtype=np.float64)
        self.slope = np.full(n, slope_floor, dtype=np.float64)
        rng = np.random.default_rng(seed)
        self.id_sign = rng.choice(np.array([-1, 1], dtype=np.int8), size=n)
        self._has_last_response = False

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {
            "u": self.u,
            "last_u": self.last_u,
            "last_response": self.last_response,
            "slope": self.slope,
        }

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        response = np.asarray(response, dtype=np.float64)
        measured_u = self.u.copy()

        if self._has_last_response:
            delta_u = measured_u - self.last_u
            active = np.abs(delta_u) > 1e-9
            raw_slope = np.zeros(self.n, dtype=np.float64)
            raw_slope[active] = (response[active] - self.last_response[active]) / delta_u[active]
            informative = active & (np.abs(raw_slope) >= self.slope_floor)
            self.slope[informative] = (
                (1.0 - self.smoothing) * self.slope[informative]
                + self.smoothing * raw_slope[informative]
            )

        if not self._has_last_response:
            action = self.identification_amplitude * self.id_sign.astype(np.float64)
        else:
            safe_slope = np.where(
                np.abs(self.slope) >= self.slope_floor,
                self.slope,
                np.where(self.slope < 0, -self.slope_floor, self.slope_floor),
            )
            action = self.eta * (target - response) / safe_slope
            action = np.clip(action, -self.trust_radius, self.trust_radius)

        new_u = np.clip(measured_u + action, self.lo, self.hi)
        self.last_u[:] = measured_u
        self.last_response[:] = response
        self.u[:] = new_u
        self._has_last_response = True
        self.update_count += 1
        return self.u


class AndersonResidual(Controller):
    """Fixed-window Anderson acceleration of the retained residual map.

    The window is fixed at design time, so total work and state remain linear
    in width.  This is intentionally a strong in-class comparator rather than
    a weakened baseline.
    """

    metadata = ControllerMetadata(
        name="anderson_residual",
        information_access="one component-resolved vector/acquisition",
        commissioned=False,
        ranked=True,
        retained_configuration=True,
        state_class="O(k) float words/channel for fixed window k",
        acquisition_depth_class="O(1)",
        host_arithmetic_class="O(kn + k^3), linear in n for fixed k",
        host_state_class="O(kn), bounded O(1) per channel for fixed k",
        discarded_probe_acquisitions=False,
        minimal_sufficient_cold_start_candidate=True,
        resource_class_note=(
            "Candidate minimal-sufficient member with a fixed retained history; "
            "larger constants than diagonal retained laws but no superlinear width term."
        ),
    )

    def __init__(
        self,
        n: int,
        seed: int,
        *,
        window: int = 5,
        eta: float = 0.65,
        momentum: float = 0.15,
        estimator_smoothing: float = 0.50,
        gain_floor: float = 0.15,
        identification_amplitude: float = 0.150,
        identification_cycles: int = 3,
        regularization: float = 1e-7,
        mixing: float = 0.50,
        trust_radius: float = 0.90,
        lo: float = -3.0,
        hi: float = 3.0,
    ):
        super().__init__(n, seed, lo, hi)
        if window < 1:
            raise ValueError("Anderson window must be positive")
        self.window = int(window)
        self.eta = eta
        self.momentum = momentum
        self.estimator_smoothing = estimator_smoothing
        self.gain_floor = gain_floor
        self.identification_amplitude = identification_amplitude
        self.identification_cycles = identification_cycles
        self.regularization = regularization
        self.mixing = mixing
        self.trust_radius = trust_radius
        self.u_prev = np.zeros(n, dtype=np.float64)
        self.last_action = np.zeros(n, dtype=np.float64)
        self.last_response = np.zeros(n, dtype=np.float64)
        self.correlation = np.zeros(n, dtype=np.float64)
        self.gain_hat = np.full(n, gain_floor, dtype=np.float64)
        self.history_residuals = np.zeros((self.window, n), dtype=np.float64)
        self.history_candidates = np.zeros((self.window, n), dtype=np.float64)
        rng = np.random.default_rng(seed)
        self.id_sign = rng.choice(np.array([-1, 1], dtype=np.int8), size=n)
        self._has_last_response = False
        self._history_count = 0
        self._history_cursor = 0

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {
            "u": self.u,
            "u_prev": self.u_prev,
            "last_action": self.last_action,
            "last_response": self.last_response,
            "correlation": self.correlation,
            "gain_hat": self.gain_hat,
            "history_residuals": self.history_residuals,
            "history_candidates": self.history_candidates,
        }

    def _ordered_history(self) -> tuple[FloatArray, FloatArray]:
        if self._history_count < self.window:
            return (
                self.history_residuals[: self._history_count],
                self.history_candidates[: self._history_count],
            )
        order = np.concatenate(
            (
                np.arange(self._history_cursor, self.window),
                np.arange(0, self._history_cursor),
            )
        )
        return self.history_residuals[order], self.history_candidates[order]

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        response = np.asarray(response, dtype=np.float64)
        if self._has_last_response:
            delta_response = response - self.last_response
            active = np.abs(self.last_action) > 1e-9
            if np.any(active):
                beta = self.estimator_smoothing
                observed_sign = np.sign(delta_response[active] * self.last_action[active])
                self.correlation[active] = (
                    (1.0 - beta) * self.correlation[active] + beta * observed_sign
                )
                local_slope = np.abs(delta_response[active]) / np.maximum(
                    np.abs(self.last_action[active]), 1e-9
                )
                self.gain_hat[active] = (
                    (1.0 - beta) * self.gain_hat[active] + beta * local_slope
                )

        if self.update_count < self.identification_cycles:
            direction = 1.0 if self.update_count % 2 == 0 else -1.0
            action = self.identification_amplitude * self.id_sign.astype(np.float64) * direction
            proposed = self.u + action
        else:
            polarity_hat = np.where(self.correlation == 0.0, 1.0, np.sign(self.correlation))
            gain = self.eta * polarity_hat / np.maximum(self.gain_hat, self.gain_floor)
            residual_step = gain * (target - response) + self.momentum * (
                self.u - self.u_prev
            )
            base_candidate = np.clip(self.u + residual_step, self.lo, self.hi)
            fixed_point_residual = base_candidate - self.u
            slot = self._history_cursor
            self.history_residuals[slot] = fixed_point_residual
            self.history_candidates[slot] = base_candidate
            self._history_cursor = (slot + 1) % self.window
            self._history_count = min(self._history_count + 1, self.window)
            residuals, candidates = self._ordered_history()
            count = residuals.shape[0]
            if count == 1:
                proposed = base_candidate
            else:
                gram = residuals @ residuals.T
                gram.flat[:: count + 1] += self.regularization
                kkt = np.empty((count + 1, count + 1), dtype=np.float64)
                kkt[:count, :count] = gram
                kkt[:count, count] = 1.0
                kkt[count, :count] = 1.0
                kkt[count, count] = 0.0
                rhs = np.zeros(count + 1, dtype=np.float64)
                rhs[count] = 1.0
                try:
                    coefficients = np.linalg.solve(kkt, rhs)[:count]
                    if np.max(np.abs(coefficients)) > 4.0:
                        proposed = base_candidate
                    else:
                        mixed = coefficients @ candidates
                        proposed = (
                            (1.0 - self.mixing) * base_candidate
                            + self.mixing * mixed
                        )
                except np.linalg.LinAlgError:
                    proposed = base_candidate
            proposed = self.u + np.clip(
                proposed - self.u, -self.trust_radius, self.trust_radius
            )

        new_u = np.clip(proposed, self.lo, self.hi)
        self.last_action[:] = new_u - self.u
        self.u_prev[:] = self.u
        self.u[:] = new_u
        self.last_response[:] = response
        self._has_last_response = True
        self.update_count += 1
        return self.u


class FullBroyden(Controller):
    """Retained full-Jacobian Broyden comparator with an explicit dense ceiling."""

    metadata = ControllerMetadata(
        name="full_broyden",
        information_access="one component-resolved vector/acquisition",
        commissioned=False,
        ranked=True,
        retained_configuration=True,
        state_class="O(n^2) dense Jacobian plus O(n) vectors",
        acquisition_depth_class="O(1)",
        host_arithmetic_class="O(n^3) direct regularized solve as implemented",
        host_state_class="O(n^2)",
        discarded_probe_acquisitions=False,
        minimal_sufficient_cold_start_candidate=False,
        resource_class_note=(
            "Retains ordinary acquisitions but re-imports a dense model and solve. "
            "This is distinct from the in-class diagonal retained secant controller."
        ),
    )

    def __init__(
        self,
        n: int,
        seed: int,
        *,
        eta: float = 0.70,
        regularization: float = 1e-2,
        identification_amplitude: float = 0.150,
        trust_radius: float = 0.75,
        lo: float = -3.0,
        hi: float = 3.0,
    ):
        if n > MAX_DENSE_CONTROLLER_WIDTH:
            raise ValueError(
                "full_broyden is deliberately limited to "
                f"n <= {MAX_DENSE_CONTROLLER_WIDTH}; its O(n^2) state and O(n^3) "
                "solve are represented structurally beyond that width"
            )
        super().__init__(n, seed, lo, hi)
        self.eta = eta
        self.regularization = regularization
        self.identification_amplitude = identification_amplitude
        self.trust_radius = trust_radius
        self.last_u = np.zeros(n, dtype=np.float64)
        self.last_response = np.zeros(n, dtype=np.float64)
        self.jacobian = np.eye(n, dtype=np.float64)
        rng = np.random.default_rng(seed)
        self.id_sign = rng.choice(np.array([-1, 1], dtype=np.int8), size=n)
        self._has_last_response = False
        self._diagonal_initialized = False

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {
            "u": self.u,
            "last_u": self.last_u,
            "last_response": self.last_response,
            "jacobian": self.jacobian,
        }

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        response = np.asarray(response, dtype=np.float64)
        measured_u = self.u.copy()
        if self._has_last_response:
            step = measured_u - self.last_u
            change = response - self.last_response
            active = np.abs(step) > 1e-9
            if not self._diagonal_initialized and np.all(active):
                slope = change / step
                slope = np.where(
                    np.abs(slope) >= 0.03,
                    slope,
                    np.where(slope < 0, -0.03, 0.03),
                )
                self.jacobian[:] = np.diag(slope)
                self._diagonal_initialized = True
            denominator = float(step @ step)
            if denominator > 1e-12:
                defect = change - self.jacobian @ step
                self.jacobian += np.outer(defect, step) / denominator

        if not self._has_last_response:
            action = self.identification_amplitude * self.id_sign.astype(np.float64)
        else:
            lhs = self.jacobian.T @ self.jacobian
            lhs.flat[:: self.n + 1] += self.regularization
            rhs = self.jacobian.T @ (target - response)
            try:
                action = self.eta * np.linalg.solve(lhs, rhs)
            except np.linalg.LinAlgError:
                action = self.eta * rhs
            action = np.clip(action, -self.trust_radius, self.trust_radius)

        new_u = np.clip(measured_u + action, self.lo, self.hi)
        self.last_u[:] = measured_u
        self.last_response[:] = response
        self.u[:] = new_u
        self._has_last_response = True
        self.update_count += 1
        return self.u


class SPSA(Controller):
    """Scalar-objective simultaneous perturbation baseline.

    The runner charges two discarded probe acquisitions per update in addition
    to ordinary contract observations.  Only the two scalar losses are used.
    """

    metadata = ControllerMetadata(
        name="spsa",
        information_access="two scalar losses from discarded +/- perturbation acquisitions",
        commissioned=False,
        ranked=True,
        retained_configuration=True,
        state_class="two float words/channel",
        acquisition_depth_class="two sequential probes per update",
        host_arithmetic_class="O(n)",
        host_state_class="O(n) total; O(1) per channel",
        discarded_probe_acquisitions=True,
        minimal_sufficient_cold_start_candidate=False,
        resource_class_note=(
            "Keeps linear state and arithmetic but buys a noisy direction with two "
            "discarded plant evaluations; estimator variance is tested with width."
        ),
    )

    def __init__(
        self,
        n: int,
        seed: int,
        *,
        a: float = 0.55,
        c: float = 0.15,
        stability_constant: float = 5.0,
        alpha: float = 0.602,
        gamma: float = 0.101,
        lo: float = -3.0,
        hi: float = 3.0,
    ):
        super().__init__(n, seed, lo, hi)
        self.a = a
        self.c = c
        self.stability_constant = stability_constant
        self.alpha = alpha
        self.gamma = gamma
        self.delta = np.ones(n, dtype=np.float64)
        self._rng = np.random.default_rng(seed)

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {"u": self.u, "delta": self.delta}

    def probe_commands(self) -> tuple[FloatArray, FloatArray, float]:
        iteration = self.update_count + 1
        self.delta[:] = self._rng.choice(np.array([-1.0, 1.0]), size=self.n)
        ck = self.c / (iteration**self.gamma)
        plus = np.clip(self.u + ck * self.delta, self.lo, self.hi)
        minus = np.clip(self.u - ck * self.delta, self.lo, self.hi)
        return plus, minus, ck

    def update_from_probe_losses(
        self, loss_plus: float, loss_minus: float, ck: float
    ) -> FloatArray:
        if ck <= 0 or not np.isfinite(loss_plus + loss_minus):
            raise ValueError("invalid SPSA probe losses")
        iteration = self.update_count + 1
        ak = self.a / ((self.stability_constant + iteration) ** self.alpha)
        gradient = ((loss_plus - loss_minus) / (2.0 * ck)) * self.delta
        self.u[:] = np.clip(self.u - ak * gradient, self.lo, self.hi)
        self.update_count += 1
        return self.u

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        raise RuntimeError("SPSA updates require the runner's two scalar probe losses")


class CommissionedPI(Controller):
    """PI controller given a charged two-acquisition parallel commissioning."""

    metadata = ControllerMetadata(
        name="commissioned_pi",
        information_access="component vectors plus two charged coded commissioning acquisitions",
        commissioned=True,
        ranked=True,
        retained_configuration=True,
        state_class="three float words/channel",
        acquisition_depth_class="O(1) after O(1) coded commissioning in this plant",
        host_arithmetic_class="O(n)",
        host_state_class="O(n) total; O(1) per channel",
        discarded_probe_acquisitions=True,
        minimal_sufficient_cold_start_candidate=False,
        resource_class_note=(
            "Maintenance-floor comparator after charged commissioning; the separate "
            "probe configurations exclude it from the cold-start retained class."
        ),
    )

    def __init__(
        self,
        n: int,
        seed: int,
        *,
        proportional_gain: float = 0.70,
        integral_gain: float = 0.06,
        slope_floor: float = 0.03,
        trust_radius: float = 0.75,
        lo: float = -3.0,
        hi: float = 3.0,
    ):
        super().__init__(n, seed, lo, hi)
        self.proportional_gain = proportional_gain
        self.integral_gain = integral_gain
        self.slope_floor = slope_floor
        self.trust_radius = trust_radius
        self.integral = np.zeros(n, dtype=np.float64)
        self.slope = np.full(n, slope_floor, dtype=np.float64)
        self._is_commissioned = False

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {"u": self.u, "integral": self.integral, "slope": self.slope}

    def set_commissioning(
        self,
        response_minus: FloatArray,
        response_plus: FloatArray,
        code: FloatArray,
        amplitude: float,
    ) -> None:
        if amplitude <= 0 or np.any(np.abs(code) != 1):
            raise ValueError("commissioning requires positive amplitude and +/-1 code")
        raw = (response_plus - response_minus) / (2.0 * amplitude * code)
        sign = np.where(raw < 0, -1.0, 1.0)
        self.slope[:] = sign * np.maximum(np.abs(raw), self.slope_floor)
        self.u.fill(0.0)
        self.integral.fill(0.0)
        self._is_commissioned = True

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        if not self._is_commissioned:
            raise RuntimeError("CommissionedPI must be commissioned before update")
        error = target - response
        self.integral[:] = np.clip(self.integral + error, -1.0, 1.0)
        action = (
            self.proportional_gain * error + self.integral_gain * self.integral
        ) / self.slope
        action = np.clip(action, -self.trust_radius, self.trust_radius)
        self.u[:] = np.clip(self.u + action, self.lo, self.hi)
        self.update_count += 1
        return self.u


class DenseFiniteDifference(Controller):
    """Small-width commissioned full-Jacobian baseline.

    Its ``n+1`` sequential commissioning acquisitions and ``O(n^2)`` retained
    Jacobian are deliberately charged. It is disallowed for large-width tracks.
    """

    metadata = ControllerMetadata(
        name="dense_fd",
        information_access="component vectors from n+1 sequential commissioning acquisitions",
        commissioned=True,
        ranked=True,
        retained_configuration=False,
        state_class="O(n^2) controller state",
        acquisition_depth_class="O(n) commissioning",
        host_arithmetic_class="O(n^3) dense solve as implemented",
        host_state_class="O(n^2)",
        discarded_probe_acquisitions=True,
        minimal_sufficient_cold_start_candidate=False,
        resource_class_note=(
            "Out of class on acquisition depth, retained model state, and host solve cost."
        ),
    )

    def __init__(
        self,
        n: int,
        seed: int,
        *,
        eta: float = 0.80,
        trust_radius: float = 0.40,
        regularization: float = 1e-2,
        lo: float = -3.0,
        hi: float = 3.0,
    ):
        if n > MAX_DENSE_CONTROLLER_WIDTH:
            raise ValueError(
                "dense_fd is deliberately limited to "
                f"n <= {MAX_DENSE_CONTROLLER_WIDTH}; its n+1 commissioning depth, "
                "O(n^2) state, and O(n^3) solve are represented structurally beyond "
                "that width"
            )
        super().__init__(n, seed, lo, hi)
        self.eta = eta
        self.trust_radius = trust_radius
        self.regularization = regularization
        self.jacobian = np.eye(n, dtype=np.float64)
        self._is_commissioned = False

    def mutable_state_arrays(self) -> dict[str, NDArray]:
        return {"u": self.u, "jacobian": self.jacobian}

    def set_commissioning(
        self,
        base_response: FloatArray,
        probe_responses: list[FloatArray],
        amplitude: float,
    ) -> None:
        if len(probe_responses) != self.n or amplitude <= 0:
            raise ValueError("dense finite difference requires n probe responses")
        for column, response in enumerate(probe_responses):
            self.jacobian[:, column] = (response - base_response) / amplitude
        self.u.fill(0.0)
        self._is_commissioned = True

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        if not self._is_commissioned:
            raise RuntimeError("DenseFiniteDifference must be commissioned before update")
        lhs = self.jacobian.T @ self.jacobian + self.regularization * np.eye(self.n)
        rhs = self.jacobian.T @ (target - response)
        action = self.eta * np.linalg.solve(lhs, rhs)
        norm = float(np.linalg.norm(action))
        if norm > self.trust_radius:
            action *= self.trust_radius / norm
        self.u[:] = np.clip(self.u + action, self.lo, self.hi)
        self.update_count += 1
        return self.u


class Oracle(Controller):
    metadata = ControllerMetadata(
        name="oracle",
        information_access="hidden drift, actuator polarity, and gain",
        commissioned=False,
        ranked=False,
        retained_configuration=True,
        state_class="unranked lower bound",
        acquisition_depth_class="O(1)",
        host_arithmetic_class="O(n)",
        host_state_class="hidden plant state supplied by evaluator",
        discarded_probe_acquisitions=False,
        minimal_sufficient_cold_start_candidate=False,
        resource_class_note="Unranked information-access lower bound, not a realizable controller.",
    )

    def set_hidden_state(
        self, drift: FloatArray, polarities: FloatArray, gains: FloatArray
    ) -> FloatArray:
        self.u[:] = np.clip(-drift / (polarities * gains), self.lo, self.hi)
        return self.u

    def update(self, response: FloatArray, target: FloatArray) -> FloatArray:
        self._check_observation(response, target)
        self.update_count += 1
        return self.u


def make_controller(name: str, n: int, seed: int) -> Controller:
    factories = {
        "do_nothing": DoNothing,
        "retained_residual": RetainedResidual,
        "diagonal_secant": DiagonalSecant,
        "anderson_residual": AndersonResidual,
        "full_broyden": FullBroyden,
        "spsa": SPSA,
        "commissioned_pi": CommissionedPI,
        "dense_fd": DenseFiniteDifference,
        "oracle": Oracle,
    }
    try:
        return factories[name](n=n, seed=seed)
    except KeyError as exc:
        raise ValueError(f"unknown controller {name!r}") from exc
