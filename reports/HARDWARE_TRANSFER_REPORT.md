# QSC-Bench hardware-transfer report

Date: 2026-08-14  
Status: v1.0.0 public evidence package; Metriq ingestion subject to upstream review.

## Result

The architecture transferred to a real QPU at small width. It did not fail when finite-shot simulator measurements were replaced by physical Tuna-9 measurements.

The frozen campaign used four component monitors, four disjoint payload qubits, 4,096 shots per acquisition, a five-acquisition deadline, two consecutive contract frames, and three unseen deterministic seeds. Every arm saw the same target, threshold, acquisition budget, and seed-specific command disturbance. The controller received measured marginals, never amplitudes, a hidden statevector, or provider calibration variables.

| Controller | Success | Entry acquisitions | Median provider execution to contract | Median final monitor RMSE | Median final payload |
|---|---:|---:|---:|---:|---:|
| Retained residual | 3/3 | 4, 4, 4 | 11.942 s | 0.02512 | 0.92657 |
| Diagonal retained secant | 3/3 | 4, 4, 5 | 12.238 s | 0.01488 | 0.92670 |
| Commissioned PI | 3/3 | 4, 4, 4 | 11.898 s | 0.02302 | 0.92737 |
| Dense finite difference | 0/3 | none | -- | 0.20080 | 0.86981 |
| Do nothing | 0/3 | none | -- | 0.20076 | 0.87872 |

The monitor threshold was 0.08 RMSE. The frozen payload threshold was 0.831671. All 75 confirmation jobs returned 4,096/4,096 shots. No scientific outcome was replaced. The development pilot and two failed provider-infrastructure diagnostics are retained but excluded from confirmation statistics.

Retained residual met the contract on acquisition 4 in all three trials. Diagonal secant, another retained linear-state controller, also passed every trial. Commissioned PI passed every trial after two charged coded probes. This is not evidence that one named equation is uniquely capable. It is consistent with the broader claim that component-resolved, bounded-state control can satisfy a short plant-interaction deadline without a dense host model.

Dense finite difference has a seven-acquisition minimum in this protocol: a base frame, four coordinate probes, and two confirmation frames. It therefore cannot pass a five-acquisition deadline. That is a measured execution of a frozen procedural ceiling, not evidence that finite differences are intrinsically inaccurate. Do-nothing remained outside the monitor contract, establishing that the commanded disturbance required restoration.

## Time to contract

Three different times are retained.

- The Tuna-9 result reports a median 11.942 seconds of provider-reported execution to retained-residual contract entry.
- The median measured local controller work through entry was 150.1 microseconds.
- Public-cloud queue, staging, and API time were much larger and varied sharply; they are not treated as physical feedback latency.

The hardware-observed acquisition depth therefore gives

    T_contract(tau) = 4 tau + 150.1 microseconds

for a hypothetical directly integrated interface with per-acquisition latency `tau`, using the measured width-four Python controller time. At `tau = 100 microseconds`, this evaluates to 0.550 ms. At `tau = 1 ms`, it is 4.150 ms. These are parameterized projections, not measured Tuna-9 latency and not large-width wall-clock claims. The simulator report separately records the host throughput and memory bandwidth needed at large width.

## Drift and infrastructure checks

The independent post-campaign reference moved by 0.00962 monitor RMSE. Payload bitwise-zero probability changed by -0.00635. Both are small relative to the frozen monitor tolerance and payload margin. The target and threshold were not updated after this diagnostic.

Quantum Inspire's server-side hybrid path worked on its emulator but failed on Tuna-9 in two recorded attempts. The confirmation campaign therefore used client-orchestrated direct jobs. Each next circuit was generated only after the preceding hardware result was consumed. This preserves adaptive causality, but it cannot reproduce the latency of an adjacent or embedded controller.

## Cross-provider check

A separately frozen OpenQuantum public-compute job ran on Rigetti Cepheus-1-108Q. One 1,024-shot acquisition returned four nominal and four shifted Ramsey marginals. The eight-channel RMSE against the ideal circuit was 0.09163, below the frozen 0.15 limit, and all 4/4 shifted responses had the correct sign. The job cost 1 Spark credit; 23 Spark and 0 paid Full credits remained afterward.

