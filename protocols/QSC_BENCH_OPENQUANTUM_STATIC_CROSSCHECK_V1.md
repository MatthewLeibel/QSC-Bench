# QSC-Bench OpenQuantum static cross-check v1

## Purpose

This is a secondary, post-campaign portability check. It tests whether a
component-resolved Ramsey monitor can return eight channel marginals in one
parallel hardware acquisition on a provider stack independent of Quantum
Inspire. It is not an adaptive controller campaign, a channel-scaling result,
or evidence that OpenQuantum exposes private calibration controls.

## Frozen circuit and metric

One 1,024-shot job contains four nominal Ramsey channels and four shifted
channels. For every channel, the circuit is

    H -> Rz(pi/2 + e_i) -> H -> Z measurement.

The nominal channels use `e = 0`. The shifted channels use
`e = (+0.35, -0.35, +0.65, -0.65)` radians. In the ideal model,

    Pr(1 | e_i) = (1 + sin(e_i)) / 2.

The pre-outcome descriptive checks are:

1. at least three of four shifted channels have the expected response
   direction relative to 0.5; and
2. the RMSE between measured and ideal eight-channel marginals is at most
   0.15.

These loose checks test observability and circuit portability under native
hardware noise. They do not test controller convergence.

## Cost and publication controls

- Backend: `rigetti:cepheus-1-108q`.
- Execution plan: public compute only.
- Queue priority: the lowest-cost available priority.
- Maximum authorized quote: 2 Spark credits.
- Paid Full Credits must remain zero and must never be used.
- The job is not submitted until its returned quote is inspected.
- Nothing is uploaded to Metriq, GitHub, or another publication service.

