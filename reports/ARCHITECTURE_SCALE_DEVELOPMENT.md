# Architecture-scale development result

Status: developmental evidence, not frozen confirmation and not authorized for publication.

## Question actually tested

The architectural claim is not that one named update law beats every controller. It is that a maintenance law can discharge the stability contract without importing a growing sequential-acquisition burden, a dense plant model, or superlinear host work.

A strict cold-start minimal-sufficient candidate therefore uses one ordinary full-vector acquisition per update, retains the writable configuration, discards no probe configuration, performs (O(n)) arithmetic, and stores (O(1)) auxiliary words per channel. It must also restore the plant and validate a separate payload. Resource counts alone are not sufficient.

The retained-residual and diagonal retained-secant implementations are candidates. Dense finite difference is out of class. Commissioned PI is a bounded-depth commissioned comparator: it remains linear after two coded probes on this plant, but it does not meet the stricter no-discarded-probe cold-start definition. Do-nothing is resource-cheap but empirically insufficient. The oracle is unranked.

## Fresh quantum-simulation ladder

The Aer matrix-product-state development run used widths 4, 8, 12, and 16, two paired seeds, 512 shots per ordinary acquisition, a 4,096-shot reference, three consecutive monitor passes, independent payload validation, and a 40-acquisition censoring budget. The main plant was weakly coupled and locally diagonally dominant. These settings differ from the manuscript's classical scale ladder, so the absolute acquisition counts need not match.

| Controller | n=4 | n=8 | n=12 | n=16 | Successes |
|---|---:|---:|---:|---:|---:|
| Retained residual | 14.5 | 13.5 | 10.5 | 17.0 | 8/8 |
| Diagonal retained secant | 12.0 | 15.0 | 23.5 | 18.5 | 8/8 |
| Commissioned PI | 8.5 | 12.5 | 12.0 | 12.5 | 8/8 |
| Dense finite difference | 13.5 | 26.0 (1/2) | 29.0 (1/2) | timeout (0/2) | 4/8 |
| Do nothing | timeout | timeout | timeout | timeout | 0/8 |
| Oracle, unranked | 3.0 | 3.0 | 3.0 | 3.0 | 8/8 |

Entries are median verified acquisitions to contract among successful runs; parenthetical fractions expose censoring. The retained-residual medians give a purely descriptive log-log exponent of (alpha=0.003) over these four widths. With two seeds per cell this is not an inferential scaling estimate. It is a feasibility signal consistent with bounded acquisition depth. Its accepted payload bitwise-zero probabilities ranged from 0.9866 to 0.9914.

Dense finite difference consumes (n+1) commissioning acquisitions before its ordinary loop. It failed one of two runs at 8 and 12 qubits and both runs at 16 inside the same 40-acquisition budget. That is a measured benchmark failure, not a large-(n) projection. Commissioned PI remained competitive, which must be published: this plant permits a constant-depth coded commissioning procedure. The architecture claim is therefore broader and more defensible than controller exclusivity.

The density-matrix/MPS overlap check passed at 4 and 8 qubits across two seeds, three ordinary commands, reference output, and payload output. The maximum declared output difference was 0.01832 against a 0.025 tolerance. It validates only the stated overlap.

## Validated marginal scale backend

The ring monitor has a closed-form component-marginal solution. Its ideal monitor and local-mirror payload expectations agree with direct Aer statevector evolution to (1.10\times10^{-14}) and (2.56\times10^{-14}), respectively, across 120 phase cases through 16 qubits. Its sparse analytic Jacobian agrees with finite differences to (5.90\times10^{-7}). Symmetric readout noise is exact. Finite-shot marginals are exact binomials, but the reduced backend omits cross-channel shot covariance.

A 20-seed closed-loop overlap at 8 and 12 qubits bounded the largest controller/cell success-rate difference by 0.10 and the largest successful-cell median acquisition difference by two. The validation passed its development thresholds. A failed earlier width-4 overlap is retained: at very small width the omitted joint-shot covariance was material. The frozen scale track therefore starts at 16, while the full Aer core retains widths 4 and 8.

On ten development seeds at widths 16, 256, 8,192, and 65,536, fixed-window Anderson succeeded in 40/40 cells with median acquisition counts 13, 11, 11, and 11. Its descriptive paired scaling exponent was −0.0178 with a development bootstrap interval [−0.0257, −0.0093]. Retained residual succeeded in 37/40 cells; all three failures were at width 16, and its complete-pair descriptive exponent was 0.0052 [−0.0041, 0.0306]. All tuning stopped after these development data and before any frozen outcome was generated. They remain development evidence.

