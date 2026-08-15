import json
from pathlib import Path
import tempfile
import unittest

from qsc_bench.scaling import build_architecture_projection


class ArchitectureProjectionTests(unittest.TestCase):
    def test_projection_separates_anchor_from_structural_baseline(self):
        measured = {
            "development_run": True,
            "result_label": "DEVELOPMENT / NOT FOR PUBLICATION",
            "protocol_version": "test",
            "records": [
                {
                    "controller": "retained_residual",
                    "width": 8,
                    "contract_success": True,
                    "acquisitions_to_contract": 5,
                    "controller_metadata": {
                        "minimal_sufficient_cold_start_candidate": True
                    },
                },
                {
                    "controller": "retained_residual",
                    "width": 16,
                    "contract_success": True,
                    "acquisitions_to_contract": 6,
                    "controller_metadata": {
                        "minimal_sufficient_cold_start_candidate": True
                    },
                },
                {
                    "controller": "dense_fd",
                    "width": 8,
                    "contract_success": True,
                    "acquisitions_to_contract": 12,
                    "controller_metadata": {
                        "minimal_sufficient_cold_start_candidate": False
                    },
                },
                {
                    "controller": "diagonal_secant",
                    "width": 8,
                    "contract_success": True,
                    "acquisitions_to_contract": 7,
                    "controller_metadata": {
                        "minimal_sufficient_cold_start_candidate": True
                    },
                },
                {
                    "controller": "diagonal_secant",
                    "width": 16,
                    "contract_success": False,
                    "acquisitions_to_contract": None,
                    "controller_metadata": {
                        "minimal_sufficient_cold_start_candidate": True
                    },
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "measured.json"
            source.write_text(json.dumps(measured), encoding="utf-8")
            result = build_architecture_projection(
                source,
                widths=(100,),
                latencies_seconds=(1e-3,),
                confirmation_depth=3,
            )

        anchor = result["measured_anchor_summary"][0]
        self.assertEqual(anchor["projection_anchor_acquisitions"], 6)
        methods = {row["method"]: row for row in result["projection_rows"][0]["methods"]}
        self.assertEqual(methods["retained_residual"]["sequential_acquisitions"], 6)
        self.assertNotIn("diagonal_secant", methods)
        self.assertEqual(
            methods["dense_finite_difference_best_case_verified"]["sequential_acquisitions"],
            104,
        )
        self.assertAlmostEqual(
            methods["dense_finite_difference_best_case_verified"]["times"][0][
                "acquisition_only_seconds"
            ],
            0.104,
        )
        self.assertIn("not an executed", methods["dense_finite_difference_best_case_verified"]["evidence_kind"])


if __name__ == "__main__":
    unittest.main()
