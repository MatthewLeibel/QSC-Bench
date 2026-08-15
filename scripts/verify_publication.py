#!/usr/bin/env python3
"""Verify the self-contained QSC-Bench public evidence package."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_json() -> int:
    count = 0
    for base in ("configs", "schemas", "results"):
        for path in (ROOT / base).rglob("*.json"):
            _load(path)
            count += 1
    return count


def verify_manifests() -> tuple[int, int]:
    manifests = [
        path
        for path in (ROOT / "results").rglob("ARTIFACT_MANIFEST_SHA256.txt")
        if path.parent != ROOT / "results" / "confirmation"
    ]
    files = 0
    for manifest in manifests:
        directory = manifest.parent
        for line in manifest.read_text(encoding="utf-8").splitlines():
            digest, relative = line.split("  ", maxsplit=1)
            path = directory / relative
            if not path.is_file() or _sha256(path) != digest:
                raise ValueError(f"manifest mismatch: {path}")
            files += 1
    return len(manifests), files


def verify_submission_index() -> int:
    index = _load(ROOT / "results" / "METRIQ_SUBMISSION_INDEX.json")
    if index["release"] != "1.0.0":
        raise ValueError("unexpected release version")
    records = 0
    for entry in index["candidate_result_envelopes"]:
        path = ROOT / entry["path"]
        payload = _load(path)
        if _sha256(path) != entry["sha256"] or len(payload) != entry["records"]:
            raise ValueError(f"Metriq record index mismatch: {path}")
        records += len(payload)
        for envelope in payload:
            if envelope["job_type"] != "QSC-Bench Cold Start":
                raise ValueError("unexpected candidate result type")
            result = envelope["results"]
            expected_score = (
                1.0 / result["acquisitions_to_contract"]
                if result["contract_success"]
                else 0.0
            )
            if not math.isclose(
                result["score"]["value"], expected_score, rel_tol=0.0, abs_tol=1e-15
            ):
                raise ValueError("candidate Metriq score mismatch")
            if envelope["platform"]["device_metadata"]["simulator"] is not False:
                raise ValueError("hardware record mislabeled as simulator")
    return records


def verify_hardware_claims() -> None:
    cepheus = _load(
        ROOT
        / "results"
        / "hardware"
        / "openquantum_cepheus_96q_single_rx_v3"
        / "QSC_CEPHEUS_96Q_HARDWARE_SUMMARY.json"
    )
    if cepheus["decision"] != {
        "dense_finite_difference_executed": False,
        "dense_finite_difference_structural_minimum_acquisitions": 51,
        "do_nothing_contract": "FAIL",
        "hardware_width_scaling_exponent": "NOT_ESTABLISHED",
        "replication_strength": "single paired confirmation seed",
        "retained_contract_entry_acquisition": 4,
        "retained_residual_contract": "PASS",
    }:
        raise ValueError("Cepheus decision changed")
    emerald = _load(
        ROOT
        / "results"
        / "hardware"
        / "openquantum_iqm_emerald_command_effect_v1"
        / "OPENQUANTUM_EMERALD_COMMAND_EFFECT_SUMMARY.json"
    )
    if emerald["result"]["decision"] != "PASS":
        raise ValueError("Emerald decision changed")
    if "not an adaptive" not in emerald["claim_boundary"].lower():
        raise ValueError("Emerald claim boundary missing")


def verify_public_text() -> None:
    paths = [
        ROOT / "README.md",
        ROOT / "NOTICE",
        ROOT / "IP_AND_DISCLOSURE_BOUNDARY.md",
        *sorted((ROOT / "reports").glob("*.md")),
        *sorted((ROOT / "results").rglob("*.md")),
        *sorted((ROOT / "results").rglob("*.json")),
    ]
    disallowed = [
        re.compile(r"/Users/[A-Za-z0-9._-]+/"),
        re.compile(r"EVAL-[A-Za-z0-9]+"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for pattern in disallowed:
            if pattern.search(text):
                raise ValueError(f"private material pattern in {path}: {pattern.pattern}")


def main() -> None:
    json_files = verify_json()
    manifests, manifest_files = verify_manifests()
    records = verify_submission_index()
    verify_hardware_claims()
    verify_public_text()
    print(
        "PUBLICATION_VALID "
        f"json={json_files} manifests={manifests} "
        f"manifest_files={manifest_files} candidate_metriq_records={records}"
    )


if __name__ == "__main__":
    main()
