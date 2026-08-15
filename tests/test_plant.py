import unittest

import numpy as np

from qsc_bench.config import NoiseConfig, PlantConfig
from qsc_bench.plant import AnalyticRingPlant, QuantumStabilityPlant


class PlantTests(unittest.TestCase):
    def test_reference_targets_are_reproducible(self):
        first = QuantumStabilityPlant(4, 1234, PlantConfig())
        second = QuantumStabilityPlant(4, 1234, PlantConfig())
        np.testing.assert_array_equal(
            first.reference_monitor_target(256), second.reference_monitor_target(256)
        )

    def test_main_track_is_informative_and_diagonally_dominant(self):
        plant = QuantumStabilityPlant(4, 1234, PlantConfig(coupling_radians=0.05))
        diagnostics = plant.local_jacobian_diagnostics()
        self.assertGreater(diagnostics.minimum_diagonal_magnitude, 0.02)
        self.assertLess(diagnostics.maximum_row_offdiag_to_diag_ratio, 1.0)
        off_diagonal = diagnostics.jacobian - np.diag(np.diag(diagnostics.jacobian))
        self.assertGreater(float(np.max(np.abs(off_diagonal))), 1e-3)

    def test_one_acquisition_returns_every_component(self):
        plant = QuantumStabilityPlant(4, 55, PlantConfig())
        acquisition = plant.acquire_monitor(np.zeros(4), 128)
        self.assertEqual(acquisition.response.shape, (4,))
        self.assertTrue(np.all((0 <= acquisition.response) & (acquisition.response <= 1)))

    def test_analytic_ring_matches_exact_ideal_marginals(self):
        config = PlantConfig(
            backend="analytic_ring",
            payload_kind="local_mirror",
            noise=NoiseConfig(0.0, 0.0, 0.0),
        )
        for width in (1, 2, 3, 4, 8):
            analytic = AnalyticRingPlant(width, 991, config)
            aer = QuantumStabilityPlant(
                width,
                991,
                PlantConfig(
                    backend="aer",
                    payload_kind="local_mirror",
                    noise=NoiseConfig(0.0, 0.0, 0.0),
                    simulator_method="statevector",
                ),
            )
            phase = np.linspace(-0.4, 0.5, width)
            np.testing.assert_allclose(
                analytic.ideal_monitor_response(phase),
                aer.ideal_monitor_response(phase),
                rtol=0.0,
                atol=3e-14,
            )

    def test_analytic_jacobian_matches_finite_difference(self):
        config = PlantConfig(
            backend="analytic_ring",
            payload_kind="local_mirror",
            noise=NoiseConfig(0.0, 0.0, 0.005),
        )
        plant = AnalyticRingPlant(8, 177, config)
        diagnostics = plant.local_jacobian_diagnostics()
        self.assertIsNotNone(diagnostics.jacobian)
        step = 1e-6
        base = plant._readout_probabilities(plant.ideal_monitor_response(np.zeros(8)))
        finite = np.empty((8, 8))
        for channel in range(8):
            phase = np.zeros(8)
            phase[channel] = step
            shifted = plant._readout_probabilities(plant.ideal_monitor_response(phase))
            finite[:, channel] = (shifted - base) / step
        np.testing.assert_allclose(diagnostics.jacobian, finite, atol=3e-7, rtol=3e-6)


if __name__ == "__main__":
    unittest.main()
