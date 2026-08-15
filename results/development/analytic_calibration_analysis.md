# QSC-Bench campaign analysis

Class-level result: **PASS**

This is finite-range simulator evidence, not a proof of asymptotic constant depth.

| Controller | Candidate | Success lower bound | alpha (95% CI) | Paired seeds | Result |
|---|---:|---:|---:|---:|---:|
| anderson_residual | yes | 0.722 | -0.018 [-0.026, -0.009] | 10 | PASS |
| commissioned_pi | no | 0.490 | 0.056 [0.026, 0.107] | 7 | FAIL/INCONCLUSIVE |
| diagonal_secant | yes | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |
| do_nothing | no | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |
| retained_residual | yes | 0.397 | 0.005 [-0.004, 0.031] | 7 | FAIL/INCONCLUSIVE |
| spsa | no | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |

Qualifying controllers: anderson_residual
