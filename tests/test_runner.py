import unittest

from qsc_bench.config import (
    BenchmarkConfig,
    ContractConfig,
    ControllerConfig,
    NoiseConfig,
    PlantConfig,
)
from qsc_bench.runner import run_suite


class RunnerTests(unittest.TestCase):
    def test_tiny_adaptive_run_produces_machine_readable_records(self):
        config = BenchmarkConfig(
            development_run=True,
            widths=(2,),
            seeds=(77,),
            shots=128,
            reference_shots=512,
            contract=ContractConfig(
                monitor_rmse_tolerance=0.08,
                consecutive_acquisitions=2,
                payload_drop_tolerance=0.08,
                max_monitor_acquisitions=10,
            ),
            controllers=ControllerConfig(names=("retained_residual", "oracle")),
        )
        bundle = run_suite(config)
        self.assertEqual(len(bundle["records"]), 2)
        self.assertTrue(all(record["status"] != "ERROR" for record in bundle["records"]))
        oracle = next(record for record in bundle["records"] if record["controller"] == "oracle")
        self.assertTrue(oracle["contract_success"])
        self.assertFalse(oracle["ranked"])

    def test_spsa_probe_acquisitions_are_charged(self):
        config = BenchmarkConfig(
            development_run=True,
            widths=(4,),
            seeds=(91,),
            shots=128,
            reference_shots=512,
            plant=PlantConfig(
                backend="analytic_ring",
                payload_kind="local_mirror",
                noise=NoiseConfig(0.0, 0.0, 0.005),
            ),
            contract=ContractConfig(
                monitor_rmse_tolerance=0.04,
                consecutive_acquisitions=2,
                payload_drop_tolerance=0.08,
                max_monitor_acquisitions=12,
            ),
            controllers=ControllerConfig(names=("spsa",)),
        )
        record = run_suite(config)["records"][0]
        self.assertNotEqual(record["status"], "ERROR")
        self.assertGreater(record["probe_acquisitions"], 0)
        self.assertEqual(
            record["total_monitor_acquisitions"],
            record["ordinary_monitor_acquisitions"] + record["probe_acquisitions"],
        )


if __name__ == "__main__":
    unittest.main()
