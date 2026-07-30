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

from realm.validate.baseline import DEAD_TERMS, KNOB_KEYS, score_with_independent_baseline
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


def score_window_filtration(
    knobs: dict[str, Any],
    *,
    n_windows: int = 7,
    n_zeros: int = 14,
    N: int = 13,
    n_sectors: int = 6,
    n_zeros_table: int | None = None,
    omega_span: float | None = None,
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
    """
    kn = dict(knobs)
    if omega_span is not None:
        kn = {**kn, "omega_span": float(omega_span)}
    # Keymaker.forge may accept omega_span via knobs if derive supports it —
    # baseline._forge passes **knobs,gammas= so only KNOB_KEYS are cleaned.
    # omega_span is applied only if present in knobs and Keymaker accepts it.
    W = int(n_windows)
    k = int(n_zeros)
    table_n = int(n_zeros_table) if n_zeros_table is not None else max(k * (W + 1), k * 2)
    zeros = real_zeros(table_n)
    blocks = contiguous_windows(zeros, n_zeros=k, n_windows=W)

    window_rows: list[dict[str, Any]] = []
    for b in blocks:
        kn_forge = {kk: kn[kk] for kk in KNOB_KEYS if kk in kn}
        # optional span: pass only if Keymaker supports via forge kwargs
        if "omega_span" in kn and kn["omega_span"] is not None:
            kn_forge = {**kn_forge, "omega_span": float(kn["omega_span"])}
        try:
            row = score_with_independent_baseline(
                knobs=kn_forge,
                key_gammas=b["key_gammas"],
                lock_gammas=b["lock_gammas"],
                N=int(N),
                n_sectors=int(n_sectors),
            )
        except TypeError:
            # Keymaker without omega_span kw
            kn_forge.pop("omega_span", None)
            row = score_with_independent_baseline(
                knobs=kn_forge,
                key_gammas=b["key_gammas"],
                lock_gammas=b["lock_gammas"],
                N=int(N),
                n_sectors=int(n_sectors),
            )
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
        "windows": window_rows,
        "component_matrix": mat.tolist(),
        "cross_window_live": cross,
        "zeros_table_n": int(zeros.size),
        "ontology": "window_filtration_independent_baseline_not_lambda_eq_gamma",
        "note": (
            "Sub-spec II Stage 6. Shared knobs across W windows; "
            "independent lock baseline per window. Does not modify dual-gate "
            "LengthPolicy. Never λ=γ."
        ),
    }


def load_champion_knobs(path: Path | str = "evolve_result.json") -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return dict(data["best_knobs"])
