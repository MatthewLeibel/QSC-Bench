# QSC-Bench campaign analysis

Class-level result: **PASS**

This is finite-range simulator evidence, not a proof of asymptotic constant depth.

| Controller | Candidate | Success lower bound | alpha (95% CI) | Paired seeds | Result |
|---|---:|---:|---:|---:|---:|
| anderson_residual | yes | 0.095 | n/a | 1 | FAIL/INCONCLUSIVE |
| commissioned_pi | no | 0.095 | n/a | 1 | FAIL/INCONCLUSIVE |
| diagonal_secant | yes | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |
| do_nothing | no | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |
| oracle | no | 0.342 | -0.000 [-0.000, -0.000] | 2 | FAIL/INCONCLUSIVE |
| retained_residual | yes | 0.342 | -0.065 [-0.071, -0.056] | 2 | PASS |
| spsa | no | 0.000 | n/a | 0 | FAIL/INCONCLUSIVE |

Qualifying controllers: retained_residual
