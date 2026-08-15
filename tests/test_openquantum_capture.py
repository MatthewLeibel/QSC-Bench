from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "collect_openquantum_job.py"
SPEC = importlib.util.spec_from_file_location("collect_openquantum_job", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@dataclass
class DummyJob:
    id: str = "job-1"
    status: str = "Completed"
    input_data_url: str = "https://signed.example/input?secret=yes"
    output_data_url: str = "https://signed.example/output?secret=yes"
    calibration_data_url: str = "https://signed.example/cal?secret=yes"
    job_preparation_id: str = "prep-1"
    execution_plan_id: str = "public"
    queue_priority_id: str = "standard"
    message: str | None = None
    transaction_id: str | None = "txn-1"
    submitted_at: str | None = "2026-08-14T00:00:00Z"


class OpenQuantumCaptureTest(unittest.TestCase):
    def test_public_job_excludes_signed_urls(self) -> None:
        public = MODULE._public_job(DummyJob())
        self.assertEqual(public["id"], "job-1")
        self.assertNotIn("input_data_url", public)
        self.assertNotIn("output_data_url", public)
        self.assertNotIn("calibration_data_url", public)
        self.assertNotIn("secret=yes", repr(public))


if __name__ == "__main__":
    unittest.main()
