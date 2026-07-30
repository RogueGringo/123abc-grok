"""Sub-spec II Stages 7–8 — cross-window rigidity + persistence (Axioms 8.2, 4.3).

Stage 7: long-range statistics on each window's ordinate block (and on the
component matrix across the filtration). Candidates for the fitness carrier:
number variance Σ²(L), spectral rigidity Δ₃(L), pair correlation at L>1.

Stage 8: persistence of an arm's *advantage* across window index — birth/death
barcode; pass if max consecutive lifespan ≥ ceil(W/2).

Does not modify dual-gate LengthPolicy. Never λ=γ.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.validate.seeds import make_seed, sample_gue_spacings
from realm.validate.window_filtration import (
    COMPONENT_SCALAR_KEYS,
    load_champion_knobs,
    score_window_filtration,
)
from realm.validate.zeros import real_zeros


# ---------------------------------------------------------------------------
# Unfolding + spectral statistics (Stage 7)
# ---------------------------------------------------------------------------


def unfold_ordinates(g: np.ndarray) -> np.ndarray:
    """Map ordinates to unit-mean nearest-neighbour spacings (local mean gap)."""
    g = np.asarray(g, dtype=float).ravel()
    if g.size < 3:
        return np.zeros(0, dtype=float)
    d = np.diff(g)
    # local mean via 3-point smooth of gaps; fallback global mean
    if d.size >= 3:
        ker = np.array([1.0, 2.0, 1.0]) / 4.0
        pad = np.pad(d, (1, 1), mode="edge")
        local = np.convolve(pad, ker, mode="valid")
        s = d / (local + 1e-15)
    else:
        s = d / (float(np.mean(d)) + 1e-15)
    return s


def number_variance(spacings: np.ndarray, L: float) -> float:
    """Number variance Σ²(L) from unit-mean spacings (interval length L in mean units).

    Monte-Carlo style: tile a long unfolded staircase from spacings and measure
    variance of count in windows of length L.
    """
    s = np.asarray(spacings, dtype=float).ravel()
    s = s[np.isfinite(s) & (s > 0)]
    if s.size < 4 or L <= 0:
        return float("nan")
    # unfolded positions
    x = np.concatenate([[0.0], np.cumsum(s)])
    total = float(x[-1])
    if total < 2 * L:
        return float("nan")
    # sample many intervals
    n_samp = min(200, max(20, int(total / L) - 1))
    rng = np.random.default_rng(0)
    starts = rng.uniform(0.0, total - L, size=n_samp)
    counts = np.searchsorted(x, starts + L) - np.searchsorted(x, starts)
    return float(np.var(counts.astype(float)))


def spectral_rigidity_delta3(spacings: np.ndarray, L: float) -> float:
    """Spectral rigidity Δ₃(L) via least-squares fit of staircase on [a, a+L].

    Dyson–Mehta: min over A,B of (1/L) ∫_a^{a+L} (N(x) − A − Bx)² dx.
    Approximated by discrete LS on unfolded positions.
    """
    s = np.asarray(spacings, dtype=float).ravel()
    s = s[np.isfinite(s) & (s > 0)]
    if s.size < 6 or L <= 0:
        return float("nan")
    x = np.concatenate([[0.0], np.cumsum(s)])
    n_count = np.arange(x.size, dtype=float)
    total = float(x[-1])
    if total < L + 1e-9:
        return float("nan")
    # one central interval for stability
    a = max(0.0, 0.5 * (total - L))
    b = a + L
    mask = (x >= a) & (x <= b)
    if int(np.sum(mask)) < 4:
        return float("nan")
    xx = x[mask] - a
    nn = n_count[mask]
    # fit nn ≈ A + B xx
    A = np.column_stack([np.ones_like(xx), xx])
    coef, _, _, _ = np.linalg.lstsq(A, nn, rcond=None)
    resid = nn - (coef[0] + coef[1] * xx)
    return float(np.mean(resid**2))


def pair_correlation(spacings: np.ndarray, L: float, *, n_bins: int = 20) -> float:
    """Integrated pair correlation excess at separation ~L (L>1 mean spacings).

    Returns mean of g2(r) − 1 over r ∈ [L, L+0.5] estimated from all pairs of
    unfolded positions (cheap O(n²) on window size k~14).
    """
    s = np.asarray(spacings, dtype=float).ravel()
    s = s[np.isfinite(s) & (s > 0)]
    if s.size < 4 or L <= 1.0:
        return float("nan")
    x = np.concatenate([[0.0], np.cumsum(s)])
    diffs = []
    for i in range(x.size):
        for j in range(i + 1, x.size):
            diffs.append(float(x[j] - x[i]))
    d = np.asarray(diffs, dtype=float)
    lo, hi = float(L), float(L) + 0.5
    in_bin = d[(d >= lo) & (d < hi)]
    # expected density of pairs in [lo,hi] for Poisson: ~ length * density
    # normalize by total pairs / mean range
    if d.size == 0:
        return float("nan")
    dens = float(in_bin.size) / (0.5 * max(d.size, 1))
    # crude Poisson baseline ~ 1 for unit density pair measure; return dens-1
    return float(dens - 1.0)


def rigidity_report_for_block(gammas: np.ndarray, *, L_values: tuple[float, ...] = (2.0, 5.0, 10.0)) -> dict[str, Any]:
    """Stage 7 statistics for one ordinate block."""
    g = np.asarray(gammas, dtype=float).ravel()
    s = unfold_ordinates(g)
    out: dict[str, Any] = {
        "n_ordinates": int(g.size),
        "n_spacings": int(s.size),
        "mean_spacing_raw": float(np.mean(np.diff(g))) if g.size > 1 else float("nan"),
        "unfolded_mean": float(np.mean(s)) if s.size else float("nan"),
        "number_variance": {},
        "delta3": {},
        "pair_corr_excess": {},
    }
    for L in L_values:
        out["number_variance"][str(L)] = number_variance(s, L)
        out["delta3"][str(L)] = spectral_rigidity_delta3(s, L)
        if L > 1.0:
            out["pair_corr_excess"][str(L)] = pair_correlation(s, L)
    # scalar carrier: mean Δ₃ at L=5 (long-range; GUE expects ~log L / π²)
    d5 = out["delta3"].get("5.0", float("nan"))
    nv5 = out["number_variance"].get("5.0", float("nan"))
    out["carrier"] = {
        "delta3_L5": d5,
        "number_variance_L5": nv5,
        # lower Δ₃ relative to Poisson (~L/15) is "more rigid"
        "rigidity_score": float(d5) if np.isfinite(d5) else float("nan"),
    }
    return out


def score_rigidity_filtration(
    *,
    n_windows: int = 7,
    n_zeros: int = 14,
    n_zeros_table: int | None = None,
    arm: str = "zeta",
    rng_seed: int = 0,
) -> dict[str, Any]:
    """Stage 7: rigidity stats on each window of an arm's spectrum (shared block layout).

    For ``arm='zeta'`` uses verified real zeros. For ``gue`` / other seeds, draws
    one spectrum via ``make_seed`` (or GUE spacings → cumulative) and windows it.
    """
    W = int(n_windows)
    k = int(n_zeros)
    table_n = int(n_zeros_table) if n_zeros_table is not None else max(k * (W + 1), 2 * k)
    rng = np.random.default_rng(int(rng_seed))

    if arm == "zeta":
        g = real_zeros(table_n)
        source = "real_zeros_verified"
    elif arm in ("gue", "goe", "goe_true", "poisson", "scramble", "arith"):
        try:
            g = make_seed(arm if arm != "gue" else "gue", table_n, rng)
            source = f"make_seed:{arm}"
        except Exception:
            # build from GUE spacings if kind name differs
            sp = sample_gue_spacings(table_n - 1, rng)
            g = np.concatenate([[14.1347], 14.1347 + np.cumsum(sp * 1.0)])
            source = "sample_gue_spacings_fallback"
    else:
        raise ValueError(f"unknown arm {arm!r}")

    rows = []
    carriers = []
    for i in range(W):
        block = g[i * k : (i + 1) * k]
        if block.size < k:
            break
        rep = rigidity_report_for_block(block)
        rows.append({"index": i, "rigidity": rep})
        carriers.append(rep["carrier"]["rigidity_score"])

    carr = np.asarray(carriers, dtype=float)
    finite = carr[np.isfinite(carr)]
    return {
        "stage": 7,
        "stage_name": "cross_window_rigidity",
        "arm": arm,
        "source": source,
        "W": len(rows),
        "n_zeros": k,
        "windows": rows,
        "carrier_series": carriers,
        "carrier_mean": float(np.mean(finite)) if finite.size else float("nan"),
        "carrier_std": float(np.std(finite)) if finite.size else float("nan"),
        "ontology": "spectral_rigidity_not_lambda_eq_gamma",
        "note": (
            "Sub-spec II Stage 7. Long-range stats on ordinate windows only — "
            "no dual-gate LengthPolicy change. Never λ=γ."
        ),
    }


# ---------------------------------------------------------------------------
# Stage 8 — persistence of advantage
# ---------------------------------------------------------------------------


def advantage_series(
    series_a: np.ndarray | list[float],
    series_b: np.ndarray | list[float],
    *,
    lower_is_better: bool = True,
) -> np.ndarray:
    """Boolean mask: True where arm A beats arm B at that window."""
    a = np.asarray(series_a, dtype=float).ravel()
    b = np.asarray(series_b, dtype=float).ravel()
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]
    if lower_is_better:
        return np.isfinite(a) & np.isfinite(b) & (a < b)
    return np.isfinite(a) & np.isfinite(b) & (a > b)


def persistence_barcode(wins: np.ndarray | list[bool]) -> dict[str, Any]:
    """Birth/death intervals of consecutive True runs; max lifespan.

    Stage 8 pass: max_lifespan ≥ ceil(W/2).
    """
    w = np.asarray(wins, dtype=bool).ravel()
    W = int(w.size)
    intervals: list[dict[str, int]] = []
    i = 0
    while i < W:
        if not w[i]:
            i += 1
            continue
        birth = i
        while i < W and w[i]:
            i += 1
        death = i  # exclusive
        intervals.append({"birth": birth, "death": death, "lifespan": death - birth})
    max_life = max((iv["lifespan"] for iv in intervals), default=0)
    threshold = int(np.ceil(W / 2.0)) if W else 0
    return {
        "W": W,
        "intervals": intervals,
        "max_lifespan": int(max_life),
        "threshold_ceil_W_over_2": threshold,
        "stage8_pass": bool(max_life >= threshold and W > 0),
        "n_true": int(np.sum(w)),
        "wins": w.astype(bool).tolist(),
    }


def compare_arms_filtration(
    knobs: dict[str, Any],
    *,
    arm_a: str = "zeta",
    arm_b: str = "gue",
    n_windows: int = 7,
    n_zeros: int = 14,
    N: int = 13,
    n_sectors: int = 6,
    component_key: str = "density_return_l1",
    lower_is_better: bool = True,
    rng_seed: int = 0,
    use_g5_span: bool = True,
    omega_span: float | None = None,
) -> dict[str, Any]:
    """Stage 7+8 joint: residual components per window for two arms + persistence.

    Arm ``zeta`` uses real zeros windows (via score_window_filtration on champion
    knobs — the spectrum is ζ). Arm ``gue`` re-scores the *same knobs* on GUE
    ordinate windows (span-matched length via make_seed per window pair).

    Default ``use_g5_span=True`` anchors omega_span to window-1 ζ ratio so both
    arms share a window-invariant frequency ratio (Axiom G5).

    For a fair Stage 7 spectrum-rigidity comparison, also emits rigidity
    filtrations for both arms.
    """
    from realm.validate.baseline import score_with_independent_baseline
    from realm.validate.window_filtration import (
        _knobs_for_forge,
        anchor_omega_span,
        contiguous_windows,
    )
    from realm.validate.zeros import real_zeros as _rz

    W = int(n_windows)
    k = int(n_zeros)
    table_n = max(k * (W + 1), 2 * k)
    rng = np.random.default_rng(int(rng_seed))

    kn = dict(knobs)
    if omega_span is not None:
        kn["omega_span"] = float(omega_span)
    elif use_g5_span and kn.get("omega_span") is None:
        kn["omega_span"] = anchor_omega_span(_rz(k), n_zeros=k)

    # Arm A (ζ): full Stage 6 path under G5 span when requested
    if arm_a != "zeta":
        raise ValueError("compare_arms_filtration currently requires arm_a='zeta'")
    filt_a = score_window_filtration(
        kn,
        n_windows=W,
        n_zeros=k,
        N=N,
        n_sectors=n_sectors,
        use_g5_span=use_g5_span,
        omega_span=kn.get("omega_span"),
    )
    series_a = []
    for w in filt_a["windows"]:
        series_a.append(float(w["components"].get(component_key, np.nan)))

    # Arm B: GUE (or other) windows with independent baseline, same knobs
    g_b = make_seed("gue" if arm_b == "gue" else arm_b, table_n, rng)
    blocks_b = contiguous_windows(g_b, n_zeros=k, n_windows=W)
    kn_forge = _knobs_for_forge(kn)
    series_b = []
    windows_b = []
    for b in blocks_b:
        row = score_with_independent_baseline(
            knobs=kn_forge,
            key_gammas=b["key_gammas"],
            lock_gammas=b["lock_gammas"],
            N=int(N),
            n_sectors=int(n_sectors),
        )
        c = row["components"]
        series_b.append(float(c.get(component_key, np.nan)))
        windows_b.append(
            {
                "index": b["index"],
                "components": c,
                "degeneracy": row.get("degeneracy"),
                "is_degenerate": bool((row.get("degeneracy") or {}).get("is_degenerate", True)),
            }
        )

    wins = advantage_series(series_a, series_b, lower_is_better=lower_is_better)
    barcode = persistence_barcode(wins)

    # Stage 7 rigidity on raw spectra (windowed)
    rig_a = score_rigidity_filtration(
        n_windows=W, n_zeros=k, n_zeros_table=table_n, arm="zeta", rng_seed=rng_seed
    )
    rig_b = score_rigidity_filtration(
        n_windows=W, n_zeros=k, n_zeros_table=table_n, arm=arm_b, rng_seed=rng_seed + 1
    )
    # advantage on rigidity (lower Δ₃ often more rigid — treat lower as better)
    rig_wins = advantage_series(
        rig_a["carrier_series"], rig_b["carrier_series"], lower_is_better=True
    )
    rig_barcode = persistence_barcode(rig_wins)

    return {
        "stage": "7+8",
        "stage_name": "rigidity_and_persistence",
        "arm_a": arm_a,
        "arm_b": arm_b,
        "component_key": component_key,
        "lower_is_better": lower_is_better,
        "W": W,
        "series_a": series_a,
        "series_b": series_b,
        "component_persistence": barcode,
        "rigidity_a": {
            "carrier_mean": rig_a["carrier_mean"],
            "carrier_series": rig_a["carrier_series"],
        },
        "rigidity_b": {
            "carrier_mean": rig_b["carrier_mean"],
            "carrier_series": rig_b["carrier_series"],
        },
        "rigidity_persistence": rig_barcode,
        "stage6_a": {
            "stage6_pass": filt_a["stage6_pass"],
            "dof_ratio": filt_a["dof_ratio"],
            "n_windows_guard_clear": filt_a["n_windows_guard_clear"],
            "g5": filt_a.get("g5"),
            "omega_span": filt_a.get("omega_span"),
        },
        "windows_b_guard_clear": sum(1 for w in windows_b if not w["is_degenerate"]),
        "use_g5_span": bool(use_g5_span or kn.get("omega_span") is not None),
        "omega_span": kn.get("omega_span"),
        "ontology": "cross_window_persistence_not_lambda_eq_gamma",
        "note": (
            "Sub-spec II Stages 7–8. Component advantage + spectral rigidity "
            "persistence across windows under optional G5 omega_span. "
            "Dual-gate LengthPolicy untouched. Never λ=γ."
        ),
    }


# ---------------------------------------------------------------------------
# Multi-carrier Stage 8 + multi-arm existence scan (Stage 9-lite)
# ---------------------------------------------------------------------------


def multi_carrier_persistence(
    win_masks: dict[str, np.ndarray | list[bool]],
) -> dict[str, Any]:
    """Stage 8 over several carriers: per-carrier barcode + OR / AND fusion.

    OR: advantage if *any* carrier wins at that window (liberal).
    AND: advantage only if *all* carriers win (strict).
    """
    if not win_masks:
        raise ValueError("need at least one carrier mask")
    names = list(win_masks.keys())
    mats = [np.asarray(win_masks[n], dtype=bool).ravel() for n in names]
    W = min(m.size for m in mats)
    mats = [m[:W] for m in mats]
    stacked = np.stack(mats, axis=0)
    or_mask = np.any(stacked, axis=0)
    and_mask = np.all(stacked, axis=0)
    per = {n: persistence_barcode(m) for n, m in zip(names, mats)}
    best_name = max(per.keys(), key=lambda n: per[n]["max_lifespan"])
    return {
        "W": W,
        "carriers": per,
        "or_fusion": persistence_barcode(or_mask),
        "and_fusion": persistence_barcode(and_mask),
        "best_carrier": best_name,
        "best_lifespan": per[best_name]["max_lifespan"],
        "stage8_pass_any": bool(per[best_name]["stage8_pass"]),
        "stage8_pass_or": bool(persistence_barcode(or_mask)["stage8_pass"]),
        "stage8_pass_and": bool(persistence_barcode(and_mask)["stage8_pass"]),
    }


def score_arm_component_series(
    knobs: dict[str, Any],
    arm: str,
    *,
    n_windows: int = 7,
    n_zeros: int = 14,
    N: int = 13,
    n_sectors: int = 6,
    component_keys: tuple[str, ...] = ("density_return_l1", "corr_penalty", "stationarity"),
    use_g5_span: bool = True,
    omega_span: float | None = None,
    rng_seed: int = 0,
    skip_rigidity: bool = False,
) -> dict[str, Any]:
    """Independent-baseline component series for one arm under shared knobs + G5."""
    from realm.validate.baseline import score_with_independent_baseline
    from realm.validate.window_filtration import (
        _knobs_for_forge,
        anchor_omega_span,
        contiguous_windows,
        score_window_filtration,
    )
    from realm.validate.zeros import real_zeros as _rz

    W = int(n_windows)
    k = int(n_zeros)
    table_n = max(k * (W + 1), 2 * k)
    kn = dict(knobs)
    if omega_span is not None:
        kn["omega_span"] = float(omega_span)
    elif use_g5_span and kn.get("omega_span") is None:
        kn["omega_span"] = anchor_omega_span(_rz(k), n_zeros=k)

    series: dict[str, list[float]] = {ck: [] for ck in component_keys}
    guard_clear = 0

    if arm == "zeta":
        filt = score_window_filtration(
            kn,
            n_windows=W,
            n_zeros=k,
            N=N,
            n_sectors=n_sectors,
            use_g5_span=True,
            omega_span=kn.get("omega_span"),
        )
        for w in filt["windows"]:
            c = w["components"]
            for ck in component_keys:
                series[ck].append(float(c.get(ck, np.nan)))
            if not w["is_degenerate"]:
                guard_clear += 1
        g5 = filt.get("g5")
        span = filt.get("omega_span")
    else:
        rng = np.random.default_rng(int(rng_seed))
        kind = "gue" if arm == "gue" else arm
        g = make_seed(kind, table_n, rng)
        blocks = contiguous_windows(g, n_zeros=k, n_windows=W)
        kn_forge = _knobs_for_forge(kn)
        for b in blocks:
            row = score_with_independent_baseline(
                knobs=kn_forge,
                key_gammas=b["key_gammas"],
                lock_gammas=b["lock_gammas"],
                N=int(N),
                n_sectors=int(n_sectors),
            )
            c = row["components"]
            for ck in component_keys:
                series[ck].append(float(c.get(ck, np.nan)))
            if not bool((row.get("degeneracy") or {}).get("is_degenerate", True)):
                guard_clear += 1
        g5 = None
        span = kn.get("omega_span")

    means = {
        ck: float(np.nanmean(np.asarray(series[ck], dtype=float))) for ck in component_keys
    }
    if skip_rigidity:
        rig_mean = float("nan")
        rig_series: list[float] = []
    else:
        rig = score_rigidity_filtration(
            n_windows=W,
            n_zeros=k,
            n_zeros_table=table_n,
            arm=arm if arm != "arith" else "arith",
            rng_seed=int(rng_seed),
        )
        rig_mean = rig["carrier_mean"]
        rig_series = list(rig["carrier_series"])
    return {
        "arm": arm,
        "W": W,
        "series": series,
        "means": means,
        "guard_clear": int(guard_clear),
        "rigidity_carrier_mean": rig_mean,
        "rigidity_series": rig_series,
        "omega_span": span,
        "g5": g5,
    }


def existence_arm_scan(
    knobs: dict[str, Any],
    *,
    arms: tuple[str, ...] = ("zeta", "arith", "gue", "poisson"),
    n_windows: int = 7,
    n_zeros: int = 14,
    N: int = 13,
    n_sectors: int = 6,
    rng_seed: int = 0,
) -> dict[str, Any]:
    """Stage 9-lite: deterministic/stochastic arm means under G5 (no M=59).

    Existence claims (design §7.1): if arith mean dens < ζ mean dens, that is an
    existence falsifier of residual preference under these knobs — no p-value.

    Also multi-carrier Stage 8 of ζ vs each null on dens/corr/rigidity.
    """
    # Ensure arith works in rigidity filtration
    component_keys = ("density_return_l1", "corr_penalty", "stationarity")
    arm_rows: dict[str, Any] = {}
    for i, arm in enumerate(arms):
        # rigidity for arith via special case
        if arm == "arith":
            row = score_arm_component_series(
                knobs,
                "arith",
                n_windows=n_windows,
                n_zeros=n_zeros,
                N=N,
                n_sectors=n_sectors,
                component_keys=component_keys,
                use_g5_span=True,
                rng_seed=rng_seed + i,
            )
            # fix rigidity for arith spectrum
            from realm.validate.window_filtration import contiguous_windows as _cw
            from realm.validate.zeros import real_zeros as _rz

            k = int(n_zeros)
            W = int(n_windows)
            table_n = max(k * (W + 1), 2 * k)
            g = make_seed("arith", table_n, np.random.default_rng(rng_seed + i))
            carriers = []
            for j in range(W):
                block = g[j * k : (j + 1) * k]
                carriers.append(rigidity_report_for_block(block)["carrier"]["rigidity_score"])
            row["rigidity_series"] = carriers
            fin = [c for c in carriers if np.isfinite(c)]
            row["rigidity_carrier_mean"] = float(np.mean(fin)) if fin else float("nan")
            arm_rows[arm] = row
        else:
            arm_rows[arm] = score_arm_component_series(
                knobs,
                arm,
                n_windows=n_windows,
                n_zeros=n_zeros,
                N=N,
                n_sectors=n_sectors,
                component_keys=component_keys,
                use_g5_span=True,
                rng_seed=rng_seed + i,
            )

    # Rank arms by mean density_return (lower better)
    dens_rank = sorted(
        arms, key=lambda a: arm_rows[a]["means"].get("density_return_l1", 1e9)
    )
    zeta_dens = arm_rows["zeta"]["means"]["density_return_l1"]
    arith_beats_zeta = bool(
        "arith" in arm_rows
        and arm_rows["arith"]["means"]["density_return_l1"] < zeta_dens
    )

    # Multi-carrier persistence ζ vs each null
    vs: dict[str, Any] = {}
    if "zeta" in arm_rows:
        z = arm_rows["zeta"]
        for null in arms:
            if null == "zeta":
                continue
            n = arm_rows[null]
            masks = {
                "density_return_l1": advantage_series(
                    z["series"]["density_return_l1"],
                    n["series"]["density_return_l1"],
                    lower_is_better=True,
                ),
                "corr_penalty": advantage_series(
                    z["series"]["corr_penalty"],
                    n["series"]["corr_penalty"],
                    lower_is_better=True,
                ),
                "rigidity_delta3": advantage_series(
                    z["rigidity_series"],
                    n["rigidity_series"],
                    lower_is_better=True,
                ),
            }
            # stationarity: higher may be worse under residual — lower is better in residual terms
            if "stationarity" in z["series"]:
                masks["stationarity"] = advantage_series(
                    z["series"]["stationarity"],
                    n["series"]["stationarity"],
                    lower_is_better=True,
                )
            vs[null] = multi_carrier_persistence(masks)

    return {
        "stage": "9-lite",
        "stage_name": "existence_arm_scan_g5",
        "arms": list(arms),
        "arm_rows": {
            a: {
                "means": arm_rows[a]["means"],
                "guard_clear": arm_rows[a]["guard_clear"],
                "rigidity_carrier_mean": arm_rows[a]["rigidity_carrier_mean"],
                "omega_span": arm_rows[a].get("omega_span"),
            }
            for a in arms
        },
        "density_return_rank_lower_better": list(dens_rank),
        "arith_beats_zeta_existence": arith_beats_zeta,
        "multi_carrier_vs_zeta": vs,
        "any_stage8_pass": any(
            v.get("stage8_pass_or") or v.get("stage8_pass_any") for v in vs.values()
        ),
        "ontology": "existence_scan_g5_not_lambda_eq_gamma",
        "note": (
            "Stage 9-lite under G5. Deterministic arith is an existence result "
            "(§7.1), not a sampling p-value. Dual-gate LengthPolicy untouched. Never λ=γ."
        ),
    }
