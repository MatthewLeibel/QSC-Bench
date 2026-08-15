# Manuscript review: stability contract for scalable hybrid computing

## Bottom line

The package now presents a coherent and substantially better-scoped systems argument than the earlier reviews imply. The main contribution is not analog matrix multiplication, the roofline heuristic, physical interference, or heavy-ball momentum by itself. It is the separation of maintenance cost into sequential acquisition depth, interface traffic, host arithmetic, and retained state; the information-rate lower bound; and a controller/resource class that can reach the acquisition floor without moving a superlinear maintenance model across the host boundary.

The manuscript does retain the stability contract. It defines four conditional guarantees—restoration, spread tolerance, composability, and operability—and ties each to preconditions, evidence, and failure boundaries. It does not claim universal analog stabilizability, constant total information, constant host arithmetic, fabricated 100-million-channel hardware, native-drift correction on quantum processors, or a universal energy advantage.

The strongest remaining issue discovered in this review is executable state accounting. The submitted reproduction class retains both the real-valued correlation accumulator `scorr` and a cached floating-point `shat`, although the paper's six-word count derives `shat = sign(scorr)` and therefore allocates no seventh word. This is a code/paper mismatch. It does not change the published trajectories because the cache is algebraically redundant, but it must be corrected before the reference code is used to substantiate the six-word implementation claim.

## What the paper actually claims

The target hardware class has a persistent writable configuration, one parallel component-resolved acquisition, a locally identifiable response-to-control map, a revisit period shorter than the drift staleness time, and bounded per-channel auxiliary controller state. The physical configuration is retained computational state. Identification actions remain applied instead of being measured and reverted.

The reference law is

\[
\phi_{t+1}=\Pi\!\left[\phi_t+H_t(y_t-\hat p_t)+\mu(\phi_t-\phi_{t-1})\right],
\]

with

\[
H_t=\eta\,\mathrm{diag}\!\left(\hat s_{t,c}/\max(\hat g_{t,c},g_{\min})\right).
\]

The disclosed constants are \(\eta=0.65\), \(\mu=0.15\), estimator smoothing \(\beta=0.50\), slope floor \(g_{\min}=0.15\), retained identification amplitude 0.150 for the first three updates, and projection to \([-3,3]\). The first three identification moves are part of the live trajectory. The cold-start count is therefore three identification acquisitions plus one or two correction acquisitions on the manuscript's tested monitor families.

The six floating-point words are current configuration, previous configuration, last applied action, last acquisition, the real action-response correlation, and the slope estimate. The polarity is derived from the correlation. A fixed per-channel identification sign is additional immutable one-bit metadata.

The manuscript's “flat” result is flat sequential acquisition depth at fixed normalized RMS tolerance, under a uniform operating envelope. It is not flat information, memory footprint, arithmetic, sensor count, physical area, actuator energy, or worst-coordinate error. The host still performs \(\Theta(n)\) work and exchanges \(\Theta(n)\) data per maintenance cycle.

## Mathematical audit

### Causality and information rate

Proposition 1 now states the causal order. The innovation occurs, a genie-aided encoder observes it, a message with conditional entropy at most \(C\) is sent, and the decoder/controller applies the correction. Reconstructing the innovation from the correction reduces the problem to the Gaussian rate-distortion converse:

\[
C\ge \frac{n}{2}\log_2\!\frac{\sigma_w^2}{\mathcal D}.
\]

The main text explicitly distinguishes frame payload from useful mutual information. Its component-resolved corollary requires a uniformly positive per-channel information contribution and a sufficient coefficient, not merely \(n\) returned numbers. The supplement also handles correlated Gaussian innovation by reverse water filling and gives a valid counterexample showing that many active modes above the target distortion do not alone force a linear rate; the margin must be above the water-filling level.

### Rectangular dynamics

The orientation is correct. With response Jacobian \(J\in\mathbb R^{n\times m}\) and controller gain \(H\in\mathbb R^{m\times n}\), the configuration-space loop product is \(HJ\). The paper reduces the dynamics to a controlled subspace \(V\), using \(\widetilde J=JV\) and \(\widetilde K=V^T H\). The lifted recurrence is dimensionally consistent:

\[
\Phi_t=
\begin{bmatrix}
(1+\mu)I-\widetilde K_t\widetilde J_t & -\mu I\\
I & 0
\end{bmatrix}.
\]

The theorem is conditional on a common Lyapunov certificate with dimension-uniform rate and conditioning. It correctly warns that pointwise Schur stability is insufficient for a switched family and does not claim a proof of that condition for every experimental plant.

### Disclosed diagonal certificate

The explicit certificate

\[
P_2=\begin{bmatrix}1&-0.275\\-0.275&0.15\end{bmatrix},\qquad \alpha=0.765
\]

was checked independently in `tests/test_manuscript_certificate.py`. It is positive definite, has condition number approximately 15.72, and gives a positive endpoint margin for the loop-gain sector \([0.20,1.00]\). Matrix convexity of \(A(g)^TP_2A(g)\) makes the endpoint test sufficient over the complete scalar sector. The Kronecker lift preserves the rate and condition number across channel count in the separable diagonal regime.

