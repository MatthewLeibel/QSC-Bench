"""Contract-entry and payload-validation semantics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def response_rmse(response: FloatArray, target: FloatArray) -> float:
    response = np.asarray(response, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if response.shape != target.shape:
        raise ValueError("response and target shapes differ")
    return float(np.sqrt(np.mean(np.square(response - target))))


@dataclass
class ContractTracker:
    monitor_tolerance: float
    required_consecutive: int
    payload_threshold: float
    streak: int = 0
    candidate_entries: int = 0

    def observe_monitor(self, rmse: float) -> bool:
        if rmse <= self.monitor_tolerance:
            self.streak += 1
        else:
            self.streak = 0
        if self.streak >= self.required_consecutive:
            self.candidate_entries += 1
            return True
        return False

    def observe_payload(self, quality: float) -> bool:
        passed = quality >= self.payload_threshold
        if not passed:
            self.streak = 0
        return passed

