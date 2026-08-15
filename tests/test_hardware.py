import math
import unittest
from types import SimpleNamespace

import numpy as np

from qsc_bench.hardware import (
    HARDWARE_ARMS,
    HardwareAcquisitionRecord,
    QIHardwareProtocol,
    build_qi_acquisition_circuit,
    build_qi_cqasm,
    derive_hardware_scenario,
    effective_phase_error,
    hardware_contract_at_deadline,
    hardware_contract_entry,
    make_hardware_noise_model,
    reference_payload_threshold,
    run_hardware_dry_run,
    run_retained_hardware_dry_run,
    score_acquisition_counts,
)
from qsc_bench.qi_provider import (
    render_qi_hybrid_program,
    render_qi_reference_cqasm,
)
from qsc_bench.hardware_results import (
    normalize_qi_hybrid_capture,
    normalize_qi_reference,
    normalize_qi_sequential_run,
)


class HardwareProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = QIHardwareProtocol(shots=512)
        self.scenario = derive_hardware_scenario(2026081401, self.protocol)

    def test_layout_excludes_reported_tls_qubit(self):
        self.protocol.validate()
        self.assertNotIn(8, self.protocol.monitor_qubits + self.protocol.payload_qubits)
        self.assertEqual(len(set(self.protocol.monitor_qubits + self.protocol.payload_qubits)), 8)

    def test_scenario_has_declared_shock_rms(self):
        rms = float(np.sqrt(np.mean(np.square(self.scenario.disturbance))))
        self.assertAlmostEqual(rms, self.protocol.initial_shock_rms, places=12)

    def test_qiskit_and_cqasm_use_same_effective_angles(self):
        command = np.array([0.1, -0.2, 0.3, -0.4])
        phase = effective_phase_error(command, self.scenario)
        circuit = build_qi_acquisition_circuit(command, self.scenario, self.protocol)
        cqasm = build_qi_cqasm(command, self.scenario, self.protocol)
        for logical, qubit in enumerate(self.protocol.monitor_qubits):
            expected = self.protocol.base_angle + phase[logical]
            self.assertIn(f"Rz({expected:.16g}) q[{qubit}]", cqasm)
        self.assertEqual(circuit.num_qubits, 9)
        self.assertEqual(circuit.num_clbits, 9)
        self.assertEqual(cqasm.count(" = measure "), 8)
        self.assertEqual(cqasm.count("CZ "), 6)

    def test_count_scoring_accepts_binary_hex_and_decimal(self):
        # 180 sets every monitor qubit; 75 sets every payload qubit.
        binary = score_acquisition_counts({"000000000": 4, "001001011": 4}, self.protocol)
        hexa = score_acquisition_counts({"0x0": 4, "0x4b": 4}, self.protocol)
        decimal = score_acquisition_counts({"0": 4, "75": 4}, self.protocol)
        self.assertEqual(binary, hexa)
        self.assertEqual(binary, decimal)
        self.assertTrue(all(math.isclose(value, 0.0) for value in binary.monitor_response))
        self.assertEqual(binary.payload_bitwise_zero, 0.5)

    def test_dry_run_executes_five_acquisitions(self):
        result = run_retained_hardware_dry_run(
            seed=2026081402,
            protocol=self.protocol,
            noise_model=make_hardware_noise_model(),
        )
        self.assertEqual(len(result["trace"]), self.protocol.acquisitions)
        self.assertTrue(all(len(row["command"]) == self.protocol.width for row in result["trace"]))
        self.assertIsInstance(result["contract_success"], bool)

    def test_contract_requires_both_monitor_and_payload(self):
        result = run_retained_hardware_dry_run(
            seed=2026081403,
            protocol=self.protocol,
            noise_model=None,
        )
        rows = result["trace"]
        reconstructed = [HardwareAcquisitionRecord(**row) for row in rows]
        observed = hardware_contract_entry(reconstructed, self.protocol)
        at_deadline = hardware_contract_at_deadline(reconstructed, self.protocol)
        self.assertEqual(observed, result["contract_entry_acquisition"])
        self.assertEqual(at_deadline, result["contract_at_deadline"])

    def test_all_ranked_hardware_arms_follow_five_acquisition_budget(self):
        for arm in HARDWARE_ARMS:
            with self.subTest(arm=arm):
                result = run_hardware_dry_run(
                    arm=arm,
                    seed=2026081410,
                    protocol=self.protocol,
                    noise_model=None,
                )
                self.assertEqual(len(result["trace"]), 5)
                self.assertEqual(
                    result["ordinary_acquisitions"]
                    + result["discarded_probe_acquisitions"],
                    5,
                )

    def test_dense_fd_exposes_structural_deadline_ceiling(self):
        result = run_hardware_dry_run(
            arm="dense_fd",
            seed=2026081411,
            protocol=self.protocol,
            noise_model=None,
        )
        self.assertEqual(result["structural_minimum_acquisitions_to_confirm"], 7)
        self.assertEqual(result["ordinary_acquisitions"], 0)
        self.assertFalse(result["contract_success"])

    def test_payload_reference_rule_is_fixed_margin_with_absolute_floor(self):
        self.assertAlmostEqual(reference_payload_threshold(0.94, self.protocol), 0.84)
        self.assertAlmostEqual(reference_payload_threshold(0.72, self.protocol), 0.70)

    def test_reference_artifact_is_zero_disturbance_circuit(self):
        cqasm = render_qi_reference_cqasm(self.protocol)
        self.assertEqual(cqasm.count(" = measure "), 8)
        for qubit in self.protocol.monitor_qubits:
            self.assertIn(f"Rz({self.protocol.base_angle:.16g}) q[{qubit}]", cqasm)

    def test_each_hybrid_artifact_is_self_contained_and_calls_qpu_five_times(self):
        class FakeQI:
            def __init__(self):
                self.circuits = []

            def execute_circuit(self, circuit, number_of_shots):
                self.circuits.append(circuit)
                half = number_of_shots // 2
                return SimpleNamespace(
                    results={"000000000": half, "010110100": number_of_shots - half},
                    shots_requested=number_of_shots,
                    shots_done=number_of_shots,
                )

        for arm in HARDWARE_ARMS:
            with self.subTest(arm=arm):
                source = render_qi_hybrid_program(
                    arm=arm,
                    seed=2026081420,
                    monitor_target=[0.5] * self.protocol.width,
                    payload_reference_bitwise_zero=1.0,
                    protocol=self.protocol,
                )
                compile(source, f"<{arm}>", "exec")
                namespace = {}
                executable = source.replace(
                    "from qi2_shared.hybrid.quantum_interface import QuantumInterface",
                    "QuantumInterface = object",
                )
                exec(compile(executable, f"<{arm}>", "exec"), namespace)
                qi = FakeQI()
                namespace["execute"](qi)
                final = namespace["finalize"]([])
                self.assertEqual(len(qi.circuits), 5)
                self.assertEqual(len(final["trace"]), 5)
                self.assertEqual(final["arm"], arm)
                self.assertTrue(all("version 3.0" in circuit for circuit in qi.circuits))

    def test_independent_capture_normalizer_recomputes_contract(self):
        reference_capture = {
            "job": {
                "id": 10,
                "status": "completed",
                "created_on": "2026-08-14T00:00:00+00:00",
                "queued_at": "2026-08-14T00:00:01+00:00",
                "finished_at": "2026-08-14T00:00:03+00:00",
            },
            "results": [
                {
                    "results": {"000000000": 256, "010110100": 256},
                    "shots_requested": 512,
                    "shots_done": 512,
                    "execution_time_in_seconds": 0.5,
                }
            ],
        }
        reference = normalize_qi_reference(reference_capture, self.protocol)
        self.assertEqual(reference["monitor_target"], [0.5] * 4)
        self.assertEqual(reference["payload_reference_bitwise_zero"], 1.0)
        self.assertEqual(reference["timing"]["create_to_finish_seconds"], 3.0)

        trace = []
        for acquisition in range(1, 6):
            trace.append(
                {
                    "acquisition": acquisition,
                    "contract_eligible": True,
                    "monitor_rmse": 0.01,
                    "payload_bitwise_zero": 0.95,
                    "shots_requested": 512,
                    "shots_done": 512,
                    "hybrid_execute_call_seconds": 0.2,
                    "controller_update_seconds": 1e-5,
                }
            )
        hybrid_capture = {
            "job": {
                "id": 11,
                "status": "completed",
                "created_on": "2026-08-14T00:00:00+00:00",
                "queued_at": "2026-08-14T00:00:01+00:00",
                "finished_at": "2026-08-14T00:00:04+00:00",
            },
            "results": [],
            "final_result": {
                "final_result": {
                    "arm": "retained_residual",
                    "seed": 1,
                    "trace": trace,
                    "payload_threshold": 0.90,
                    "contract_entry_acquisition": 2,
                    "contract_at_deadline": True,
                    "server_total_elapsed_seconds": 1.2,
                    "structural_minimum_acquisitions_to_confirm": 2,
                }
            },
        }
        normalized = normalize_qi_hybrid_capture(hybrid_capture, self.protocol)
        self.assertEqual(normalized["contract_entry_acquisition"], 2)
        self.assertTrue(normalized["contract_at_deadline"])
        self.assertAlmostEqual(normalized["hybrid_execute_call_seconds"], 1.0)

        sequential_calls = []
        for acquisition in range(1, 6):
            job_id = 100 + acquisition
            direct_capture = {
                "job": {
                    "id": job_id,
                    "status": "completed",
                    "created_on": "2026-08-14T00:00:00+00:00",
                    "queued_at": "2026-08-14T00:00:01+00:00",
                    "finished_at": "2026-08-14T00:00:03+00:00",
                },
                "results": [
                    {
                        "results": {"000000000": 256, "010110100": 256},
                        "shots_requested": 512,
                        "shots_done": 512,
                        "execution_time_in_seconds": 0.5,
                    }
                ],
                "final_result": None,
            }
            sequential_calls.append(
                {
                    "acquisition": acquisition,
                    "selected_job_id": job_id,
                    "attempts": [direct_capture],
                }
            )
        sequential = normalize_qi_sequential_run(
            {
                "capture_schema": "qsc-qi-sequential-hardware-run-v1",
                "source_sha256": "0" * 64,
                "completed_at": "2026-08-14T00:00:05+00:00",
                "client_wall_seconds": 20.0,
                "sequential_calls": sequential_calls,
                "final_result": hybrid_capture["final_result"]["final_result"],
            },
            self.protocol,
        )
        self.assertEqual(sequential["selected_job_ids"], [101, 102, 103, 104, 105])
        self.assertEqual(sequential["provider_execution_seconds_total"], 2.5)
        self.assertEqual(sequential["provider_execution_seconds_to_contract"], 1.0)
        self.assertEqual(
            sequential["provider_job_create_to_finish_seconds_total"], 15.0
        )
        self.assertEqual(
            sequential["provider_job_create_to_finish_seconds_to_contract"], 6.0
        )


if __name__ == "__main__":
    unittest.main()
