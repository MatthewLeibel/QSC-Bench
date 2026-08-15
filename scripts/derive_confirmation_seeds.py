#!/usr/bin/env python3
"""Deterministically derive QSC-Bench v1.0 local-confirmation seeds.

The phrase and algorithm are part of the locally frozen protocol.  The output
is public metadata, not a secret.  This script never executes a benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json


DEFAULT_PHRASE = "QSC-Bench-v1.0-local-confirmation-2026-08-14"
SEED_MODULUS = 2**31 - 1


def derive_seeds(phrase: str, count: int) -> list[int]:
    if count < 1:
        raise ValueError("count must be positive")
    seeds: list[int] = []
    seen: set[int] = set()
    counter = 0
    while len(seeds) < count:
        digest = hashlib.sha256(f"{phrase}:{counter}".encode("utf-8")).digest()
        seed = int.from_bytes(digest[:8], "big") % SEED_MODULUS
        counter += 1
        if seed == 0 or seed in seen:
            continue
        seen.add(seed)
        seeds.append(seed)
    return seeds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phrase", default=DEFAULT_PHRASE)
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "phrase": args.phrase,
                "phrase_sha256": hashlib.sha256(args.phrase.encode("utf-8")).hexdigest(),
                "algorithm": (
                    "seed_i = uint64_be(SHA256(UTF8(phrase + ':' + counter))[0:8]) "
                    "mod (2^31-1); skip zero and duplicates"
                ),
                "seeds": derive_seeds(args.phrase, args.count),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
