# PREREG_SCALE_LADDER

Registered before execution. Tier: CONTROLLED SIMULATION, reference reimplementation
of the published Regime A law (tlref.py, constants eta=0.65 mu=0.15 beta=0.50
g_min=0.15 calibrated on seeds 101-103 at n=64-256 against the hosted endpoint;
analysis seeds disjoint). Not the proprietary offline build. Hosted endpoint caps
at n=4,096 (measured); all n above that run the reference law only.

## Design
Plant: coupled heterogeneous drifting family (tanh, hidden signs, log-uniform gains
0.3-1.0, 8-neighbour local coupling 0.30, OU drift). Drift severity 0.05 rad per
acquisition. Cold start phi0=0, commanded targets U(0.30,0.70). 24-cycle horizon,
one parallel acquisition per cycle, every acquisition charged. float32 at n>=1e7,
procedural chunked plant at n=1e8.

Arms: reference retained law; diagonal Broyden (retained-secant, honest nearest
competitor); do-nothing. FD excluded by arithmetic at large n (one gradient costs
n acquisitions; disclosed, not raced). SPSA excluded above 1e6 (pinned at
do-nothing in all prior measurements; disclosed).

Ladder and seeds: n=1e5 (seeds 31,32,33), n=1e6 (31,32,33), n=1e7 (31,32),
n=1e8 (31). Reduced seed counts at large n are compute-priced and disclosed.

## Registered bars (pass/fail, published either way)
B1. Usability: reference law verified RMS < 0.10 within 6 acquisitions at every n.
B2. Flatness: mean steady floor (cycles 12-24) at each n is <= 1.5x the floor at 1e5.
B3. Cost: sequential acquisitions to usability do not grow with n (6 at every rung).
B4. Control arm: do-nothing floor >= 0.15 at every n.
B5. Honest competitor: diagonal Broyden expected to survive with a floor within
    2x of the reference law; if it matches or beats, that is published as-is.
B6. Wall-clock and peak memory recorded at each rung; both expected linear in n.

Amendments, if any, will be recorded in-file below this line before further runs.
