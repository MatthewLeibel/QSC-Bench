"""Command-line interface for local QSC-Bench development runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .analysis import analyze_campaign, write_analysis
from .config import load_config
from .controllers import make_controller
from .plant import make_plant
from .runner import run_suite, write_results
from .scaling import build_architecture_projection, write_architecture_projection


def _default_config() -> Path:
    return Path(__file__).resolve().parents[1] / "configs" / "smoke.json"


def _progress(record: dict) -> None:
    acquisitions = record.get("acquisitions_to_contract")
    suffix = f"A={acquisitions}" if acquisitions is not None else record["status"]
    print(
        f"[{record['width']:>3} qubits] seed={record['seed']} "
        f"{record['controller']:<20} {suffix}",
        flush=True,
    )


def cmd_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(json.dumps(config.to_dict(), indent=2, sort_keys=True))
    print("configuration: VALID")
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    plant = make_plant(args.width, args.seed, config.plant)
    diagnostics = plant.local_jacobian_diagnostics()
    output = {
        "width": args.width,
        "seed": args.seed,
        "minimum_diagonal_magnitude": diagnostics.minimum_diagonal_magnitude,
        "maximum_row_offdiag_to_diag_ratio": diagnostics.maximum_row_offdiag_to_diag_ratio,
        "spectral_norm": diagnostics.spectral_norm,
        "locally_informative": diagnostics.minimum_diagonal_magnitude > 0,
        "strict_row_diagonal_dominance": diagnostics.maximum_row_offdiag_to_diag_ratio < 1,
        "jacobian": (
            diagnostics.jacobian.tolist()
            if args.show_jacobian and diagnostics.jacobian is not None
            else "omitted"
        ),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["locally_informative"] else 2


def cmd_state_audit(args: argparse.Namespace) -> int:
    controller = make_controller(args.controller, args.width, args.seed)
    arrays = controller.mutable_state_arrays()
    output = {
        "controller": controller.metadata.name,
        "width": args.width,
        "arrays": {
            name: {"shape": list(value.shape), "dtype": str(value.dtype), "bytes": value.nbytes}
            for name, value in arrays.items()
        },
        "mutable_float_words": controller.mutable_float_words(),
        "mutable_float_words_per_channel": controller.mutable_float_words_per_channel(),
        "mutable_state_bytes": controller.mutable_state_bytes(),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    bundle = run_suite(config, progress=_progress)
    output_json, output_csv = write_results(bundle, args.output)
    errors = [record for record in bundle["records"] if record["status"] == "ERROR"]
    print(f"JSON: {output_json}")
    print(f"CSV:  {output_csv}")
    print(f"scientific failures: {sum(not r['contract_success'] for r in bundle['records'])}")
    print(f"execution errors: {len(errors)}")
    return 2 if errors else 0


def cmd_project_architecture(args: argparse.Namespace) -> int:
    projection = build_architecture_projection(
        args.measured_results,
        widths=args.widths,
        latencies_seconds=args.latencies,
        confirmation_depth=args.confirmation_depth,
        value_bits=args.value_bits,
        bandwidths_bytes_per_second=args.bandwidths,
    )
    destination = write_architecture_projection(projection, args.output)
    print(f"JSON: {destination}")
    print(
        "classification: measured anchors + structural/projection rows; "
        "not an executed large-width quantum result"
    )
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    bundle = json.loads(args.results.read_text(encoding="utf-8"))
    analysis = analyze_campaign(
        bundle,
        bootstrap_draws=args.bootstrap_draws,
        bootstrap_seed=args.bootstrap_seed,
        alpha_upper_margin=args.alpha_upper_margin,
        success_lower_margin=args.success_lower_margin,
        minimum_width_count=args.minimum_width_count,
        minimum_paired_seeds=args.minimum_paired_seeds,
    )
    json_path, markdown_path = write_analysis(analysis, args.output)
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    print(f"class-level result: {analysis['class_level_result']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qsc-bench",
        description="Quantum Stability Contract Benchmark development runner",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-config")
    validate.add_argument("--config", type=Path, default=_default_config())
    validate.set_defaults(func=cmd_validate)

    diagnose = subparsers.add_parser("diagnose-plant")
    diagnose.add_argument("--config", type=Path, default=_default_config())
    diagnose.add_argument("--width", type=int, default=4)
    diagnose.add_argument("--seed", type=int, default=20260813)
    diagnose.add_argument("--show-jacobian", action="store_true")
    diagnose.set_defaults(func=cmd_diagnose)

    state = subparsers.add_parser("audit-controller-state")
    state.add_argument("controller")
    state.add_argument("--width", type=int, default=8)
    state.add_argument("--seed", type=int, default=20260813)
    state.set_defaults(func=cmd_state_audit)

    run = subparsers.add_parser("run")
    run.add_argument("--config", type=Path, default=_default_config())
    run.add_argument(
        "--output",
        type=Path,
        default=Path("results/development/smoke_results.json"),
    )
    run.set_defaults(func=cmd_run)

    projection = subparsers.add_parser(
        "project-architecture",
        description=(
            "Project acquisition-latency consequences from measured QSC-Bench records "
            "while keeping measured, structural, and hypothetical quantities separate."
        ),
    )
    projection.add_argument("--measured-results", type=Path, required=True)
    projection.add_argument("--output", type=Path, required=True)
    projection.add_argument(
        "--widths",
        type=int,
        nargs="+",
        default=[8, 128, 1024, 1_000_000, 100_000_000],
    )
    projection.add_argument(
        "--latencies",
        type=float,
        nargs="+",
        default=[1e-6, 1e-5, 1e-4, 1e-3, 1e-1],
    )
    projection.add_argument("--confirmation-depth", type=int, default=3)
    projection.add_argument("--value-bits", type=int, default=16)
    projection.add_argument(
        "--bandwidths",
        type=float,
        nargs="+",
        default=[1e9, 1e10, 1e11],
        help="Explicit interface bandwidth scenarios in bytes/s.",
    )
    projection.set_defaults(func=cmd_project_architecture)

    analysis = subparsers.add_parser(
        "analyze-campaign",
        description="Apply the frozen finite-range scaling and payload-validity tests.",
    )
    analysis.add_argument("--results", type=Path, required=True)
    analysis.add_argument("--output", type=Path, required=True)
    analysis.add_argument("--bootstrap-draws", type=int, default=10_000)
    analysis.add_argument("--bootstrap-seed", type=int, default=20260814)
    analysis.add_argument("--alpha-upper-margin", type=float, default=0.05)
    analysis.add_argument("--success-lower-margin", type=float, default=0.85)
    analysis.add_argument("--minimum-width-count", type=int, default=4)
    analysis.add_argument("--minimum-paired-seeds", type=int, default=20)
    analysis.set_defaults(func=cmd_analyze)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
