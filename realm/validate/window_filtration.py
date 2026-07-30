"""Sub-spec II Stage 6 — frequency-window filtration (Axioms 8.1, 4.2).

Score one knob vector against a filtration of W ordinate windows under *shared*
knobs, producing a component vector per window via the independent lock baseline
(Sub-spec I Stage 1).

Stage 6 pass (design):
  constraint_scalars ≥ 5 × n_knobs  (W ≥ 7 at n_sectors=6 → 6W ≥ 42 vs 8 knobs)
  and every window reports a non-degenerate independent-baseline signature
  when policy is independent_baseline (stamp is still recorded either way).

Does **not** touch dual-gate LengthPolicy / projection ranking production numbers.
Ontology: never λ=γ.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from realm.validate.baseline import DEAD_TERMS, G5_KEYS, KNOB_KEYS, score_with_independent_baseline
from realm.validate.zeros import real_zeros

# Live + revived diagnostic terms counted as constraint scalars per window.
# Design §3 uses 6 scalars / window at sectors=6; we count the six component
# fields that form the residual inventory (dead+live).
COMPONENT_SCALAR_KEYS = (
    "stationarity",
    "crit_coverage",
    "pin_align",
    "theta_ladder_l1",
    "corr_penalty",
    "density_return_l1",
)

N_KNOBS = len(KNOB_KEYS)


def contiguous_windows(
    zeros: np.ndarray,
    *,
    n_zeros: int,
    n_windows: int,
    lock_offset: int | None = None,
) -> list[dict[str, Any]]:
    """Build W contiguous key blocks; lock = next block (disjoint) when available.

    ``lock_offset`` defaults to ``n_zeros`` (adjacent block). When the lock block
    would run off the table, wraps to the start (still same length; may not be
    fully disjoint — flagged in the window record).
    """
    g = np.asarray(zeros, dtype=float).ravel()
    k = int(n_zeros)
    W = int(n_windows)
    if k < 2:
        raise ValueError("n_zeros must be ≥ 2")
    if W < 1:
        raise ValueError("n_windows must be ≥ 1")
    need = k * W + (lock_offset if lock_offset is not None else k)
    if g.size < k * 2:
        raise ValueError(f"need at least {2 * k} zeros for independent baseline, got {g.size}")
    if g.size < k * W:
        raise ValueError(f"need ≥ {k * W} zeros for W={W}, got {g.size}")

    off = int(k if lock_offset is None else lock_offset)
    windows: list[dict[str, Any]] = []
    for i in range(W):
        ks = i * k
        ke = ks + k
        key = g[ks:ke]
        ls = ke if off == k else ks + off
        le = ls + k
        if le <= g.size:
            lock = g[ls:le]
            disjoint = bool(key[-1] < lock[0] or lock[-1] < key[0])
        else:
            # wrap lock from start — may overlap; still equal length
            lock = g[:k]
            disjoint = bool(key[-1] < lock[0] or lock[-1] < key[0])
        windows.append(
            {
                "index": i,
                "key_slice": (ks, ke),
                "lock_slice": (int(ls) if le <= g.size else 0, int(le) if le <= g.size else k),
                "key_gammas": key,
                "lock_gammas": lock,
                "disjoint": disjoint,
            }
        )
    return windows


def anchor_omega_span(zeros: np.ndarray, *, n_zeros: int = 14) -> float:
    """Legacy window-1 frequency ratio g[-1]/g[0] — Stage 2 algebraic anchor.

    Setting ``omega_span`` to this value on *any* window reproduces the published
    window-1 omega shape exactly (see tests/test_omega_span.py).
    """
    g = np.asarray(zeros, dtype=float).ravel()[: int(n_zeros)]
    if g.size < 2:
        raise ValueError("need ≥2 ordinates to anchor omega_span")
    return float(g[-1] / (g[0] + 1e-15))


def _knobs_for_forge(knobs: dict[str, Any]) -> dict[str, float]:
    """Production knobs + optional G5 span for Keymaker.forge."""
    out: dict[str, float] = {}
    for k in KNOB_KEYS:
        if k in knobs and knobs[k] is not None:
            out[k] = float(knobs[k])
    for k in G5_KEYS:
        if k in knobs and knobs[k] is not None:
            out[k] = float(knobs[k])
    return out


def score_window_filtration(
    knobs: dict[str, Any],
    *,
    n_windows: int = 7,
    n_zeros: int = 14,
    N: int = 13,
    n_sectors: int = 6,
    n_zeros_table: int | None = None,
    omega_span: float | None = None,
    use_g5_span: bool = False,
) -> dict[str, Any]:
    """Stage 6: multi-window independent-baseline component vectors.

    Parameters
    ----------
    knobs
        Shared Keymaker knobs (Lambda, omega_scale, …). Optional ``omega_span``
        on the knobs or as an explicit arg enables G5 span parameterization.
    n_windows
        W — number of key windows in the filtration (design: ≥7 for 5× DOF).
    n_zeros
        Ordinates per window (k).
    n_zeros_table
        Total ζ ordinates to load (default: enough for W key blocks + one lock).
    use_g5_span
        If True and ``omega_span`` is None, set span to the Stage 2 anchor
        ``g[-1]/g[0]`` of window 1 (legacy-reproducing, window-invariant ratio).
    """
    kn = dict(knobs)
    W = int(n_windows)
    k = int(n_zeros)
    table_n = int(n_zeros_table) if n_zeros_table is not None else max(k * (W + 1), k * 2)
    zeros = real_zeros(table_n)

    span_used: float | None
    if omega_span is not None:
        span_used = float(omega_span)
        kn = {**kn, "omega_span": span_used}
    elif use_g5_span or kn.get("omega_span") is not None:
        if kn.get("omega_span") is not None:
            span_used = float(kn["omega_span"])
        else:
            span_used = anchor_omega_span(zeros, n_zeros=k)
            kn = {**kn, "omega_span": span_used}
    else:
        span_used = None

    blocks = contiguous_windows(zeros, n_zeros=k, n_windows=W)

    # G5 diagnostic: frequency ratio of derived omega under shared knobs
    omega_ratios: list[float] = []
    window_rows: list[dict[str, Any]] = []
    for b in blocks:
        kn_forge = _knobs_for_forge(kn)
        row = score_with_independent_baseline(
            knobs=kn_forge,
            key_gammas=b["key_gammas"],
            lock_gammas=b["lock_gammas"],
            N=int(N),
            n_sectors=int(n_sectors),
        )
        # measure omega ratio on the key block under the same knobs
        from realm.derive import SpectralAction
        from realm.zeta_field import ZetaField

        sa = SpectralAction.from_field(
            ZetaField.from_gammas(b["key_gammas"]),
            omega_scale=float(kn_forge.get("omega_scale", 1.0)),
            omega_span=span_used,
        )
        om = np.asarray(sa.omega, dtype=float).ravel()
        ratio = float(om[-1] / (om[0] + 1e-15)) if om.size >= 2 else float("nan")
        omega_ratios.append(ratio)

        deg = row.get("degeneracy") or {}
        comps = row.get("components") or {}
        window_rows.append(
            {
                "index": b["index"],
                "key_slice": b["key_slice"],
                "lock_slice": b["lock_slice"],
                "disjoint": bool(b["disjoint"] and row.get("baseline", {}).get("disjoint", False)),
                "components": comps,
                "degeneracy": deg,
                "is_degenerate": bool(deg.get("is_degenerate", True)),
                "omega_ratio": ratio,
                "ontology": row.get("ontology"),
            }
        )

    n_comp = len(COMPONENT_SCALAR_KEYS)
    constraint_scalars = n_comp * W
    dof_ratio = float(constraint_scalars) / float(N_KNOBS)
    n_clear = sum(1 for r in window_rows if not r["is_degenerate"])
    n_disjoint = sum(1 for r in window_rows if r["disjoint"])

    # Stage 6 design criterion
    pass_dof = constraint_scalars >= 5 * N_KNOBS
    # Guard: independent baseline can still fire (e.g. occupancy); report honesty
    pass_guard_all = n_clear == W
    stage6_pass = bool(pass_dof and pass_guard_all)

    # Component matrix for Stage 7+ (W × n_comp)
    mat = np.full((W, n_comp), np.nan, dtype=float)
    for i, r in enumerate(window_rows):
        c = r["components"]
        for j, key in enumerate(COMPONENT_SCALAR_KEYS):
            v = c.get(key, np.nan)
            try:
                mat[i, j] = float(v)
            except (TypeError, ValueError):
                mat[i, j] = np.nan

    # Cross-window dispersion of live terms (diagnostic for Stage 7 prep)
    live_keys = ("corr_penalty", "density_return_l1")
    cross: dict[str, Any] = {}
    for key in live_keys:
        j = COMPONENT_SCALAR_KEYS.index(key)
        col = mat[:, j]
        col = col[np.isfinite(col)]
        if col.size:
            cross[key] = {
                "mean": float(np.mean(col)),
                "std": float(np.std(col)),
                "min": float(np.min(col)),
                "max": float(np.max(col)),
                "spread_ratio": float(np.max(col) / (np.min(col) + 1e-15)) if col.size else None,
            }

    # G5 pass: omega ratios agree across windows within 5% (design Stage 2)
    ratios = np.asarray(omega_ratios, dtype=float)
    ratios = ratios[np.isfinite(ratios)]
    if ratios.size >= 2:
        rmin, rmax = float(np.min(ratios)), float(np.max(ratios))
        # relative spread of (min,max) about mid
        mid = 0.5 * (rmin + rmax)
        rel_spread = float((rmax - rmin) / (mid + 1e-15))
        g5_pass = bool(rel_spread <= 0.05)
    else:
        rmin = rmax = rel_spread = float("nan")
        g5_pass = False

    return {
        "stage": 6,
        "stage_name": "frequency_window_filtration",
        "W": W,
        "n_zeros": k,
        "N": int(N),
        "n_sectors": int(n_sectors),
        "n_knobs": N_KNOBS,
        "component_keys": list(COMPONENT_SCALAR_KEYS),
        "dead_terms": list(DEAD_TERMS),
        "constraint_scalars": int(constraint_scalars),
        "dof_ratio": dof_ratio,
        "pass_dof": pass_dof,
        "n_windows_guard_clear": int(n_clear),
        "n_windows_disjoint": int(n_disjoint),
        "pass_guard_all": pass_guard_all,
        "stage6_pass": stage6_pass,
        "omega_span": span_used,
        "use_g5_span": bool(span_used is not None),
        "g5": {
            "omega_ratio_min": rmin,
            "omega_ratio_max": rmax,
            "rel_spread": rel_spread,
            "pass_within_5pct": g5_pass,
            "axiom": "G5 scale_free_structure",
        },
        "windows": window_rows,
        "component_matrix": mat.tolist(),
        "cross_window_live": cross,
        "zeros_table_n": int(zeros.size),
        "ontology": "window_filtration_independent_baseline_not_lambda_eq_gamma",
        "note": (
            "Sub-spec II Stage 6. Shared knobs across W windows; "
            "independent lock baseline per window. Optional G5 omega_span. "
            "Does not modify dual-gate LengthPolicy. Never λ=γ."
        ),
    }


def load_champion_knobs(path: Path | str = "evolve_result.json") -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return dict(data["best_knobs"])
