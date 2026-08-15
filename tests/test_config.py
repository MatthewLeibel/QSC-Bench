import json
from pathlib import Path
import unittest

from qsc_bench.config import BenchmarkConfig, ContractConfig, ControllerConfig, load_config


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_all_bundled_configs_validate(self):
        for path in sorted((ROOT / "configs").glob("*.json")):
            with self.subTest(path=path.name):
                config = load_config(path)
                self.assertEqual(config.benchmark_name, "QSC-Bench Cold Start")

    def test_public_schema_is_json(self):
        path = ROOT / "schemas" / "qsc_bench_cold_start.schema.json"
        schema = json.loads(path.read_text())
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_dense_controllers_are_rejected_beyond_safe_execution_width(self):
        config = BenchmarkConfig(
            widths=(513,),
            contract=ContractConfig(max_monitor_acquisitions=600),
            controllers=ControllerConfig(names=("full_broyden",)),
        )
        with self.assertRaisesRegex(ValueError, "structural resource projections"):
            config.validate()

    def test_dense_fd_budget_must_include_commissioning_and_confirmation(self):
        config = BenchmarkConfig(
            widths=(16,),
            contract=ContractConfig(
                consecutive_acquisitions=3, max_monitor_acquisitions=19
            ),
            controllers=ControllerConfig(names=("dense_fd",)),
        )
        with self.assertRaisesRegex(ValueError, r"n\+1 charged commissioning"):
            config.validate()


if __name__ == "__main__":
    unittest.main()
