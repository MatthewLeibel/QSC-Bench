# QSC-Bench Tuna-9 hardware report

Hardware-transfer decision: **PASS**.

| Controller | Success | Median acquisitions | Median provider-execution s to contract | Final RMSE | Final payload |
|---|---:|---:|---:|---:|---:|
| retained_residual | 3/3 | 4.0 | 11.942 | 0.0251 | 0.9266 |
| diagonal_secant | 3/3 | 4.0 | 12.238 | 0.0149 | 0.9267 |
| commissioned_pi | 3/3 | 4.0 | 11.898 | 0.0230 | 0.9274 |
| dense_fd | 0/3 | -- | -- | 0.2008 | 0.8698 |
| do_nothing | 0/3 | -- | -- | 0.2008 | 0.8787 |

The table reports three frozen confirmation seeds per arm. The 95% Wilson interval for 3/3 is wide; this campaign establishes feasibility and paired small-width behavior, not a population-level hardware reliability rate.

The independent post-campaign reference changed by 0.00962 monitor RMSE and -0.00635 in payload bitwise-zero probability. This diagnostic did not alter the frozen target or thresholds.

Dense finite difference has a seven-acquisition structural minimum (five commissioning frames plus two ordinary confirmation frames) and therefore cannot enter the declared contract within the frozen five-acquisition deadline. Commissioned PI pays two separate coded probes. Retained residual and diagonal secant use ordinary retained full-vector acquisitions throughout.

Provider-reported direct-job execution, controller update time, and public-cloud wall time are separate fields. No queue delay is presented as physical QPU latency, and no projected large-width time is presented as measured hardware time.

For retained residual, the hardware-observed acquisition depth gives T_contract(tau) = 4 tau + 150.1 microseconds of measured local controller work (median). At tau = 100 microseconds this is 0.550 ms: a parameterized direct-feedback projection, not measured Tuna-9 time.

This is a real-QPU hardware-in-the-loop transfer at width four. It does not access provider-private calibration registers and does not establish flat physical scaling; that claim remains finite-range simulator evidence.

Nothing in this package has been uploaded to Metriq, pushed to GitHub, or published.
