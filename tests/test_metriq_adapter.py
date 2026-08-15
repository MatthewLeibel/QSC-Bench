import argparse
import importlib
import unittest


class MetriqAdapterTests(unittest.TestCase):
    def test_local_adaptive_adapter_dispatches_and_polls(self):
        try:
            module = importlib.import_module("metriq_gym.benchmarks.qsc_bench")
        except (ImportError, ModuleNotFoundError):
            self.skipTest("draft Metriq integration branch is not installed")

        class LocalDevice:
            id = "aer_simulator"

        params = type(
            "Params",
            (),
            {
                "width": 2,
                "seed": 991,
                "controller": "oracle",
                "shots": 64,
                "reference_shots": 256,
                "monitor_rmse_tolerance": 0.12,
                "consecutive_acquisitions": 2,
                "payload_drop_tolerance": 0.12,
                "max_monitor_acquisitions": 8,
                "projected_acquisition_latency_seconds": 0.001,
            },
        )()
        benchmark = module.QSCColdStartBenchmark(argparse.Namespace(), params)
        job_data = benchmark.dispatch_handler(LocalDevice())
        result = benchmark.poll_handler(job_data, [], [])
        self.assertTrue(result.contract_success)
        self.assertEqual(result.acquisitions_to_contract, 2)
        self.assertGreater(result.payload_quality, 0.0)
        self.assertEqual(result.monitor_values_per_acquisition, 2)
        self.assertEqual(result.local_monitor_plus_actuation_values_per_cycle, 4)
        self.assertGreater(result.projected_time_to_contract_seconds, 0.002)
        self.assertIsInstance(result.qsc_git_worktree_dirty, bool)


if __name__ == "__main__":
    unittest.main()
