import unittest

import numpy as np

from qsc_bench.controllers import (
    AndersonResidual,
    CommissionedPI,
    DenseFiniteDifference,
    DiagonalSecant,
    FullBroyden,
    RetainedResidual,
    SPSA,
)


class ControllerStateTests(unittest.TestCase):
    def test_retained_reference_has_exact_six_float_words_per_channel(self):
        n = 17
        controller = RetainedResidual(n=n, seed=9)
        self.assertEqual(
            set(controller.mutable_state_arrays()),
            {"u", "u_prev", "last_action", "last_response", "correlation", "gain_hat"},
        )
        self.assertEqual(controller.mutable_float_words(), 6 * n)
        self.assertEqual(controller.mutable_float_words_per_channel(), 6.0)
        self.assertEqual(controller.id_sign.dtype, np.int8)

    def test_retained_controller_updates_without_separate_polarity_cache(self):
        controller = RetainedResidual(n=4, seed=3)
        target = np.full(4, 0.5)
        controller.update(np.array([0.2, 0.3, 0.6, 0.7]), target)
        controller.update(np.array([0.3, 0.2, 0.5, 0.8]), target)
        self.assertTrue(np.all(np.isfinite(controller.u)))
        self.assertFalse(hasattr(controller, "shat"))

    def test_dense_fd_exposes_quadratic_state(self):
        n = 11
        controller = DenseFiniteDifference(n=n, seed=0)
        self.assertEqual(controller.mutable_float_words(), n * n + n)
        self.assertEqual(controller.mutable_float_words_per_channel(), n + 1)

    def test_resource_class_membership_is_controller_form_specific(self):
        retained = RetainedResidual(n=7, seed=4)
        secant = DiagonalSecant(n=7, seed=4)
        pi = CommissionedPI(n=7, seed=4)
        dense = DenseFiniteDifference(n=7, seed=4)
        anderson = AndersonResidual(n=7, seed=4)
        full_broyden = FullBroyden(n=7, seed=4)
        spsa = SPSA(n=7, seed=4)
        self.assertTrue(retained.metadata.minimal_sufficient_cold_start_candidate)
        self.assertTrue(secant.metadata.minimal_sufficient_cold_start_candidate)
        self.assertTrue(anderson.metadata.minimal_sufficient_cold_start_candidate)
        self.assertFalse(pi.metadata.minimal_sufficient_cold_start_candidate)
        self.assertFalse(dense.metadata.minimal_sufficient_cold_start_candidate)
        self.assertFalse(full_broyden.metadata.minimal_sufficient_cold_start_candidate)
        self.assertFalse(spsa.metadata.minimal_sufficient_cold_start_candidate)
        self.assertEqual(secant.metadata.host_state_class, "O(n) total; O(1) per channel")
        self.assertEqual(dense.metadata.host_state_class, "O(n^2)")

    def test_new_controller_state_scaling_is_explicit(self):
        n = 9
        anderson = AndersonResidual(n=n, seed=1, window=5)
        full_broyden = FullBroyden(n=n, seed=1)
        spsa = SPSA(n=n, seed=1)
        self.assertEqual(anderson.mutable_float_words(), 16 * n)
        self.assertEqual(full_broyden.mutable_float_words(), n * n + 3 * n)
        self.assertEqual(spsa.mutable_float_words(), 2 * n)

    def test_dense_controller_width_guard(self):
        for controller_type in (FullBroyden, DenseFiniteDifference):
            with self.subTest(controller=controller_type.__name__):
                with self.assertRaisesRegex(ValueError, "deliberately limited"):
                    controller_type(n=513, seed=1)


if __name__ == "__main__":
    unittest.main()
