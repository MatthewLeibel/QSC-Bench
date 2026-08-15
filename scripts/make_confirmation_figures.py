#!/usr/bin/env python3
"""Create compact publication figures from immutable QSC-Bench result bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "retained_residual": "#1769aa",
    "anderson_residual": "#00897b",
    "commissioned_pi": "#ef6c00",
    "diagonal_secant": "#8e24aa",
    "full_broyden": "#c62828",
    "dense_fd": "#5d4037",
    "oracle": "#546e7a",
    "do_nothing": "#9e9e9e",
    "spsa": "#f9a825",
}

LABELS = {
    "retained_residual": "Retained residual",
    "anderson_residual": "Fixed-window Anderson",
    "commissioned_pi": "Commissioned PI",
    "diagonal_secant": "Diagonal retained secant",
    "full_broyden": "Full Broyden",
    "dense_fd": "Dense finite difference",
    "oracle": "Oracle (unranked)",
    "do_nothing": "Do nothing",
    "spsa": "SPSA",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    fig.savefig(
        output_dir / f"{stem}.png",
        dpi=240,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def primary_figure(bundle: dict, output_dir: Path) -> None:
    methods = [
        "retained_residual",
        "anderson_residual",
        "commissioned_pi",
        "diagonal_secant",
        "oracle",
    ]
    summaries = {(row["controller"], row["width"]): row for row in bundle["summary"]}
    widths = list(bundle["config"]["widths"])
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 7.2), sharex=True)
    for method in methods:
        rows = [summaries[(method, width)] for width in widths]
        medians = np.asarray(
            [row["acquisitions_to_contract"]["median"] or np.nan for row in rows]
        )
        q1 = np.asarray([row["acquisitions_to_contract"]["q1"] or np.nan for row in rows])
        q3 = np.asarray([row["acquisitions_to_contract"]["q3"] or np.nan for row in rows])
        axes[0].plot(
            widths,
            medians,
            marker="o",
            linewidth=2,
            color=COLORS[method],
            label=LABELS[method],
        )
        axes[0].fill_between(widths, q1, q3, color=COLORS[method], alpha=0.13)
        axes[1].plot(
            widths,
            [row["success_rate"] for row in rows],
            marker="o",
            linewidth=2,
            color=COLORS[method],
            label=LABELS[method],
        )
    axes[0].axhline(40, color="#777777", linestyle="--", linewidth=1, label="Censoring budget")
    axes[0].set_ylabel("Acquisitions to verified contract")
    axes[0].set_ylim(0, 43)
    axes[0].grid(True, which="both", alpha=0.22)
    axes[0].legend(ncol=2, fontsize=8, loc="upper left")
    axes[1].set_ylabel("Contract success rate")
    axes[1].set_xlabel("Controlled channels, n")
    axes[1].set_ylim(-0.03, 1.03)
    axes[1].grid(True, which="both", alpha=0.22)
    for axis in axes:
        axis.set_xscale("log", base=2)
    fig.suptitle("Frozen QSC-Bench scale campaign (30 paired seeds per cell)")
    fig.tight_layout()
    _save(fig, output_dir, "fig1_frozen_scale")


def dense_resource_figure(bundle: dict, output_dir: Path) -> None:
    methods = ["retained_residual", "anderson_residual", "full_broyden", "dense_fd"]
    widths = list(bundle["config"]["widths"])
    records = bundle["records"]
    summaries = {(row["controller"], row["width"]): row for row in bundle["summary"]}
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 7.2), sharex=True)
    for method in methods:
        axes[0].plot(
            widths,
            [summaries[(method, width)]["success_rate"] for width in widths],
            marker="o",
            linewidth=2,
            color=COLORS[method],
            label=LABELS[method],
        )
        state = []
        for width in widths:
            values = [
                row["controller_mutable_state_bytes"]
                for row in records
                if row["controller"] == method
                and row["width"] == width
                and row.get("controller_mutable_state_bytes") is not None
            ]
            state.append(float(np.median(values)))
        axes[1].plot(
            widths,
            state,
            marker="o",
            linewidth=2,
            color=COLORS[method],
            label=LABELS[method],
        )
    axes[0].set_ylabel("Contract success rate")
    axes[0].set_ylim(-0.03, 1.03)
    axes[0].grid(True, which="both", alpha=0.22)
    axes[0].legend(ncol=2, fontsize=8, loc="lower left")
    axes[1].set_xlabel("Controlled channels, n")
    axes[1].set_ylabel("Mutable controller state (bytes)")
    axes[1].set_xscale("log", base=2)
    axes[1].set_yscale("log", base=2)
    axes[1].grid(True, which="both", alpha=0.22)
    fig.suptitle("Dense baselines lose operability while importing quadratic state")
    fig.tight_layout()
    _save(fig, output_dir, "fig2_dense_resource_ceiling")


def projection_figure(projection: dict, output_dir: Path) -> None:
    method_order = [
        "retained_residual",
        "anderson_residual",
        "scheduled_sweep_1024_channels_per_acquisition_best_case",
        "dense_finite_difference_best_case_verified",
    ]
    colors = {
        **COLORS,
        "scheduled_sweep_1024_channels_per_acquisition_best_case": "#ef6c00",
        "dense_finite_difference_best_case_verified": "#5d4037",
    }
    labels = {
        **LABELS,
        "scheduled_sweep_1024_channels_per_acquisition_best_case": "Scheduled sweep (1,024 channels/frame)",
        "dense_finite_difference_best_case_verified": "Dense finite difference",
    }
    widths = [row["width"] for row in projection["projection_rows"]]
    latency = 1e-4
    fig, axis = plt.subplots(figsize=(8.0, 4.8))
    for method in method_order:
        seconds = []
        for row in projection["projection_rows"]:
            item = next(entry for entry in row["methods"] if entry["method"] == method)
            timing = next(
                entry for entry in item["times"] if entry["acquisition_latency_seconds"] == latency
            )
            seconds.append(timing["acquisition_only_seconds"])
        axis.plot(
            widths,
            seconds,
            marker="o",
            linewidth=2,
            color=colors[method],
            label=labels[method],
        )
    for seconds, label in [(0.01, "10 ms"), (1.0, "1 s"), (86400.0, "1 day")]:
        axis.axhline(seconds, color="#777777", linestyle=":", linewidth=1)
        axis.text(widths[-1] / 2.8, seconds * 1.12, label, fontsize=8, color="#555555")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Controlled channels, n")
    axis.set_ylabel("Acquisition-only time at 100 µs/frame (s)")
    axis.grid(True, which="both", alpha=0.22)
    axis.legend(fontsize=8, loc="upper left")
    axis.set_title("Structural time-to-contract projection (not measured hardware time)")
    fig.tight_layout()
    _save(fig, output_dir, "fig3_acquisition_projection")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=Path, required=True)
    parser.add_argument("--strong", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    primary_figure(_load(args.scale), args.output_dir)
    dense_resource_figure(_load(args.strong), args.output_dir)
    projection_figure(_load(args.projection), args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
