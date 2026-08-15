"""Quantum Inspire artifacts for the QSC-Bench hardware-transfer track.

Generated hybrid programs are self-contained and use only the Python standard
library plus Quantum Inspire's ``QuantumInterface``.  No credential, token, or
provider-private calibration value is embedded in an artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import textwrap
from typing import Any, Sequence

from .hardware import (
    HARDWARE_ARMS,
    HardwareArm,
    QIHardwareProtocol,
    build_qi_cqasm,
    derive_hardware_scenario,
    reference_hardware_scenario,
    reference_payload_threshold,
)


def render_qi_reference_cqasm(protocol: QIHardwareProtocol | None = None) -> str:
    """Render the no-command circuit used to publish the Tuna-9 contract target."""

    protocol = protocol or QIHardwareProtocol()
    protocol.validate()
    return build_qi_cqasm(
        [0.0] * protocol.width,
        reference_hardware_scenario(protocol),
        protocol,
    )


def render_qi_hybrid_program(
    *,
    arm: HardwareArm,
    seed: int,
    monitor_target: Sequence[float],
    payload_reference_bitwise_zero: float,
    protocol: QIHardwareProtocol | None = None,
) -> str:
    """Render one adaptive, five-acquisition Quantum Inspire hybrid program."""

    protocol = protocol or QIHardwareProtocol()
    protocol.validate()
    if arm not in HARDWARE_ARMS:
        raise ValueError(f"unsupported hardware arm: {arm}")
    if len(monitor_target) != protocol.width:
        raise ValueError("monitor target does not match hardware width")
    scenario = derive_hardware_scenario(seed, protocol)
    configuration: dict[str, Any] = {
        "schema_version": "qsc-hardware-transfer-v1-development",
        "arm": arm,
        "seed": int(seed),
        "protocol": protocol.public_dict(),
        "scenario": scenario.public_dict(),
        "monitor_target": [float(value) for value in monitor_target],
        "payload_reference_bitwise_zero": float(payload_reference_bitwise_zero),
        "payload_threshold": reference_payload_threshold(
            float(payload_reference_bitwise_zero), protocol
        ),
        "scope": (
            "hardware-in-the-loop commanded phase restoration with native QPU noise; "
            "not provider-private calibration-register control"
        ),
    }
    encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":"))
    prelude = "import json\nCFG = json.loads(" + repr(encoded) + ")\n\n"
    body = textwrap.dedent(
        r'''
        import math
        import time
        from qi2_shared.hybrid.quantum_interface import QuantumInterface

        TRACE = []
        FINAL = {}


        def _clip(value, low, high):
            return min(high, max(low, value))


        def _sign(value):
            if value < 0.0:
                return -1.0
            if value > 0.0:
                return 1.0
            return 0.0


        def _count_key_to_int(raw_key):
            key = str(raw_key).strip().replace(" ", "").replace("_", "")
            if key.startswith(("0x", "0X")):
                return int(key, 16)
            if key.startswith(("0b", "0B")):
                return int(key, 2)
            if key and set(key) <= {"0", "1"}:
                return int(key, 2)
            return int(key, 10)


        def _effective_error(command):
            scenario = CFG["scenario"]
            return [
                scenario["disturbance"][i]
                + scenario["polarity"][i] * scenario["gain"][i] * command[i]
                for i in range(CFG["protocol"]["width"])
            ]


        def _build_cqasm(command):
            protocol = CFG["protocol"]
            phase_error = _effective_error(command)
            lines = [
                "version 3.0",
                "",
                "qubit[%d] q" % protocol["physical_qubits"],
                "bit[%d] b" % protocol["physical_qubits"],
                "",
            ]
            for qubit in protocol["monitor_qubits"] + protocol["payload_qubits"]:
                lines.append("init q[%d]" % qubit)
            for logical, qubit in enumerate(protocol["monitor_qubits"]):
                lines.append("H q[%d]" % qubit)
                lines.append(
                    "Rz(%.16g) q[%d]"
                    % (protocol["base_angle"] + phase_error[logical], qubit)
                )
                lines.append("H q[%d]" % qubit)
            for logical, qubit in enumerate(protocol["payload_qubits"]):
                lines.append("Ry(%.16g) q[%d]" % (protocol["payload_ry"][logical], qubit))
            for left, right in protocol["payload_edges"]:
                lines.append("CZ q[%d], q[%d]" % (left, right))
            for logical, qubit in enumerate(protocol["payload_qubits"]):
                local_rx = protocol["payload_rx"][logical]
                angle = protocol["payload_error_amplification"] * phase_error[logical]
                lines.append("Rx(%.16g) q[%d]" % (local_rx, qubit))
                lines.append("Rz(%.16g) q[%d]" % (angle, qubit))
                lines.append("Rx(%.16g) q[%d]" % (-local_rx, qubit))
            for left, right in reversed(protocol["payload_edges"]):
                lines.append("CZ q[%d], q[%d]" % (left, right))
            for logical, qubit in enumerate(protocol["payload_qubits"]):
                lines.append("Ry(%.16g) q[%d]" % (-protocol["payload_ry"][logical], qubit))
            for logical, qubit in enumerate(protocol["monitor_qubits"]):
                lines.append("b[%d] = measure q[%d]" % (qubit, qubit))
            for logical, qubit in enumerate(protocol["payload_qubits"]):
                lines.append("b[%d] = measure q[%d]" % (qubit, qubit))
            return "\n".join(lines) + "\n"


        def _score_counts(counts):
            protocol = CFG["protocol"]
            width = protocol["width"]
            total = sum(int(count) for count in counts.values())
            if total <= 0:
                raise RuntimeError("QPU acquisition returned no completed shots")
            monitor_ones = [0] * width
            payload_zero = 0
            payload_all_zero = 0
            for raw_key, raw_count in counts.items():
                value = _count_key_to_int(raw_key)
                count = int(raw_count)
                for logical, qubit in enumerate(protocol["monitor_qubits"]):
                    monitor_ones[logical] += count * ((value >> qubit) & 1)
                payload_bits = [
                    (value >> qubit) & 1 for qubit in protocol["payload_qubits"]
                ]
                payload_zero += count * payload_bits.count(0)
                if not any(payload_bits):
                    payload_all_zero += count
            response = [value / total for value in monitor_ones]
            rmse = math.sqrt(
                sum(
                    (response[i] - CFG["monitor_target"][i]) ** 2
                    for i in range(width)
                )
                / width
            )
            return {
                "monitor_response": response,
                "monitor_rmse": rmse,
                "payload_bitwise_zero": payload_zero / (total * width),
                "payload_all_zero": payload_all_zero / total,
            }


        def _solve(matrix, rhs):
            """Small dense solve used only by the explicitly out-of-class n=4 arm."""
            n = len(rhs)
            augmented = [list(matrix[i]) + [rhs[i]] for i in range(n)]
            for column in range(n):
                pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
                if abs(augmented[pivot][column]) < 1e-12:
                    raise RuntimeError("singular dense finite-difference normal matrix")
                augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
                scale = augmented[column][column]
                augmented[column] = [value / scale for value in augmented[column]]
                for row in range(n):
                    if row == column:
                        continue
                    factor = augmented[row][column]
                    augmented[row] = [
                        augmented[row][entry] - factor * augmented[column][entry]
                        for entry in range(n + 1)
                    ]
            return [augmented[i][n] for i in range(n)]


        def _passes_contract(row):
            protocol = CFG["protocol"]
            return (
                row["contract_eligible"]
                and row["monitor_rmse"] <= protocol["monitor_tolerance"]
                and row["payload_bitwise_zero"] >= CFG["payload_threshold"]
            )


        def _contract_entry():
            required = CFG["protocol"]["required_consecutive"]
            for stop in range(required, len(TRACE) + 1):
                if all(_passes_contract(row) for row in TRACE[stop - required : stop]):
                    return stop
            return None


        def execute(qi: QuantumInterface) -> None:
            global TRACE, FINAL
            TRACE = []
            FINAL = {}
            protocol = CFG["protocol"]
            scenario = CFG["scenario"]
            arm = CFG["arm"]
            width = protocol["width"]
            target = CFG["monitor_target"]
            low = protocol["command_low"]
            high = protocol["command_high"]
            amplitude = protocol["identification_amplitude"]
            id_sign = [float(value) for value in scenario["identification_sign"]]
            u = [0.0] * width
            update_count = 0

            # Retained-residual state.
            u_prev = [0.0] * width
            last_action = [0.0] * width
            last_response = None
            correlation = [0.0] * width
            gain_hat = [protocol["gain_floor"]] * width

            # Diagonal-secant state.
            secant_last_u = [0.0] * width
            secant_last_response = None
            secant_slope = [0.03] * width

            # Commissioned PI and dense finite-difference state.
            integral = [0.0] * width
            pi_minus = None
            dense_base = None
            dense_probes = []

            server_started = time.perf_counter()
            for acquisition in range(protocol["acquisitions"]):
                if arm == "commissioned_pi" and acquisition == 0:
                    command = [-amplitude * value for value in id_sign]
                    kind = "coded_probe_minus"
                    eligible = False
                elif arm == "commissioned_pi" and acquisition == 1:
                    command = [amplitude * value for value in id_sign]
                    kind = "coded_probe_plus"
                    eligible = False
                elif arm == "dense_fd" and acquisition == 0:
                    command = [0.0] * width
                    kind = "dense_base"
                    eligible = False
                elif arm == "dense_fd":
                    command = [0.0] * width
                    command[acquisition - 1] = amplitude
                    kind = "dense_probe_%d" % (acquisition - 1)
                    eligible = False
                else:
                    command = list(u)
                    kind = "ordinary"
                    eligible = True

                call_started = time.perf_counter()
                result = qi.execute_circuit(_build_cqasm(command), protocol["shots"])
                call_seconds = time.perf_counter() - call_started
                scores = _score_counts(result.results)
                response = list(scores["monitor_response"])

                update_started = time.perf_counter()
                if arm == "retained_residual":
                    if last_response is not None:
                        beta = protocol["estimator_smoothing"]
                        for i in range(width):
                            if abs(last_action[i]) > 1e-9:
                                observed = _sign((response[i] - last_response[i]) * last_action[i])
                                correlation[i] = (1.0 - beta) * correlation[i] + beta * observed
                                local_slope = abs(response[i] - last_response[i]) / max(
                                    abs(last_action[i]), 1e-9
                                )
                                gain_hat[i] = (1.0 - beta) * gain_hat[i] + beta * local_slope
                    if update_count < protocol["identification_cycles"]:
                        direction = 1.0 if update_count % 2 == 0 else -1.0
                        action = [amplitude * id_sign[i] * direction for i in range(width)]
                    else:
                        action = []
                        for i in range(width):
                            polarity_hat = 1.0 if correlation[i] == 0.0 else _sign(correlation[i])
                            diagonal_gain = (
                                protocol["eta"]
                                * polarity_hat
                                / max(gain_hat[i], protocol["gain_floor"])
                            )
                            action.append(
                                diagonal_gain * (target[i] - response[i])
                                + protocol["momentum"] * (u[i] - u_prev[i])
                            )
                    new_u = [_clip(u[i] + action[i], low, high) for i in range(width)]
                    last_action = [new_u[i] - u[i] for i in range(width)]
                    u_prev = list(u)
                    u = new_u
                    last_response = list(response)
                    update_count += 1

                elif arm == "diagonal_secant":
                    measured_u = list(u)
                    if secant_last_response is not None:
                        for i in range(width):
                            delta_u = measured_u[i] - secant_last_u[i]
                            if abs(delta_u) > 1e-9:
                                raw_slope = (response[i] - secant_last_response[i]) / delta_u
                                if abs(raw_slope) >= 0.03:
                                    secant_slope[i] = 0.5 * secant_slope[i] + 0.5 * raw_slope
                    if secant_last_response is None:
                        action = [amplitude * id_sign[i] for i in range(width)]
                    else:
                        action = []
                        for i in range(width):
                            safe_slope = secant_slope[i]
                            if abs(safe_slope) < 0.03:
                                safe_slope = -0.03 if safe_slope < 0.0 else 0.03
                            value = 0.80 * (target[i] - response[i]) / safe_slope
                            action.append(_clip(value, -0.75, 0.75))
                    u = [_clip(measured_u[i] + action[i], low, high) for i in range(width)]
                    secant_last_u = measured_u
                    secant_last_response = list(response)
                    update_count += 1

                elif arm == "commissioned_pi":
                    if acquisition == 0:
                        pi_minus = list(response)
                    elif acquisition == 1:
                        if pi_minus is None:
                            raise RuntimeError("missing commissioned-PI minus probe")
                        slope = []
                        for i in range(width):
                            raw = (response[i] - pi_minus[i]) / (2.0 * amplitude * id_sign[i])
                            slope.append((-1.0 if raw < 0.0 else 1.0) * max(abs(raw), 0.03))
                        midpoint = [0.5 * (pi_minus[i] + response[i]) for i in range(width)]
                        for i in range(width):
                            error = target[i] - midpoint[i]
                            integral[i] = _clip(integral[i] + error, -1.0, 1.0)
                            action = _clip((0.70 * error + 0.06 * integral[i]) / slope[i], -0.75, 0.75)
                            u[i] = _clip(u[i] + action, low, high)
                        update_count += 1
                    else:
                        for i in range(width):
                            error = target[i] - response[i]
                            integral[i] = _clip(integral[i] + error, -1.0, 1.0)
                            action = _clip((0.70 * error + 0.06 * integral[i]) / slope[i], -0.75, 0.75)
                            u[i] = _clip(u[i] + action, low, high)
                        update_count += 1

                elif arm == "dense_fd":
                    if acquisition == 0:
                        dense_base = list(response)
                    else:
                        dense_probes.append(list(response))
                        if acquisition == width:
                            jacobian = [[0.0] * width for _ in range(width)]
                            for column in range(width):
                                for row in range(width):
                                    jacobian[row][column] = (
                                        dense_probes[column][row] - dense_base[row]
                                    ) / amplitude
                            lhs = [[0.0] * width for _ in range(width)]
                            rhs = [0.0] * width
                            for row in range(width):
                                for column in range(width):
                                    lhs[row][column] = sum(
                                        jacobian[k][row] * jacobian[k][column]
                                        for k in range(width)
                                    ) + (0.01 if row == column else 0.0)
                                rhs[row] = sum(
                                    jacobian[k][row] * (target[k] - dense_base[k])
                                    for k in range(width)
                                )
                            action = [0.80 * value for value in _solve(lhs, rhs)]
                            norm = math.sqrt(sum(value * value for value in action))
                            if norm > 0.40:
                                action = [value * 0.40 / norm for value in action]
                            u = [_clip(action[i], low, high) for i in range(width)]
                            update_count += 1

                elif arm != "do_nothing":
                    raise RuntimeError("unsupported hardware arm: %s" % arm)

                update_seconds = time.perf_counter() - update_started
                TRACE.append(
                    {
                        "acquisition": acquisition + 1,
                        "acquisition_kind": kind,
                        "contract_eligible": eligible,
                        "command": command,
                        "monitor_response": response,
                        "monitor_rmse": scores["monitor_rmse"],
                        "payload_bitwise_zero": scores["payload_bitwise_zero"],
                        "payload_all_zero": scores["payload_all_zero"],
                        "shots_requested": int(result.shots_requested),
                        "shots_done": int(result.shots_done),
                        "hybrid_execute_call_seconds": call_seconds,
                        "controller_update_seconds": update_seconds,
                    }
                )

            entry = _contract_entry()
            required = protocol["required_consecutive"]
            at_deadline = (
                len(TRACE) >= required
                and all(_passes_contract(row) for row in TRACE[-required:])
            )
            structural_minimum = required
            if arm == "commissioned_pi":
                structural_minimum = 2 + required
            elif arm == "dense_fd":
                structural_minimum = width + 1 + required
            FINAL = {
                "schema_version": CFG["schema_version"],
                "scope": CFG["scope"],
                "arm": arm,
                "seed": CFG["seed"],
                "protocol": protocol,
                "scenario": scenario,
                "monitor_target": target,
                "payload_reference_bitwise_zero": CFG["payload_reference_bitwise_zero"],
                "payload_threshold": CFG["payload_threshold"],
                "contract_entry_acquisition": entry,
                "contract_success": entry is not None,
                "contract_at_deadline": at_deadline,
                "structural_minimum_acquisitions_to_confirm": structural_minimum,
                "ordinary_acquisitions": sum(row["contract_eligible"] for row in TRACE),
                "discarded_probe_acquisitions": sum(not row["contract_eligible"] for row in TRACE),
                "final_command": u,
                "trace": TRACE,
                "server_total_elapsed_seconds": time.perf_counter() - server_started,
                "timing_note": (
                    "provider job execution time is authoritative for QPU execution; "
                    "hybrid call timing includes service overhead and excludes queue wait"
                ),
            }


        def finalize(list_of_measurements):
            result = dict(FINAL)
            result["provider_measurements"] = list_of_measurements
            return result
        '''
    ).lstrip()
    return prelude + body


def write_qi_job_artifacts(
    output_directory: Path,
    *,
    seeds: Sequence[int],
    monitor_target: Sequence[float],
    payload_reference_bitwise_zero: float,
    arms: Sequence[HardwareArm] = HARDWARE_ARMS,
    protocol: QIHardwareProtocol | None = None,
) -> dict[str, str]:
    """Write reproducible provider artifacts and return relative SHA-256 entries."""

    protocol = protocol or QIHardwareProtocol()
    protocol.validate()
    output_directory.mkdir(parents=True, exist_ok=True)
    artifacts: list[Path] = []
    reference_path = output_directory / "tuna9_contract_reference.cq"
    reference_path.write_text(render_qi_reference_cqasm(protocol), encoding="utf-8")
    artifacts.append(reference_path)
    for seed in seeds:
        for arm in arms:
            path = output_directory / f"tuna9_{arm}_seed_{int(seed)}.py"
            path.write_text(
                render_qi_hybrid_program(
                    arm=arm,
                    seed=int(seed),
                    monitor_target=monitor_target,
                    payload_reference_bitwise_zero=payload_reference_bitwise_zero,
                    protocol=protocol,
                ),
                encoding="utf-8",
            )
            artifacts.append(path)
    return {
        str(path.relative_to(output_directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(artifacts)
    }
