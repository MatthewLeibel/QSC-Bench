"""Scale ladder runner. Fused, chunked, float32 above 1e7.

Plant (procedural where possible): p_i = 0.5 + 0.5*tanh( g_i*s_i*(phi_i - theta_i) + c*L[phi] )
  g_i log-uniform 0.3..1.0, s_i = +/-1 hidden, both regenerated per chunk from seed.
  L[phi] = 8-neighbour local coupling (mean of +-1..4 shifted phi), c=0.30.
  theta OU drift: theta += drift * N(0,1) - 0.02*theta, persisted (the only plant state).
Controllers: reference retained law (calibrated constants), diagonal Broyden, do-nothing.
"""
import numpy as np, time, json, sys, resource

C_COUPLE = 0.30
CAL = dict(eta=0.65, mu=0.15, beta=0.50, g_min=0.15)


def gains_signs(n, seed, dt):
    rng = np.random.default_rng(seed + 777)
    g = np.exp(rng.uniform(np.log(0.3), np.log(1.0), n)).astype(dt)
    s = rng.choice(np.array([-1.0, 1.0], dt), n)
    return g, s


def couple(phi):
    acc = np.zeros_like(phi)
    for k in (1, 2, 3, 4):
        acc += np.roll(phi, k) + np.roll(phi, -k)
    return acc / 8.0


def measure(phi, theta, g, s, noise_rng, dt):
    x = g * s * (phi - theta) + C_COUPLE * (couple(phi) - couple(theta))
    p = 0.5 + 0.5 * np.tanh(x)
    p += noise_rng.normal(0, 0.003, phi.shape).astype(dt)
    return p


def drift(theta, rng, sev, dt):
    theta += rng.normal(0, sev, theta.shape).astype(dt)
    theta -= 0.02 * theta
    return theta


def run_arm(n, seed, arm, sev=0.05, cycles=24, dt=np.float32):
    rng = np.random.default_rng(seed)
    target = rng.uniform(0.30, 0.70, n).astype(dt)
    g, s = gains_signs(n, seed, dt)
    theta = rng.normal(0, 0.4, n).astype(dt)
    noise_rng = np.random.default_rng(seed + 1)
    drift_rng = np.random.default_rng(seed + 2)
    phi = np.zeros(n, dt)
    errs = []
    t0 = time.time()
    if arm == "ref":
        from tlref import RetainedLawRef
        c = RetainedLawRef(n, target, phi, dtype=dt, seed=seed, **CAL)
        for t in range(cycles):
            p = measure(c.phi, theta, g, s, noise_rng, dt)
            errs.append(float(np.sqrt(np.mean((target - p) ** 2))))
            c.step(p)
            theta = drift(theta, drift_rng, sev, dt)
    elif arm == "broyden":
        # retained-secant: 2 excitation reads then damped per-channel secant refresh
        b_g = np.full(n, 0.5, dt); b_s = np.ones(n, dt)
        phi_p = phi.copy(); p_p = None
        for t in range(cycles):
            p = measure(phi, theta, g, s, noise_rng, dt)
            errs.append(float(np.sqrt(np.mean((target - p) ** 2))))
            if p_p is not None:
                dphi = phi - phi_p; dp = p - p_p
                m = np.abs(dphi) > 1e-6
                sec = np.where(m, dp / np.where(m, dphi, 1), 0).astype(dt)
                upd = np.abs(sec) > 0.02
                b_g[upd] = 0.5 * b_g[upd] + 0.5 * np.abs(sec[upd])
                b_s[upd] = np.sign(sec[upd])
            phi_p = phi.copy(); p_p = p.copy()
            if t < 2:
                exc = np.random.default_rng(seed + 9 + t).choice(np.array([-1., 1.], dt), n)
                phi = np.clip(phi + 0.15 * exc, -np.pi, np.pi)
            else:
                step = 0.6 * b_s * (target - p) / np.maximum(b_g, 0.15)
                phi = np.clip(phi + np.clip(step, -0.6, 0.6), -np.pi, np.pi)
            theta = drift(theta, drift_rng, sev, dt)
    else:  # do-nothing
        for t in range(cycles):
            p = measure(phi, theta, g, s, noise_rng, dt)
            errs.append(float(np.sqrt(np.mean((target - p) ** 2))))
            theta = drift(theta, drift_rng, sev, dt)
    wall = time.time() - t0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # GB-ish (kB->GB)
    usable = next((t for t, e in enumerate(errs) if e < 0.10), None)
    return dict(n=n, seed=seed, arm=arm, usable_at=usable,
                floor=float(np.mean(errs[12:])), err6=errs[min(6, len(errs)-1)],
                wall_s=round(wall, 1), peak_gb=round(peak, 2),
                errs=[round(e, 4) for e in errs])


if __name__ == "__main__":
    n = int(float(sys.argv[1])); seed = int(sys.argv[2]); arm = sys.argv[3]
    dt = np.float32 if n >= 10**7 else np.float64
    out = run_arm(n, seed, arm, dt=dt)
    print(json.dumps(out))
