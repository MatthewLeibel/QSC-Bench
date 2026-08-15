"""n=1e8 rung: disk-backed chunked execution of the reference law, Broyden, do-nothing.
Persistent state in float32 memmaps under /home/claude/rnd/mm/. Gains, signs and
targets are procedural (regenerated per chunk per cycle from counter-keyed RNG).
Coupling uses 4-element halos across chunk edges. Same physics and constants as
ladder.py; equivalence spot-checked at n=1e6 against the in-RAM runner.
"""
import numpy as np, os, sys, json, time, resource

N = 10 ** 8
CH = 2 ** 21            # 16.7M per chunk
SEV = 0.05
CYCLES = 24
CAL = dict(eta=0.65, mu=0.15, beta=0.50, g_min=0.15)
MM = "/home/claude/rnd/mm"


def rng_for(seed, tag, chunk, cycle=0):
    return np.random.default_rng(np.random.SeedSequence([seed, tag, chunk, cycle]))


def chunk_slices(n, ch):
    return [(i, min(i + ch, n)) for i in range(0, n, ch)]


def proc_target(seed, a, b):
    return rng_for(seed, 1, a).uniform(0.30, 0.70, b - a).astype(np.float32)


def proc_gs(seed, a, b):
    r = rng_for(seed, 2, a)
    g = np.exp(r.uniform(np.log(0.3), np.log(1.0), b - a)).astype(np.float32)
    s = r.choice(np.array([-1.0, 1.0], np.float32), b - a)
    return g, s


def couple_chunk(phi_mm, a, b, n):
    """8-neighbour mean over +-1..4 with wraparound halos."""
    lo, hi = (a - 4) % n, (b + 4) % n
    left = phi_mm[a - 4:a] if a >= 4 else np.concatenate([phi_mm[a - 4:], phi_mm[:a]])
    right = phi_mm[b:b + 4] if b + 4 <= n else np.concatenate([phi_mm[b:], phi_mm[:(b + 4) % n]])
    ext = np.concatenate([left, np.asarray(phi_mm[a:b]), right])
    acc = np.zeros(b - a, np.float32)
    for k in (1, 2, 3, 4):
        acc += ext[4 - k:4 - k + (b - a)] + ext[4 + k:4 + k + (b - a)]
    return acc / 8.0


AUX16 = {"s_hat", "g_hat", "b_g", "b_s"}
def open_state(names, mode):
    return {nm: np.zeros(N, np.float16 if nm in AUX16 else np.float32) for nm in names}


