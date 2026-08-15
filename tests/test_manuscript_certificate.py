import unittest

import numpy as np


class ManuscriptCertificateTests(unittest.TestCase):
    def test_disclosed_diagonal_sector_certificate(self):
        momentum = 0.15
        alpha = 0.765
        certificate = np.array([[1.0, -0.275], [-0.275, 0.15]], dtype=np.float64)
        eigenvalues = np.linalg.eigvalsh(certificate)
        self.assertGreater(float(eigenvalues[0]), 0.0)
        self.assertAlmostEqual(float(eigenvalues[-1] / eigenvalues[0]), 15.72, delta=0.02)
        for loop_gain in (0.20, 1.00):
            lifted = np.array(
                [[1.0 + momentum - loop_gain, -momentum], [1.0, 0.0]],
                dtype=np.float64,
            )
            margin = alpha**2 * certificate - lifted.T @ certificate @ lifted
            with self.subTest(loop_gain=loop_gain):
                self.assertGreater(float(np.min(np.linalg.eigvalsh(margin))), 7e-5)


if __name__ == "__main__":
    unittest.main()