The same run produced important negative results. Diagonal retained secant fell from 10/10 success at width 16 to 0/10 at 8,192 and 65,536. Class membership therefore does not guarantee controller adequacy on every plant. Commissioned PI remained viable and linear-state, although its two discarded coded probes exclude it from the strict retained cold-start class. Scalar-loss SPSA and do-nothing failed every development cell.

The extended dense-baseline development run used a 180-acquisition budget through width 128. Dense finite difference succeeded in 2/2, 2/2, and 1/2 runs at widths 4, 8, and 16, then 0/2 at 32, 64, and 128. Full Broyden succeeded through 16, in 1/2 runs at 32, and 0/2 at 64 and 128. Retained residual succeeded in all 12 paired runs. This is not the confirmation result, but it verifies that the frozen dense-baseline budget is long enough to reveal staleness and dense-model failure rather than truncating commissioning by construction.

## Fresh reproduction of the manuscript ladder

The original ladder package was recovered outside `TC_SUBMIT.zip` and copied byte-for-byte into `evidence/manuscript_scale_ladder_original`. Its preregistration SHA-256 is `f128dae481b8bd0951117fd6179f666c8088dd6d2f6dd68925039d16aa6778d5`.

The recovered runner was freshly executed on this Mac at (n=10^5) and (n=10^6), with seeds 31, 32, and 33 and all three arms. Both rungs reproduce the recovered aggregates to four decimals:

| Width | Retained residual | Diagonal retained secant | Do nothing | Fresh status |
|---:|---:|---:|---:|---|
| (10^5) | floor 0.0496; contract on acquisition 5 | floor 0.0383; acquisition 4 | floor 0.1512; no entry | PASS |
| (10^6) | floor 0.0496; contract on acquisition 5 | floor 0.0383; acquisition 4 | floor 0.1515; no entry | PASS |

The one-based acquisition numbers correct the recovered runner's zero-based `usable_at` field. The recovered raw (10^7) records and final (10^8) traces are preserved with hashes but were not rerun on this Mac because only about 0.3 GB of disk was free. The top rung has one seed and remains feasibility evidence, not a distribution.

### Provenance discrepancy

The registered and executed ladder used an eight-neighbour circular coupling mean with strength 0.30. The current `TC_SUBMIT` supplement says radius-one coupling and strength 0.20. Those are not the same plant. The result remains reproducible under the executed protocol, but the supplement must either describe that protocol exactly or the ladder must be rerun under the new description before submission. It cannot remain ambiguous.

## Time-to-contract consequence

At (n=10^8), a coordinate finite-difference Jacobian requires (n+1) sequential commissioning acquisitions before confirmation. Using the conservative maximum of 20 acquisitions observed for retained residual in the new 4–16 qubit MPS development ladder gives the following acquisition-only sensitivity:

| Per-acquisition latency | Retained no-growth hypothesis | Dense-FD best case | Acquisition-depth ratio |
|---:|---:|---:|---:|
| 100 microseconds | 2 ms | 10,000 s (2.78 h) | about 5,000,000x |
| 1 ms | 20 ms | 100,000 s (1.16 d) | about 5,000,000x |
| 100 ms | 2 s | 10,000,000 s (116 d) | about 5,000,000x |

These are projections from an explicit procedure and an explicit no-growth hypothesis. They are not executed (10^8)-qubit results. The manuscript's classical plant measured five acquisitions through (10^8), which would make the corresponding acquisition-depth ratio about 20 million. The stricter quantum benchmark currently has a larger absolute count because it adds finite-shot noise, three-pass confirmation, and payload validation.

The flat quantity is the sequential latency multiplier. Vector traffic remains (Theta(n)), controller arithmetic remains (Theta(n)), and total bounded state remains (Theta(n)). An end-to-end 10 ms claim at enormous width additionally requires enough local readout bandwidth, update parallelism, command-distribution bandwidth, and actuator settling. Without those measurements, the correct statement is:

> A qualifying maintenance layer removes channel count from the number of sequential plant revisits and avoids a superlinear host model; it does not make every physical or digital cost constant.

That is still the decisive architectural separation. A probe-based method pays physical latency repeatedly as dimension grows. A qualifying adjacent maintenance layer pays one full-vector frame per cycle and keeps its work in the same linear class as the controlled interface.

## Current conclusion

The results support the architecture strongly enough to justify a frozen confirmation campaign. They do not yet justify a public universal “10 ms at any scale” claim. The next decisive evidence is 30 paired confirmation seeds at the declared exact widths, a validated tiled extension, a measured host/readout-throughput model, and a corrected, immutable scale-ladder protocol. If those retain a near-zero acquisition-depth exponent while growing-depth comparators fail or diverge, the time-to-solution result is publication-grade and potentially breakthrough-grade.
