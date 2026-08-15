# QSC-Bench campaign analysis

Class-level result: **PASS**

This is finite-range simulator evidence, not a proof of asymptotic constant depth.

| Controller | Candidate | Success lower bound | alpha (95% CI) | Paired seeds | Result |
|---|---:|---:|---:|---:|---:|
| anderson_residual | yes | 0.886 | -0.002 [-0.015, 0.007] | 30 | PASS |
| commissioned_pi | no | 0.488 | 0.095 [0.064, 0.132] | 14 | FAIL/INCONCLUSIVE |
| diagonal_secant | yes | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |
| do_nothing | no | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |
| oracle | no | 0.886 | -0.000 [-0.000, -0.000] | 30 | FAIL/INCONCLUSIVE |
| retained_residual | yes | 0.886 | 0.005 [-0.006, 0.012] | 30 | PASS |
| spsa | no | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |

Qualifying controllers: anderson_residual, retained_residual
