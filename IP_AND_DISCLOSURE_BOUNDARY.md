# IP and disclosure boundary

QSC-Bench is deliberately neutral and reviewable. The public disclosure is
limited to what is required to reproduce the benchmark and audit the reported
evidence:

- benchmark contracts, metrics, plant models, controller interfaces, and access
  rules;
- the independent manuscript-level retained-residual reference controller;
- competing baseline implementations and resource-accounting metadata;
- frozen protocols, configurations, seeds, summaries, raw result records, and
  provider job provenance;
- Metriq-compatible schemas and candidate result envelopes.

The repository does not disclose the TrueLoop hosted runtime, licensed offline
build, service infrastructure, credentials, private provider calibration data,
patent drafts, or unpublished implementation details. No equivalence between the
public reference controller and a proprietary TrueLoop implementation is claimed.

The repository is MIT licensed. A contribution accepted into Metriq Gym is
governed by that project's Apache-2.0 license and contribution terms. Those
terms include patent provisions that are legally significant. The upstream
proposal therefore contains the benchmark interface and public reference path,
not proprietary runtime code.

This document records the intended technical disclosure boundary. It is not
legal advice and does not replace review by patent or licensing counsel.
