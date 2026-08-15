"""Reference reimplementation of the retained residual law, Regime A.

Built strictly from the published specification in Manuscript_FINAL_CLARIFIED:
  eq. (1): phi_{t+1} = Proj[ phi_t + H_t (y_t - p_hat_t) + mu (phi_t - phi_{t-1}) ]
  eq. (3): H_t = eta * diag( s_hat / max(g_hat, g_min) )
  Identification: first 3 acquisitions are retained fixed-amplitude excitations
  (0.150 rad per channel, sign uncorrelated with residual), charged to budget.
  Auxiliary state O(1)/channel: last action, running polarity s_hat, slope g_hat.
This is NOT the proprietary offline build. Tier: REFERENCE REIMPLEMENTATION.
Acceptance per Supplementary Table S1: from cycle 4, |corr(r, dphi)| > 0.9 and
||dphi||/||r|| in 0.65..1.8.
"""
import numpy as np


class RetainedLawRef:
    def __init__(self, n, target, phi0, lo=-np.pi, hi=np.pi,
                 eta=0.45, mu=0.20, g_min=0.15, beta=0.5,
                 id_cycles=3, id_amp=0.150, dtype=np.float64, seed=0):
        self.n = n
        self.dt = dtype
        self.y = np.asarray(target, dtype)
        self.phi = np.asarray(phi0, dtype).copy()
        self.phi_prev = self.phi.copy()
        self.lo, self.hi = lo, hi
        self.eta, self.mu, self.g_min, self.beta = eta, mu, g_min, beta
        self.id_cycles, self.id_amp = id_cycles, id_amp
        self.t = 0
        self.rng = np.random.default_rng(seed)
        # bounded auxiliary state, O(1) per channel
        self.s_hat = np.zeros(n, np.float16 if n > 10**7 else dtype)  # polarity estimate in [-1,1]
        self.g_hat = np.full(n, 0.5, np.float16 if n > 10**7 else dtype)  # slope magnitude
        self.p_prev = None
        self.dphi_last = np.zeros(n, dtype)

    def step(self, p_hat):
        """One closed-loop cycle: consume acquisition p_hat, emit next phi."""
        p_hat = np.asarray(p_hat, self.dt)
        # --- update auxiliary state from action-response correlation ---
        if self.p_prev is not None:
            dp = p_hat - self.p_prev
            act = self.dphi_last
            mask = np.abs(act) > 1e-9
            corr = np.sign(act) * np.sign(dp)          # one signed bit / channel
            slope = np.abs(dp) / np.maximum(np.abs(act), 1e-9)
            b = self.beta
            sh = self.s_hat.astype(self.dt)
            gh = self.g_hat.astype(self.dt)
            sh[mask] = (1 - b) * sh[mask] + b * corr[mask]
            gh[mask] = (1 - b) * gh[mask] + b * np.clip(slope[mask], 0.02, 5.0)
            self.s_hat = sh.astype(self.s_hat.dtype)
            self.g_hat = gh.astype(self.g_hat.dtype)
        self.p_prev = p_hat.copy()

        r = self.y - p_hat
        if self.t < self.id_cycles:
            # retained identification update: kept and built upon, charged like any acquisition
            eps = self.rng.choice(np.array([-1.0, 1.0], self.dt), size=self.n)
            dphi = self.id_amp * eps
        else:
            sh = self.s_hat.astype(self.dt)
            gh = self.g_hat.astype(self.dt)
            s_eff = np.sign(sh)
            s_eff[s_eff == 0] = 1.0
            conf = np.clip(np.abs(sh), 0.0, 1.0)       # confidence gates the gain
            H = self.eta * conf * s_eff / np.maximum(gh, self.g_min)
            dphi = H * r + self.mu * (self.phi - self.phi_prev)
        new_phi = np.clip(self.phi + dphi, self.lo, self.hi)
        self.dphi_last = new_phi - self.phi
        self.phi_prev = self.phi
        self.phi = new_phi
        self.t += 1
        return self.phi