The theorem does not prove the sparse coupled regime. The manuscript says so. QSC-Bench must therefore measure the coupling boundary instead of importing the diagonal certificate as if it covered the RZZ plant.

## Evidence hierarchy

| Claim | Evidence in the package | Correct label |
|---|---|---|
| Four-to-five acquisition cold start on tested monitor families | Simulated photonic/device families and the disclosed controller class | Demonstrated in the reported simulations, not universal |
| Flat normalized RMS hold to \(10^6\) photonic channels | Photonic model | Simulated |
| Scale ladder to \(10^8\) channels | Coupled heterogeneous device model; one seed at \(10^8\) | Modeled/simulated scale extension, not hardware |
| Quantum operation | Three commercial processors with software-injected command disturbance | Hardware execution under injected disturbance, not native-drift correction |
| IMC accuracy, energy, area | Device/workload/component models | Modeled architecture; no fabricated silicon |
| Controller-state area = 4.4% | Six 16-bit state words only | State-storage estimate, not complete-controller area |
| Diagonal secant can attain the same acquisition class | Reported scale ladder, often lower residual/fewer acquisitions | In-class comparator, not excluded baseline |
| Dense finite difference cost | \(n+1\) interactions to form one gradient | Lower bound to first update, not measured convergence time |

The manuscript now handles the diagonal secant result correctly. It says the resource-class floor is larger than one equation and does not claim the heavy-ball law is the sole possible in-class controller. The distinct claimed advantages are cold-start identification, bounded state, robustness within the tested drift/coupling regime, and simultaneous attainment of the declared axes.

## Evidence the paper reports against itself

The negative results are scientifically valuable and should remain:

- Scheduled calibration wins on the modeled per-column gain/offset surface because a complete sweep costs only 16 acquisition-equivalents and falls below the measured breakeven.
- Host time per channel varies by 4.16× across the tested range because the \(O(n)\) update becomes memory-bandwidth bound. Only acquisition depth is flat.
- Magnitude-only readout succeeds because retained action-response correlation recovers polarity, falsifying an earlier sign-transmission prediction.
- Photonic dither wins at small width and fails only after its sweep becomes stale at large width.
- PI can win on a known static plant; the retained law is not a universal optimizer.
- All tested methods exceed tolerance beyond the drift frontier.

These results make a neutral public benchmark more credible. They should not be tuned away.

## Remaining corrections before another manuscript submission

**Submission-blocking: correct the scale-ladder plant description or rerun it.** The recovered preregistration and runner use an eight-neighbour circular mean at coupling 0.30. The current supplement says radius-one coupling at 0.20. Fresh runs at `10^5` and `10^6` reproduce the recovered aggregates, so the numerical records are reproducible under the executed protocol, but the paper presently describes a different plant.

1. **Fix the reproduction implementation's seventh cached vector.** Derive polarity from `scorr` on demand, as the supplement's pseudocode does, or report seven floating-point arrays. QSC-Bench implements the former and tests the exact count.

2. **Clarify the one-bit identification sign in area accounting.** Six 16-bit words equal 96 bits per channel; the persistent identification sign makes the exact implementation 97 bits per channel unless stored elsewhere or generated procedurally. The rounded tile fraction remains about 4.4%, but the text should say what is and is not included.

3. **Use “persistent state,” not “auxiliary state,” consistently.** The six-word list includes the current and previous configurations, so not all six words are auxiliary beyond configuration.

4. **Preserve the acquisition/traffic/arithmetic distinction everywhere.** “Constant time” is only defensible as constant sequential acquisition depth at fixed plant latency with \(O(n)\) parallel sensing, traffic, and host work. The manuscript mostly does this correctly; publicity must do the same.

5. **Do not turn the physical analogy into an implementation claim.** The paper implements the heavy-ball recurrence digitally against physical measurements. It does not demonstrate a wave resonator physically storing \(\mu(\phi_t-\phi_{t-1})\), phase hardware applying \(\eta\), or an entirely autonomous optical optimization loop. Those are future architectures, not evidence in this package.

6. **Resolve page policy deliberately.** The rendered main paper is 16 pages. The package README acknowledges that an external page-limit check remains open. No submission package should be called final until the target venue's current policy is checked.

## Consequence for QSC-Bench

QSC-Bench should test the paper's actual claim, not a stronger marketing version. The neutral hypothesis is that retained component-resolved controllers can keep sequential acquisition depth from scaling with channel count when the plant remains locally informative, sufficiently conditioned, slowly drifting, and weakly coupled. The benchmark must also expose where diagonal secant, commissioned PI, dense model-based control, or scheduled recalibration is better.

The first quantum smoke runs already validated the need for those boundaries. An early monitor circuit admitted a second fringe-equivalent root. Controllers could match the monitor while leaving a large physical phase error, and the payload rejected them. Moving the main track to the central high-slope fringe restored the intended capture basin. The ambiguous-fringe case belongs in a failure track, not in the main result.
