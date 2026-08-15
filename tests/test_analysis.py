import unittest

from qsc_bench.analysis import analyze_campaign, wilson_interval


class AnalysisTests(unittest.TestCase):
    def test_wilson_interval_is_non_degenerate_for_all_successes(self):
        lower, upper = wilson_interval(30, 30)
        self.assertGreater(lower, 0.85)
        self.assertAlmostEqual(upper, 1.0)

    def test_finite_range_class_test_uses_paired_successes(self):
        records = []
        for width in (16, 64, 256, 1024):
            for seed in range(30):
                records.append(
                    {
                        "width": width,
                        "seed": seed,
                        "controller": "retained_residual",
                        "contract_success": True,
                        "acquisitions_to_contract": 12 + seed % 2,
                        "payload_bitwise_zero_probability_at_entry": 0.98,
                        "payload_quality_threshold": 0.95,
                        "host_update_seconds": width * 1e-8,
                        "wall_runtime_seconds": width * 2e-8,
                        "commissioning_acquisitions": 0,
                        "controller_mutable_state_bytes": width * 48,
                        "controller_metadata": {
                            "minimal_sufficient_cold_start_candidate": True
                        },
                    }
                )
        bundle = {
            "protocol_version": "test",
            "result_label": "FROZEN CONFIRMATION",
            "config_sha256": "abc",
            "config": {"contract": {"max_monitor_acquisitions": 40}},
            "environment": {"git_commit": "abc", "git_worktree_dirty": False},
            "records": records,
        }
        analysis = analyze_campaign(bundle, bootstrap_draws=200, bootstrap_seed=4)
        self.assertEqual(analysis["class_level_result"], "PASS")
        row = analysis["controllers"][0]
        self.assertEqual(row["scaling"]["complete_successful_paired_seed_count"], 30)
        self.assertLessEqual(row["scaling"]["alpha_ci95"][1], 0.05)
        self.assertAlmostEqual(
            row["resource_scaling"]["state_bytes_power_law_exponent"], 1.0
        )


if __name__ == "__main__":
    unittest.main()