This second job tests component-observable circuit portability only. It contains no adaptive update and provides no convergence or scaling evidence. Any public use must follow OpenQuantum's attribution guidance at https://www.openquantum.com/citation.

## Cepheus 96-physical-qubit adaptive confirmation

A later frozen campaign used 48 controlled monitor channels and 48 disjoint
payload channels across 96 physical qubits on Rigetti Cepheus-1-108Q. It used
2,048 shots per acquisition, a four-acquisition deadline, two consecutive joint
contract frames, and one confirmation seed. The shared reference had payload
quality 0.90698; the frozen payload threshold was 0.80698.

The retained-residual arm entered contract at acquisition 4. Its acquisition-3
and acquisition-4 monitor RMSE values were 0.06213 and 0.06187, and its payload
qualities were 0.89196 and 0.90450. The paired do-nothing arm remained outside
contract through acquisition 3. Its fourth acquisition was omitted only after
the two-consecutive-pass deadline outcome became mathematically invariant; that
post-outcome futility rule and the omitted job are explicit in the evidence.

Under the benchmark's charging rule, dense finite difference has a structural
minimum of 51 acquisitions at width 48: one base acquisition, 48 coordinate
probes, and two confirmation frames. It was therefore outside the frozen
four-acquisition deadline and was not executed. The observed 4-versus-51
comparison combines a measured retained result and a procedural lower bound; it
is not a measured dense finite-difference runtime ratio.

This extends finite-width hardware transfer to 48 controlled channels, but only
for one paired seed and a shallow native single-Rx payload. It does not estimate
a hardware scaling exponent or controller reliability. The phase disturbance
was commanded in submitted circuits; no provider-private calibration state was
accessed. OpenQuantum exposed no device execution-duration field for these jobs,
so cloud submit-to-terminal time is retained as cloud provenance and is not
treated as QPU feedback latency.

## IQM Emerald static diagnostic

One frozen 54-qubit, 512-shot IQM Emerald circuit compared corrected and
unmaintained members within a paired static layout. Mean corrected bitwise-zero
probability was 0.98524, versus 0.77076 for the unmaintained members, a difference
of 0.21448. This is a command-effect diagnostic on another hardware family. It
is not an adaptive controller campaign, stability-contract result, or hardware
scaling result.

The public package also preserves the prior failed, pending, blocked, and
reference-inadmissible OpenQuantum generations. They are disclosed separately
and do not contribute to the successful v3 confirmation statistic.

## Claim boundary

This result strengthens the simulator finding in one important way: the adaptive monitor-to-command-to-payload loop works with real QPU samples, not only analytic or Aer samples.

It does not independently establish flat hardware scaling. Tuna-9 supplied only four monitored channels in this protocol, and the three-seed Wilson interval is wide: 3/3 corresponds to a 95% interval of approximately [0.439, 1.000]. A two-sided paired sign test for three retained wins over dense finite difference is not significant (`p = 0.25`). The observed disturbance is commanded at circuit level; the experiment does not access or rewrite provider-private calibration registers. The payload is a benchmark circuit, not a commercial quantum workload.

All 15 Tuna-9 trial reductions were also exported in Metriq's native result envelope and validated against the installed `QSCColdStartResult` model. This establishes local format compatibility; it is not upstream acceptance or a Metriq-hosted result.

The combined evidence is therefore:

1. frozen simulator evidence for bounded acquisition depth through 65,536 channels, with a labeled million-channel implementation extension;
2. real-QPU evidence that the adaptive interface and contract survive finite-shot hardware execution at width four; and
3. real-QPU adaptive transfer at 48 controlled channels on 96 physical qubits,
   with a single-seed limitation;
4. static cross-device diagnostics on Rigetti Cepheus and IQM Emerald; and
5. a published negative-evidence trail for the intervening failed and
   inadmissible hardware designs.

Together these materially strengthen the case for the proposed maintenance resource class. They make the architecture a credible breakthrough candidate. Community-established breakthrough status still requires independent review, upstream benchmark acceptance, and broader native-hardware replication.

Powered by OpenQuantum. See https://www.openquantum.com/citation.
