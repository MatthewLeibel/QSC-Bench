"""Frozen-campaign statistics for QSC-Bench.

Failures remain right-censored.  Scaling exponents are fit only on paired seeds
that succeed at every declared width, and the number excluded by that rule is
reported rather than hidden.
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def wilson_interval(successes: int, runs: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if runs <= 0:
        return math.nan, math.nan
    proportion = successes / runs
    denominator = 1.0 + z * z / runs
    centre = (proportion + z * z / (2.0 * runs)) / denominator
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / runs + z * z / (4.0 * runs * runs)
    ) / denominator
    return max(0.0, centre - radius), min(1.0, centre + radius)


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "q1": None, "q3": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "median": float(np.median(array)),
        "q1": float(np.quantile(array, 0.25)),
        "q3": float(np.quantile(array, 0.75)),
    }


def _median_field(records: list[dict[str, Any]], field: str) -> float | None:
    values = [float(record[field]) for record in records if record.get(field) is not None]
    return float(np.median(values)) if values else None


def _bootstrap_median_interval(
    values: list[float], rng: np.random.Generator, draws: int
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    array = np.asarray(values, dtype=np.float64)
    indices = rng.integers(0, array.size, size=(draws, array.size))
    medians = np.median(array[indices], axis=1)
    return float(np.quantile(medians, 0.025)), float(np.quantile(medians, 0.975))


def _kaplan_meier(
    records: list[dict[str, Any]], budget: int
) -> dict[str, float | None]:
    observations = []
    for record in records:
        if record.get("contract_success"):
            observations.append((int(record["acquisitions_to_contract"]), True))
        else:
            observations.append((budget, False))
    at_risk = len(observations)
    survival = 1.0
    rmst = 0.0
    median = None
    for acquisition in range(1, budget + 1):
        rmst += survival
        events = sum(t == acquisition and event for t, event in observations)
        censored = sum(t == acquisition and not event for t, event in observations)
        if at_risk > 0 and events:
            survival *= 1.0 - events / at_risk
            if median is None and survival <= 0.5:
                median = float(acquisition)
        at_risk -= events + censored
    return {
        "kaplan_meier_median_acquisitions": median,
        "restricted_mean_acquisitions_to_budget": float(rmst),
        "survival_at_budget": float(survival),
    }


def _paired_scaling(
    records: list[dict[str, Any]],
    widths: list[int],
    *,
    rng: np.random.Generator,
    draws: int,
) -> dict[str, Any]:
    by_width_seed = {
        (int(record["width"]), int(record["seed"])): record for record in records
    }
    all_seeds = sorted({int(record["seed"]) for record in records})
    paired = [
        seed
        for seed in all_seeds
        if all(
            (width, seed) in by_width_seed
            and by_width_seed[(width, seed)].get("contract_success")
            for width in widths
        )
    ]
    result: dict[str, Any] = {
        "declared_widths": widths,
        "all_seed_count": len(all_seeds),
        "complete_successful_paired_seed_count": len(paired),
        "excluded_seed_count": len(all_seeds) - len(paired),
        "fit_semantics": (
            "log(A)=log(c)+alpha*log(n), using width medians over seeds that "
            "succeeded at every declared width; failures are reported separately"
        ),
        "alpha": None,
        "alpha_ci95": [None, None],
        "acquisitions_per_doubling": None,
        "acquisitions_per_doubling_ci95": [None, None],
    }
    if len(widths) < 3 or len(paired) < 2:
        return result

    log_widths = np.log(np.asarray(widths, dtype=np.float64))
    log2_widths = np.log2(np.asarray(widths, dtype=np.float64))

    def fit(seed_sample: list[int]) -> tuple[float, float]:
        medians = np.asarray(
            [
                np.median(
                    [
                        float(by_width_seed[(width, seed)]["acquisitions_to_contract"])
                        for seed in seed_sample
                    ]
                )
                for width in widths
            ],
            dtype=np.float64,
        )
        alpha = float(np.polyfit(log_widths, np.log(medians), 1)[0])
        per_doubling = float(np.polyfit(log2_widths, medians, 1)[0])
        return alpha, per_doubling

    point_alpha, point_doubling = fit(paired)
    boot_alpha = np.empty(draws, dtype=np.float64)
    boot_doubling = np.empty(draws, dtype=np.float64)
    paired_array = np.asarray(paired, dtype=np.int64)
    for index in range(draws):
        sample = paired_array[rng.integers(0, len(paired), size=len(paired))].tolist()
        boot_alpha[index], boot_doubling[index] = fit(sample)
    result.update(
        {
            "alpha": point_alpha,
            "alpha_ci95": [
                float(np.quantile(boot_alpha, 0.025)),
                float(np.quantile(boot_alpha, 0.975)),
            ],
            "acquisitions_per_doubling": point_doubling,
            "acquisitions_per_doubling_ci95": [
                float(np.quantile(boot_doubling, 0.025)),
                float(np.quantile(boot_doubling, 0.975)),
            ],
        }
    )
    return result


def _power_law_exponent(widths: list[int], values: list[float]) -> float | None:
    usable = [
        (float(width), float(value))
        for width, value in zip(widths, values, strict=True)
        if width > 0 and value > 0 and np.isfinite(value)
    ]
    if len(usable) < 3:
        return None
    x, y = zip(*usable, strict=True)
    return float(np.polyfit(np.log(np.asarray(x)), np.log(np.asarray(y)), 1)[0])


def analyze_campaign(
    bundle: dict[str, Any],
    *,
    bootstrap_draws: int = 10_000,
    bootstrap_seed: int = 20260814,
    alpha_upper_margin: float = 0.05,
    success_lower_margin: float = 0.85,
    minimum_width_count: int = 4,
    minimum_paired_seeds: int = 20,
) -> dict[str, Any]:
    records = bundle.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("campaign bundle has no records")
    budget = int(bundle["config"]["contract"]["max_monitor_acquisitions"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["controller"])].append(record)
    rng = np.random.default_rng(bootstrap_seed)
    controllers = []
    for controller, group in sorted(grouped.items()):
        widths = sorted({int(record["width"]) for record in group})
        width_rows = []
        for width in widths:
            cell = [record for record in group if int(record["width"]) == width]
            successes = [record for record in cell if record.get("contract_success")]
            counts = [float(record["acquisitions_to_contract"]) for record in successes]
            payload_margins = [
                float(record["payload_bitwise_zero_probability_at_entry"])
                - float(record["payload_quality_threshold"])
                for record in successes
            ]
            lower, upper = wilson_interval(len(successes), len(cell))
            median_low, median_high = _bootstrap_median_interval(
                counts, rng, bootstrap_draws
            )
            width_rows.append(
                {
                    "width": width,
                    "runs": len(cell),
                    "successes": len(successes),
                    "failures": len(cell) - len(successes),
                    "success_rate": len(successes) / len(cell),
                    "success_rate_wilson_ci95": [lower, upper],
                    "acquisitions_successes_only": _quantiles(counts),
                    "median_acquisitions_bootstrap_ci95": [median_low, median_high],
                    "payload_margin": _quantiles(payload_margins),
                    "censored_time_to_event": _kaplan_meier(cell, budget),
                    "median_host_update_seconds": _median_field(
                        cell, "host_update_seconds"
                    ),
                    "median_controller_state_bytes": _median_field(
                        cell, "controller_mutable_state_bytes"
                    ),
                }
            )
        scaling = _paired_scaling(
            group, widths, rng=rng, draws=bootstrap_draws
        )
        width_groups = [
            [record for record in group if int(record["width"]) == width]
            for width in widths
        ]
        state_medians = [
            _median_field(cell, "controller_mutable_state_bytes")
            for cell in width_groups
        ]
        host_medians = [_median_field(cell, "host_update_seconds") for cell in width_groups]
        wall_medians = [_median_field(cell, "wall_runtime_seconds") for cell in width_groups]
        commissioning_medians = [
            _median_field(cell, "commissioning_acquisitions") for cell in width_groups
        ]
        state_per_channel = [
            value / width if value is not None else None
            for value, width in zip(state_medians, widths, strict=True)
        ]
        finite_state_per_channel = [
            value for value in state_per_channel if value is not None and value > 0
        ]
        resource_scaling = {
            "widths": widths,
            "median_state_bytes": state_medians,
            "median_state_bytes_per_channel": state_per_channel,
            "state_bytes_power_law_exponent": _power_law_exponent(
                widths, [value if value is not None else math.nan for value in state_medians]
            ),
            "state_bytes_per_channel_max_to_min_ratio": (
                max(finite_state_per_channel) / min(finite_state_per_channel)
                if finite_state_per_channel
                else None
            ),
            "median_total_host_seconds": host_medians,
            "total_host_seconds_power_law_exponent": _power_law_exponent(
                widths, [value if value is not None else math.nan for value in host_medians]
            ),
            "median_wall_runtime_seconds": wall_medians,
            "wall_runtime_power_law_exponent": _power_law_exponent(
                widths, [value if value is not None else math.nan for value in wall_medians]
            ),
            "median_commissioning_acquisitions": commissioning_medians,
            "commissioning_acquisitions_power_law_exponent": _power_law_exponent(
                widths,
                [value if value is not None else math.nan for value in commissioning_medians],
            ),
            "runtime_semantics": (
                "Measured Python/Aer-or-analytic implementation time on this Mac; "
                "not a physical-device latency and not a machine-independent operation count"
            ),
        }
        metadata = group[0].get("controller_metadata", {})
        minimum_success_lower = min(
            row["success_rate_wilson_ci95"][0] for row in width_rows
        )
        alpha_upper = scaling["alpha_ci95"][1]
        payload_valid = all(
            row["failures"] == 0 or row["successes"] > 0 for row in width_rows
        ) and all(
            row["payload_margin"]["median"] is None
            or row["payload_margin"]["median"] >= 0
            for row in width_rows
        )
        tests = {
            "resource_class_candidate": bool(
                metadata.get("minimal_sufficient_cold_start_candidate", False)
            ),
            "at_least_minimum_widths": len(widths) >= minimum_width_count,
            "success_wilson_lower_bound": minimum_success_lower >= success_lower_margin,
            "paired_seed_count": (
                scaling["complete_successful_paired_seed_count"] >= minimum_paired_seeds
            ),
            "alpha_upper_equivalence_margin": (
                alpha_upper is not None and alpha_upper <= alpha_upper_margin
            ),
            "payload_valid_at_entry": payload_valid,
        }
        supports = all(tests.values())
        controllers.append(
            {
                "controller": controller,
                "metadata": metadata,
                "width_cells": width_rows,
                "scaling": scaling,
                "resource_scaling": resource_scaling,
                "predeclared_tests": tests,
                "supports_bounded_depth_with_payload_over_tested_range": supports,
            }
        )

    qualifying = [
        row["controller"]
        for row in controllers
        if row["supports_bounded_depth_with_payload_over_tested_range"]
    ]
    return {
        "artifact": "QSC-Bench frozen campaign analysis",
        "source_config_sha256": bundle.get("config_sha256"),
        "source_protocol_version": bundle.get("protocol_version"),
        "source_result_label": bundle.get("result_label"),
        "source_git_commit": bundle.get("environment", {}).get("git_commit"),
        "source_git_worktree_dirty": bundle.get("environment", {}).get(
            "git_worktree_dirty"
        ),
        "statistical_contract": {
            "bootstrap_draws": bootstrap_draws,
            "bootstrap_seed": bootstrap_seed,
            "alpha_upper_margin": alpha_upper_margin,
            "success_wilson_lower_margin": success_lower_margin,
            "minimum_width_count": minimum_width_count,
            "minimum_complete_successful_paired_seeds": minimum_paired_seeds,
            "claim_scope": (
                "finite-range empirical support; no finite campaign proves asymptotic O(1)"
            ),
        },
        "controllers": controllers,
        "qualifying_controllers": qualifying,
        "class_level_result": (
            "PASS" if qualifying else "FAIL_OR_INCONCLUSIVE"
        ),
    }


def write_analysis(analysis: dict[str, Any], output: str | Path) -> tuple[Path, Path]:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(analysis, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output)

    markdown = output.with_suffix(".md")
    lines = [
        "# QSC-Bench campaign analysis",
        "",
        f"Class-level result: **{analysis['class_level_result']}**",
        "",
        "This is finite-range simulator evidence, not a proof of asymptotic constant depth.",
        "",
        "| Controller | Candidate | Success lower bound | alpha (95% CI) | Paired seeds | Result |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in analysis["controllers"]:
        minimum_success = min(
            cell["success_rate_wilson_ci95"][0] for cell in row["width_cells"]
        )
        scaling = row["scaling"]
        alpha = scaling["alpha"]
        ci = scaling["alpha_ci95"]
        alpha_text = (
            "n/a"
            if alpha is None
            else f"{alpha:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"
        )
        lines.append(
            "| {controller} | {candidate} | {success:.3f} | {alpha} | {paired} | {result} |".format(
                controller=row["controller"],
                candidate="yes" if row["predeclared_tests"]["resource_class_candidate"] else "no",
                success=minimum_success,
                alpha=alpha_text,
                paired=scaling["complete_successful_paired_seed_count"],
                result=(
                    "PASS"
                    if row["supports_bounded_depth_with_payload_over_tested_range"]
                    else "FAIL/INCONCLUSIVE"
                ),
            )
        )
    lines.extend(
        [
            "",
            "Qualifying controllers: "
            + (", ".join(analysis["qualifying_controllers"]) or "none"),
            "",
        ]
    )
    markdown.write_text("\n".join(lines), encoding="utf-8")
    return output, markdown
