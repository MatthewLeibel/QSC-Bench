import math
import importlib.util
from pathlib import Path
import unittest

import numpy as np
from qiskit import qasm2

from qsc_bench.openquantum_scale import (
    OPENQUANTUM_ARMS,
    OpenQuantumAdaptiveRun,
    build_openquantum_qasm,
    cepheus_native_mirror_protocol,
    cepheus_protocol,
    cepheus_local_protocol,
    cepheus_single_rx_protocol,
    derive_openquantum_scenario,
    render_openquantum_reference_qasm,
    run_openquantum_rehearsal,
    score_openquantum_counts,
    simulate_openquantum_counts,
)


class OpenQuantumScaleTests(unittest.TestCase):
    def test_max_width_uses_108_qubits_as_54_disjoint_pairs(self):
        protocol = cepheus_protocol(54, shots=128, reference_shots=256)
        protocol.validate()
        self.assertEqual(protocol.physical_qubits, 108)
        self.assertEqual(len(protocol.monitor_qubits), 54)
        self.assertEqual(len(protocol.payload_qubits), 54)
        self.assertEqual(len(protocol.payload_edges), 27)
        self.assertEqual(
            set(qubit for edge in protocol.payload_edges for qubit in edge),
            set(protocol.payload_qubits),
        )

    def test_qasm_round_trips_at_both_frozen_widths(self):
        for width in (18, 24, 30, 36, 42, 48, 54):
            with self.subTest(width=width):
                protocol = cepheus_protocol(width, shots=64, reference_shots=128)
                scenario = derive_openquantum_scenario(4100 + width, protocol)
                source = build_openquantum_qasm([0.0] * width, scenario, protocol)
                circuit = qasm2.loads(source)
                self.assertEqual(circuit.num_qubits, 2 * width)
                self.assertEqual(circuit.num_clbits, 2 * width)
                self.assertEqual(source.count("measure q -> c;"), 1)
                self.assertEqual(source.count("cz q["), width)

    def test_reference_is_ideal_in_noiseless_block_model(self):
        protocol = cepheus_protocol(18, shots=512, reference_shots=512)
        source = render_openquantum_reference_qasm(protocol)
        self.assertIn("qreg q[36];", source)
        scenario = derive_openquantum_scenario(22, protocol)
        run = OpenQuantumAdaptiveRun(
            arm="do_nothing",
            seed=22,
            monitor_target=[0.5] * protocol.width,
            payload_reference_bitwise_zero=1.0,
            protocol=protocol,
        )
        request = run.next_request()
        # Check the commanded shock, not the reference circuit, is visibly out of contract.
        counts = simulate_openquantum_counts(
            request, protocol, seed=4, shots=4096, readout_flip=0.0
        )
        scores = score_openquantum_counts(counts, protocol)
        self.assertGreater(scores.monitor_rmse, 0.12)

    def test_count_scoring_uses_qasm_bit_order(self):
        protocol = cepheus_protocol(18, shots=10, reference_shots=10)
        # Set monitor q0 and payload q18 in half the shots.
        value = (1 << 0) | (1 << 18)
        counts = {"0" * 36: 5, f"{value:036b}": 5}
        scores = score_openquantum_counts(counts, protocol)
        self.assertAlmostEqual(scores.monitor_response[0], 0.5)
        self.assertTrue(all(value == 0.0 for value in scores.monitor_response[1:]))
        self.assertAlmostEqual(scores.payload_bitwise_zero, 1.0 - 0.5 / 18.0)

    def test_rehearsal_runs_every_arm_to_the_four_read_deadline(self):
        protocol = cepheus_protocol(18, shots=512, reference_shots=1024)
        for arm in OPENQUANTUM_ARMS:
            with self.subTest(arm=arm):
                result = run_openquantum_rehearsal(
                    arm=arm,
                    seed=2026081518,
                    protocol=protocol,
                )
                self.assertEqual(len(result["trace"]), 4)
                self.assertEqual(
                    result["dense_fd_structural_minimum_acquisitions_to_confirm"],
                    21,
                )
                self.assertTrue(math.isfinite(result["total_controller_update_seconds"]))

    def test_scenario_shock_rms_is_exact_at_max_width(self):
        protocol = cepheus_protocol(54, shots=64, reference_shots=64)
        scenario = derive_openquantum_scenario(2026081554, protocol)
        observed = float(np.sqrt(np.mean(np.square(scenario.disturbance))))
        self.assertAlmostEqual(observed, protocol.initial_shock_rms, places=12)

    def test_local_payload_has_no_cz_and_rehearses_at_96_physical_qubits(self):
        protocol = cepheus_local_protocol(48, shots=512, reference_shots=1024)
        scenario = derive_openquantum_scenario(2026082248, protocol)
        source = build_openquantum_qasm([0.0] * protocol.width, scenario, protocol)
        circuit = qasm2.loads(source)
        self.assertEqual(circuit.num_qubits, 96)
        self.assertEqual(source.count("cz q["), 0)
        result = run_openquantum_rehearsal(
            arm="retained_residual",
            seed=2026082248,
            protocol=protocol,
        )
        self.assertTrue(result["contract_success"])
        self.assertEqual(result["contract_entry_acquisition"], 4)
        self.assertGreater(result["reference"]["payload_bitwise_zero"], 0.90)

    def test_native_mirror_uses_all_96_qubits_with_informative_remap(self):
        protocol = cepheus_native_mirror_protocol(shots=512, reference_shots=1024)
        source = render_openquantum_reference_qasm(protocol)
        circuit = qasm2.loads(source)
        self.assertEqual(circuit.num_qubits, 96)
        self.assertEqual(
            set(protocol.monitor_qubits) | set(protocol.payload_qubits), set(range(96))
        )
        self.assertFalse(set(protocol.monitor_qubits) & set(protocol.payload_qubits))
        self.assertNotIn(16, protocol.monitor_qubits)
        self.assertNotIn(40, protocol.monitor_qubits)
        self.assertNotIn(43, protocol.monitor_qubits)
        self.assertEqual(source.count("cz q["), 0)
        self.assertEqual(source.count("rx("), 96)
        self.assertEqual(source.count("rz("), 96)
        result = run_openquantum_rehearsal(
            arm="retained_residual",
            seed=109376490,
            protocol=protocol,
        )
        self.assertTrue(result["contract_success"])
        self.assertEqual(result["contract_entry_acquisition"], 4)
        self.assertGreater(result["reference"]["payload_bitwise_zero"], 0.90)

    def test_native_mirror_payload_is_sensitive_to_commanded_phase_error(self):
        protocol = cepheus_native_mirror_protocol(shots=4096, reference_shots=4096)
        scenario = derive_openquantum_scenario(109376490, protocol)
        run = OpenQuantumAdaptiveRun(
            arm="do_nothing",
            seed=109376490,
            monitor_target=[0.5] * protocol.width,
            payload_reference_bitwise_zero=1.0,
            protocol=protocol,
        )
        request = run.next_request()
        counts = simulate_openquantum_counts(
            request, protocol, seed=17, shots=4096, readout_flip=0.0
        )
        scores = score_openquantum_counts(counts, protocol)
        self.assertLess(scores.payload_bitwise_zero, 0.78)

    def test_single_rx_payload_is_short_identity_and_error_sensitive(self):
        protocol = cepheus_single_rx_protocol(shots=4096, reference_shots=4096)
        reference = render_openquantum_reference_qasm(protocol)
        circuit = qasm2.loads(reference)
        self.assertEqual(circuit.num_qubits, 96)
        self.assertEqual(reference.count("cz q["), 0)
        self.assertEqual(reference.count("rx("), 48)
        self.assertEqual(reference.count("rz("), 48)
        development_seed = 2026082401
        retained = run_openquantum_rehearsal(
            arm="retained_residual",
            seed=development_seed,
            protocol=protocol,
        )
        no_control = run_openquantum_rehearsal(
            arm="do_nothing",
            seed=development_seed,
            protocol=protocol,
        )
        self.assertTrue(retained["contract_success"])
        self.assertEqual(retained["contract_entry_acquisition"], 4)
        self.assertFalse(no_control["contract_success"])
        self.assertGreater(retained["reference"]["payload_bitwise_zero"], 0.90)

    def test_provider_retry_exhaustion_is_a_narrow_transient_class(self):
        script = Path(__file__).parents[1] / "scripts" / "run_openquantum_scale_campaign.py"
        spec = importlib.util.spec_from_file_location("openquantum_scale_runner", script)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        base = {
            "preparation": {"status": "Completed"},
            "job": {
                "status": "Failed",
                "message": "Execution failed after 3 attempts",
            },
        }
        self.assertTrue(module.is_verified_transient_execution_failure(base))
        compile_failure = {
            "preparation": {"status": "Failed"},
            "job": {"status": "Failed", "message": "invalid circuit"},
        }
        self.assertFalse(module.is_verified_transient_execution_failure(compile_failure))


if __name__ == "__main__":
    unittest.main()