def run(arm, seed):
    os.makedirs(MM, exist_ok=True)
    sl = chunk_slices(N, CH)
    t0 = time.time()
    if arm == "ref":
        st = open_state(["phi", "phi_prev", "p_prev", "theta", "s_hat", "g_hat"], "w+")
        for a, b in sl:
            st["theta"][a:b] = rng_for(seed, 3, a).normal(0, 0.4, b - a).astype(np.float32)
            st["g_hat"][a:b] = 0.5
        errs = []
        for t in range(CYCLES):
            sq = cnt = 0.0
            for ci, (a, b) in enumerate(sl):
                g, s = proc_gs(seed, a, b)
                y = proc_target(seed, a, b)
                phi = np.asarray(st["phi"][a:b]); th = np.asarray(st["theta"][a:b])
                x = g * s * (phi - th) + 0.30 * (couple_chunk(st["phi"], a, b, N) - couple_chunk(st["theta"], a, b, N))
                p = 0.5 + 0.5 * np.tanh(x) + rng_for(seed, 4, a, t).normal(0, 0.003, b - a).astype(np.float32)
                r_ = y - p
                sq += float(np.dot(r_, r_)); cnt += b - a
                # auxiliary update from action-response correlation
                if t > 0:
                    act = phi - np.asarray(st["phi_prev"][a:b])
                    dp = p - np.asarray(st["p_prev"][a:b])
                    m = np.abs(act) > 1e-9
                    corr = np.sign(act) * np.sign(dp)
                    slope = np.abs(dp) / np.maximum(np.abs(act), 1e-9)
                    sh = np.asarray(st["s_hat"][a:b]); gh = np.asarray(st["g_hat"][a:b])
                    sh[m] = 0.5 * sh[m] + 0.5 * corr[m]
                    gh[m] = 0.5 * gh[m] + 0.5 * np.clip(slope[m], 0.02, 5.0)
                    st["s_hat"][a:b] = sh; st["g_hat"][a:b] = gh
                st["p_prev"][a:b] = p
                # update
                if t < 3:
                    dphi = 0.150 * rng_for(seed, 5, a, t).choice(np.array([-1., 1.], np.float32), b - a)
                else:
                    sh = np.asarray(st["s_hat"][a:b]); gh = np.asarray(st["g_hat"][a:b])
                    se = np.sign(sh); se[se == 0] = 1.0
                    H = CAL["eta"] * np.clip(np.abs(sh), 0, 1) * se / np.maximum(gh, CAL["g_min"])
                    dphi = H * r_ + CAL["mu"] * (phi - np.asarray(st["phi_prev"][a:b]))
                newphi = np.clip(phi + dphi, -np.pi, np.pi)
                st["phi_prev"][a:b] = phi; st["phi"][a:b] = newphi
                # drift
                th += rng_for(seed, 6, a, t).normal(0, SEV, b - a).astype(np.float32); th -= 0.02 * th
                st["theta"][a:b] = th
            errs.append(round(float(np.sqrt(sq / cnt)), 4))
    elif arm == "broyden":
        st = open_state(["phi", "phi_p", "p_p", "theta", "b_g", "b_s"], "w+")
        for a, b in sl:
            st["theta"][a:b] = rng_for(seed, 3, a).normal(0, 0.4, b - a).astype(np.float32)
            st["b_g"][a:b] = 0.5; st["b_s"][a:b] = 1.0
        errs = []
        for t in range(CYCLES):
            sq = cnt = 0.0
            for a, b in sl:
                g, s = proc_gs(seed, a, b); y = proc_target(seed, a, b)
                phi = np.asarray(st["phi"][a:b]); th = np.asarray(st["theta"][a:b])
                x = g * s * (phi - th) + 0.30 * (couple_chunk(st["phi"], a, b, N) - couple_chunk(st["theta"], a, b, N))
                p = 0.5 + 0.5 * np.tanh(x) + rng_for(seed, 4, a, t).normal(0, 0.003, b - a).astype(np.float32)
                r_ = y - p; sq += float(np.dot(r_, r_)); cnt += b - a
                if t > 0:
                    dphi = phi - np.asarray(st["phi_p"][a:b]); dp = p - np.asarray(st["p_p"][a:b])
                    m = np.abs(dphi) > 1e-6
                    sec = np.where(m, dp / np.where(m, dphi, 1), 0).astype(np.float32)
                    upd = np.abs(sec) > 0.02
                    bg = np.asarray(st["b_g"][a:b]); bs = np.asarray(st["b_s"][a:b])
                    bg[upd] = 0.5 * bg[upd] + 0.5 * np.abs(sec[upd]); bs[upd] = np.sign(sec[upd])
                    st["b_g"][a:b] = bg; st["b_s"][a:b] = bs
                st["phi_p"][a:b] = phi; st["p_p"][a:b] = p
                if t < 2:
                    newphi = np.clip(phi + 0.15 * rng_for(seed, 9, a, t).choice(np.array([-1., 1.], np.float32), b - a), -np.pi, np.pi)
                else:
                    step = 0.6 * np.asarray(st["b_s"][a:b]) * r_ / np.maximum(np.asarray(st["b_g"][a:b]), 0.15)
                    newphi = np.clip(phi + np.clip(step, -0.6, 0.6), -np.pi, np.pi)
                st["phi"][a:b] = newphi
                th += rng_for(seed, 6, a, t).normal(0, SEV, b - a).astype(np.float32); th -= 0.02 * th
                st["theta"][a:b] = th
            errs.append(round(float(np.sqrt(sq / cnt)), 4))
    else:  # do-nothing
        st = open_state(["phi", "theta"], "w+")
        for a, b in sl:
            st["theta"][a:b] = rng_for(seed, 3, a).normal(0, 0.4, b - a).astype(np.float32)
        errs = []
        for t in range(CYCLES):
            sq = cnt = 0.0
            for a, b in sl:
                g, s = proc_gs(seed, a, b); y = proc_target(seed, a, b)
                phi = np.asarray(st["phi"][a:b]); th = np.asarray(st["theta"][a:b])
                x = g * s * (phi - th) + 0.30 * (couple_chunk(st["phi"], a, b, N) - couple_chunk(st["theta"], a, b, N))
                p = 0.5 + 0.5 * np.tanh(x) + rng_for(seed, 4, a, t).normal(0, 0.003, b - a).astype(np.float32)
                r_ = y - p; sq += float(np.dot(r_, r_)); cnt += b - a
                th += rng_for(seed, 6, a, t).normal(0, SEV, b - a).astype(np.float32); th -= 0.02 * th
                st["theta"][a:b] = th
            errs.append(round(float(np.sqrt(sq / cnt)), 4))
    wall = time.time() - t0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    usable = next((t for t, e in enumerate(errs) if e < 0.10), None)
    out = dict(n=N, seed=seed, arm=arm, usable_at=usable, err6=errs[6],
               floor=round(float(np.mean(errs[12:])), 4), wall_s=round(wall, 1),
               peak_gb=round(peak, 2), errs=errs)
    print(json.dumps(out)); return out


if __name__ == "__main__":
    run(sys.argv[2], int(sys.argv[1]))
