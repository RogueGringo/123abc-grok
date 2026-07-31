"""AXiomZ activation bridge — Configurational Term Series on the dual path.

Binds Jones axioms (01-DEVELOPMENT-AXiomZ) to executable stages:

  Substrate (1.1/G1) → Dynamics (G2/G3) → Geometry (2.4) → Topology (4.x) → Quale (5.3)

Does not restore retracted ζ-preference claims. Ontology: never λ=γ.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from realm.lock_key import Keymaker, build_key, build_lock, residual
from realm.validate.dual import forge_crit_geometry, operator_fingerprint
from realm.validate.report import load_knobs

ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = ROOT / "01-DEVELOPMENT-AXiomZ" / "ACTIVE_MAPPING.json"


def load_mapping(path: Path | str = MAPPING_PATH) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"activations": [], "note": "mapping missing"}
    return json.loads(p.read_text(encoding="utf-8"))


def activation_signature(
    function_id: str,
    axiom_ids: list[str],
    **extra: Any,
) -> dict[str, Any]:
    """Axiom 18.2 — annotate a call with axioms invoked."""
    mapping = load_mapping()
    known = {a["axiom_id"]: a for a in mapping.get("activations", [])}
    return {
        "function_id": function_id,
        "axioms_invoked": list(axiom_ids),
        "axiom_roles": {
            aid: known[aid].get("role") for aid in axiom_ids if aid in known
        },
        "ontology": "not_lambda_eq_gamma",
        **extra,
    }


def crit_action_filtration(
    action,
    n_grid: int = 2000,
    n_levels: int = 24,
    *,
    with_zigzag: bool = False,
    zigzag_windows: int = 4,
) -> dict[str, Any]:
    """Axioms 4.2–4.3: sublevel filtration of S on S¹ (circular 0-homology).

    Add grid points in order of increasing S; union with active neighbors.
    Younger component dies on merge (standard elder rule). Bars that survive
    to the global max are essential Crit-basin structure.

    Optional ``with_zigzag``: multi-window barcode summary (KB geometry stalk A;
    informational only — never pin retune / never ACCEPTANCE).
    """
    del n_levels  # full vertex filtration; kept for API stability
    grid = np.linspace(0.0, 2 * np.pi, n_grid, endpoint=False)
    Sv = np.asarray(action.S(grid), dtype=float)
    s_min, s_max = float(Sv.min()), float(Sv.max())
    span = s_max - s_min
    if span < 1e-15:
        return {
            "n_levels": 0,
            "diagram_H0": [],
            "n_persistent": 0,
            "note": "flat action",
        }

    parent = np.arange(n_grid)
    rank = np.zeros(n_grid, dtype=int)
    birth_of_root: dict[int, float] = {}
    active = np.zeros(n_grid, dtype=bool)
    deaths: list[tuple[float, float]] = []

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int, t: float) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        ba, bb = birth_of_root[ra], birth_of_root[rb]
        # elder rule: older root survives; younger dies at t
        if ba < bb or (ba == bb and ra < rb):
            parent[rb] = ra
            deaths.append((bb, t))
            if rank[ra] == rank[rb]:
                rank[ra] += 1
        else:
            parent[ra] = rb
            deaths.append((ba, t))
            if rank[rb] == rank[ra]:
                rank[rb] += 1

    order = np.argsort(Sv, kind="mergesort")
    for i in order:
        t = float(Sv[i])
        active[i] = True
        birth_of_root[i] = t
        parent[i] = i
        for j in ((i - 1) % n_grid, (i + 1) % n_grid):
            if active[j]:
                union(i, j, t)

    # essential classes: remaining roots (die at +∞ → s_max + span)
    roots = {find(i) for i in range(n_grid) if active[i]}
    infinite = [(birth_of_root[r], s_max + span) for r in roots]
    diagram = deaths + infinite
    persistences = [d - b for b, d in diagram]
    thr = 0.10 * span
    n_persistent = sum(1 for p in persistences if p > thr)

    out: dict[str, Any] = {
        "n_levels": n_grid,
        "s_min": s_min,
        "s_max": s_max,
        "threshold_persistence": thr,
        "diagram_H0": [
            {"birth": b, "death": d, "persistence": d - b} for b, d in diagram
        ],
        "n_features": len(diagram),
        "n_persistent": n_persistent,
        "max_persistence": float(max(persistences)) if persistences else 0.0,
        "n_essential": len(infinite),
        "axioms": ["4.2", "4.3"],
    }
    if with_zigzag:
        try:
            from realm.kb_geometry.zigzag_windows import zigzag_from_crit_filtration

            out["zigzag_windows"] = zigzag_from_crit_filtration(
                out, n_windows=int(zigzag_windows)
            )
            out["zigzag_note"] = (
                "Multi-window H0 summary (info only); not ACCEPTANCE; not pin."
            )
        except Exception as exc:  # noqa: BLE001
            out["zigzag_windows"] = {"error": str(exc), "not_acceptance": True}
    return out


def basin_persistence_weights(
    action,
    thetas: np.ndarray | list[float],
    *,
    n_grid: int = 2000,
    floor: float = 0.35,
) -> np.ndarray:
    """Per-Crit-θ basin depth weights from sublevel structure of S on S¹.

    For each holonomy θ*, estimate 0-homology basin persistence as the
    height of the lower saddle barrier in a local window of S_Λ, then
    normalize so mean weight = 1 with a floor so weak basins still vote.

    Used to reweight Kabsch softmin toward persistent Crit valleys (CTS
    topology → projection ranking). Never λ=γ.
    """
    th = np.asarray(thetas, dtype=float).ravel()
    if th.size == 0:
        return np.zeros(0, dtype=float)
    grid = np.linspace(0.0, 2.0 * np.pi, int(n_grid), endpoint=False)
    Sv = np.asarray(action.S(grid), dtype=float)
    half = max(int(n_grid) // 4, 8)
    depths = np.zeros(th.size, dtype=float)
    for k, t in enumerate(th):
        # nearest grid on circle
        dcirc = np.abs(((grid - float(t) + np.pi) % (2.0 * np.pi)) - np.pi)
        i = int(np.argmin(dcirc))
        s0 = float(Sv[i])
        left = Sv[np.array([(i - j) % n_grid for j in range(1, half)], dtype=int)]
        right = Sv[np.array([(i + j) % n_grid for j in range(1, half)], dtype=int)]
        barrier = float(min(np.max(left), np.max(right)))
        depths[k] = max(barrier - s0, 0.0)
    mean_d = float(np.mean(depths)) + 1e-15
    fl = float(np.clip(floor, 0.0, 0.95))
    w = fl + (1.0 - fl) * (depths / mean_d)
    # renorm mean to 1
    w = w / (float(np.mean(w)) + 1e-15)
    return w.astype(float)


def run_term_series(
    knobs: dict[str, Any] | None = None,
    *,
    N: int = 13,
    n_zeros: int = 14,
    n_sectors: int = 6,
    gammas: np.ndarray | None = None,
    prefer_maxop: bool = True,
) -> dict[str, Any]:
    """Axiom 5.2 Configurational Term Series on one forge.

    Stages:
      1 substrate  — seed ordinates
      2 dynamics   — SpectralAction + Crit
      3 geometry   — Crit multimode templates
      4 topology   — sheaf L fingerprint + Crit filtration
      5 quale      — informative residual dens-return + mold occupancy proxy
    """
    if knobs is None:
        knobs = load_knobs(ROOT / "evolve_result.json")

    kn = dict(knobs)
    if gammas is not None:
        kn["gammas"] = np.asarray(gammas, float).ravel()

    # --- 1 Substrate ---
    der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(**kn)
    field = der.field
    substrate = {
        "stage": "substrate",
        "symbol": "X",
        "n_zeros": int(field.gammas.size),
        "gamma_range": [float(field.gammas[0]), float(field.gammas[-1])],
        "mean_gap": float(np.mean(field.gaps)) if field.gaps.size else 0.0,
        "axioms": ["G1", "1.1"],
    }

    # --- 2 Dynamics ---
    crit = der.critical
    n_min = sum(1 for c in crit if c.get("kind") == "minimum")
    dynamics = {
        "stage": "dynamics",
        "symbol": "f / S_Λ",
        "n_critical": len(crit),
        "n_minima": n_min,
        "Lambda": float(der.action.cutoff_Lambda),
        "axioms": ["G2", "G3", "2.2"],
    }

    # --- 3 Geometry ---
    pack = forge_crit_geometry(
        knobs,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        gammas=kn.get("gammas"),
        prefer_maxop=prefer_maxop,
    )
    geometry = {
        "stage": "geometry",
        "symbol": "M_v",
        "n_templates": pack["n_sectors"],
        "thetas": pack["thetas"].tolist(),
        "axioms": ["2.1", "2.4"],
    }

    # --- 4 Topology ---
    filt = crit_action_filtration(der.action)
    op = pack["operator"]
    topology = {
        "stage": "topology",
        "symbol": "H_k / L",
        "operator": op.to_dict(),
        "crit_filtration": filt,
        "sheaf_note": "connection Laplacian at Crit θ*; H0 via frustration",
        "axioms": ["4.1", "4.2", "4.3", "9.2"],
    }

    # --- 5 Quale (internal structure signature — not external ranking) ---
    lock = build_lock(der)
    key = build_key(der)
    res_inf = residual(lock, key, action=der.action)
    res_leg = residual(lock, key, action=der.action)
    quale = {
        "stage": "quale",
        "symbol": "Q(Φ)",
        "R_informative": float(res_inf.total),
        "R_legacy_seating": float(res_leg.total),
        "density_return": float((res_inf.diagnostics or {}).get("density_return_l1", 1.0)),
        "degenerate_seating": float(
            (res_inf.diagnostics or {}).get("degenerate_seating", 0.0)
        ),
        "n_persistent_crit_basins": filt["n_persistent"],
        "interpretation": (
            "Internal quale = dual structure signature. "
            "External quale for ranking is enrichment (pdb_batch), not R_legacy."
        ),
        "axioms": ["5.2", "5.3", "6.2"],
    }

    return {
        "cts": [substrate, dynamics, geometry, topology, quale],
        "signature": activation_signature(
            "run_term_series",
            ["G1", "G2", "G3", "1.1", "2.4", "4.1", "4.2", "4.3", "5.2", "5.3", "6.2", "18.2"],
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sectors,
        ),
        "mapping": "01-DEVELOPMENT-AXiomZ/ACTIVE_MAPPING.json",
        "ontology": "cts_dual_path_not_lambda_eq_gamma",
    }
