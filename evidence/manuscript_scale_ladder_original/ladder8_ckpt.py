"""Checkpointed n=1e8 rung. Usage: python3 ladder8_ckpt.py <arm> <seed> <cycles_this_call>
State persists in /home/claude/rnd/ck_<arm>_<seed>/ as .npy files plus meta.json.
Physics and constants identical to ladder8.py (equivalence-checked at 1e6)."""
import numpy as np, os, sys, json, time

N = 10 ** 8
CH = 2 ** 21
SEV = 0.05
TOTAL = 24
CAL = dict(eta=0.65, mu=0.15, beta=0.50, g_min=0.15)


def rng_for(seed, tag, chunk, cycle=0):
    return np.random.default_rng(np.random.SeedSequence([seed, tag, chunk, cycle]))


def slices():
    return [(i, min(i + CH, N)) for i in range(0, N, CH)]


def proc_target(seed, a, b):
    return rng_for(seed, 1, a).uniform(0.30, 0.70, b - a).astype(np.float32)


def proc_gs(seed, a, b):
    r = rng_for(seed, 2, a)
    g = np.exp(r.uniform(np.log(0.3), np.log(1.0), b - a)).astype(np.float32)
    s = r.choice(np.array([-1.0, 1.0], np.float32), b - a)
    return g, s


def couple_chunk(arr, a, b, n):
    left = arr[a - 4:a] if a >= 4 else np.concatenate([arr[a - 4:], arr[:a]])
    right = arr[b:b + 4] if b + 4 <= n else np.concatenate([arr[b:], arr[:(b + 4) % n]])
    ext = np.concatenate([left, arr[a:b], right])
    acc = np.zeros(b - a, np.float32)
    for k in (1, 2, 3, 4):
        acc += ext[4 - k:4 - k + (b - a)] + ext[4 + k:4 + k + (b - a)]
    return acc / 8.0


ARRS = dict(ref=[("phi", np.float32), ("phi_prev", np.float32), ("p_prev", np.float32),
                 ("theta", np.float32), ("s_hat", np.float16), ("g_hat", np.float16)],
            broyden=[("phi", np.float32), ("phi_p", np.float32), ("p_p", np.float32),
                     ("theta", np.float32), ("b_g", np.float16), ("b_s", np.float16)],
            nothing=[("phi", np.float32), ("theta", np.float32)])


def main(arm, seed, k):
    d = f"/home/claude/rnd/ck_{arm}_{seed}"
    os.makedirs(d, exist_ok=True)
    meta_p = f"{d}/meta.json"
    if os.path.exists(meta_p):
        meta = json.load(open(meta_p))
        st = {nm: np.load(f"{d}/{nm}.npy") for nm, _ in ARRS[arm]}
    else:
        meta = dict(t=0, errs=[], wall=0.0)
        st = {nm: np.zeros(N, dt) for nm, dt in ARRS[arm]}
        for a, b in slices():
            st["theta"][a:b] = rng_for(seed, 3, a).normal(0, 0.4, b - a).astype(np.float32)
        if arm == "ref":
            st["g_hat"][:] = 0.5
        if arm == "broyden":
            st["b_g"][:] = 0.5
            st["b_s"][:] = 1.0
    t0 = time.time()
    for _ in range(k):
        t = meta["t"]
        if t >= TOTAL:
            break
        sq = cnt = 0.0
        for a, b in slices():
            g, s = proc_gs(seed, a, b)
            y = proc_target(seed, a, b)
            phi = st["phi"][a:b].copy()
            th = st["theta"][a:b]
            x = g * s * (phi - th) + 0.30 * (couple_chunk(st["phi"], a, b, N) - couple_chunk(st["theta"], a, b, N))
            p = 0.5 + 0.5 * np.tanh(x) + rng_for(seed, 4, a, t).normal(0, 0.003, b - a).astype(np.float32)
            r_ = y - p
            sq += float(np.dot(r_, r_)); cnt += b - a
            if arm == "ref":
                if t > 0:
                    act = phi - st["phi_prev"][a:b]
                    dp = p - st["p_prev"][a:b]
                    m = np.abs(act) > 1e-9
                    corr = np.sign(act) * np.sign(dp)
                    slope = np.abs(dp) / np.maximum(np.abs(act), 1e-9)
                    sh = st["s_hat"][a:b].astype(np.float32); gh = st["g_hat"][a:b].astype(np.float32)
                    sh[m] = 0.5 * sh[m] + 0.5 * corr[m]
                    gh[m] = 0.5 * gh[m] + 0.5 * np.clip(slope[m], 0.02, 5.0)
                    st["s_hat"][a:b] = sh.astype(np.float16); st["g_hat"][a:b] = gh.astype(np.float16)
                st["p_prev"][a:b] = p
                if t < 3:
                    dphi = 0.150 * rng_for(seed, 5, a, t).choice(np.array([-1., 1.], np.float32), b - a)
                else:
                    sh = st["s_hat"][a:b].astype(np.float32); gh = st["g_hat"][a:b].astype(np.float32)
                    se = np.sign(sh); se[se == 0] = 1.0
                    H = CAL["eta"] * np.clip(np.abs(sh), 0, 1) * se / np.maximum(gh, CAL["g_min"])
                    dphi = H * r_ + CAL["mu"] * (phi - st["phi_prev"][a:b])
                st["phi_prev"][a:b] = phi
                st["phi"][a:b] = np.clip(phi + dphi, -np.pi, np.pi)
            elif arm == "broyden":
                if t > 0:
                    dphi = phi - st["phi_p"][a:b]; dp = p - st["p_p"][a:b]
                    m = np.abs(dphi) > 1e-6
                    sec = np.where(m, dp / np.where(m, dphi, 1), 0).astype(np.float32)
                    upd = np.abs(sec) > 0.02
                    bg = st["b_g"][a:b].astype(np.float32); bs = st["b_s"][a:b].astype(np.float32)
                    bg[upd] = 0.5 * bg[upd] + 0.5 * np.abs(sec[upd]); bs[upd] = np.sign(sec[upd])
                    st["b_g"][a:b] = bg.astype(np.float16); st["b_s"][a:b] = bs.astype(np.float16)
                st["phi_p"][a:b] = phi; st["p_p"][a:b] = p
                if t < 2:
                    newphi = phi + 0.15 * rng_for(seed, 9, a, t).choice(np.array([-1., 1.], np.float32), b - a)
                else:
                    step = 0.6 * st["b_s"][a:b].astype(np.float32) * r_ / np.maximum(st["b_g"][a:b].astype(np.float32), 0.15)
                    newphi = phi + np.clip(step, -0.6, 0.6)
                st["phi"][a:b] = np.clip(newphi, -np.pi, np.pi)
            th += rng_for(seed, 6, a, t).normal(0, SEV, b - a).astype(np.float32)
            th -= 0.02 * th
            st["theta"][a:b] = th
        meta["errs"].append(round(float(np.sqrt(sq / cnt)), 4))
        meta["t"] = t + 1
    meta["wall"] = round(meta["wall"] + time.time() - t0, 1)
    for nm, _ in ARRS[arm]:
        np.save(f"{d}/{nm}.npy", st[nm])
    json.dump(meta, open(meta_p, "w"))
    print(json.dumps(dict(arm=arm, t=meta["t"], errs=meta["errs"], wall=meta["wall"])))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
