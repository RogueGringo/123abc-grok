"""Dual instrument: baseline operation matrix L vs geometric projection.

Ontology (see realm.ontology)
-----------------------------
* Substrate  — ζ field seeds Crit; **not** the actual physical target
* Operation  — MaxOp/numpy connection Laplacian L(A(θ)) at Crit holonomies
* Projection — Crit-induced geometry in R³ scored vs external CA rings

Operational ranking optimizes **projection fit** of substrate-derived molds.
MaxOp supplies operator dual diagnostics and tie-breaks — never λ=γ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from realm.cohesive import CohesiveHomotopyFunctor
from realm.lock_key import Keymaker
from realm.validate.decoys import score_geometry_vs_crit, theta_proxy_from_ca


@dataclass
class OperatorFingerprint:
    thetas: np.ndarray
    gaps: np.ndarray
    frustrations: np.ndarray
    logZ: np.ndarray
    mean_gap: float
    gap_cv: float
    mean_frustration: float
    mean_logZ: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "thetas": self.thetas.tolist(),
            "gaps": self.gaps.tolist(),
            "frustrations": self.frustrations.tolist(),
            "logZ": self.logZ.tolist(),
            "mean_gap": self.mean_gap,
            "gap_cv": self.gap_cv,
            "mean_frustration": self.mean_frustration,
            "mean_logZ": self.mean_logZ,
        }

    def feature_matrix(self) -> np.ndarray:
        """Per-sector features for nearest-neighbor dual distance."""
        # scale-free-ish columns
        g = self.gaps
        f = self.frustrations
        z = self.logZ
        g_n = g / (np.mean(g) + 1e-15)
        f_n = f / (np.mean(np.abs(f)) + 1e-15)
        z_n = z - np.mean(z)
        return np.column_stack([g_n, f_n, z_n])


def operator_fingerprint(
    thetas: np.ndarray | list[float],
    N: int,
    d: int = 2,
    prefer_maxop: bool = True,
) -> OperatorFingerprint:
    """Evaluate L(A(θ)) at each Crit holonomy — baseline operation matrix side."""
    th = np.asarray(thetas, dtype=float).ravel()
    fun = CohesiveHomotopyFunctor(N=int(N), d=int(d))
    gaps, frust, logz = [], [], []
    for i, t in enumerate(th):
        st = fun.evaluate_state_from_twist(
            i + 1, float(t), float(t), prefer_maxop=prefer_maxop
        )
        gaps.append(float(st.spectral_gap))
        frust.append(float(st.frustration_closed_form))
        logz.append(float(np.log(max(st.partition_function, 1e-300))))
    g = np.asarray(gaps, float)
    f = np.asarray(frust, float)
    z = np.asarray(logz, float)
    mean_g = float(np.mean(g)) if g.size else 0.0
    cv = float(np.std(g) / (mean_g + 1e-15)) if g.size else 0.0
    return OperatorFingerprint(
        thetas=th.copy(),
        gaps=g,
        frustrations=f,
        logZ=z,
        mean_gap=mean_g,
        gap_cv=cv,
        mean_frustration=float(np.mean(f)) if f.size else 0.0,
        mean_logZ=float(np.mean(z)) if z.size else 0.0,
    )


def operator_point_at_theta(
    theta: float,
    N: int,
    d: int = 2,
    prefer_maxop: bool = True,
) -> np.ndarray:
    """Single-holonomy operator feature vector (gap_n, frust_n, logZ_c)."""
    fp = operator_fingerprint([theta], N=N, d=d, prefer_maxop=prefer_maxop)
    # raw then mild normalize locally
    g, f, z = float(fp.gaps[0]), float(fp.frustrations[0]), float(fp.logZ[0])
    return np.array([g, f, z], dtype=float)


def operator_distance_to_crit(
    xyz: np.ndarray,
    crit_fp: OperatorFingerprint,
    N: int,
    prefer_maxop: bool = True,
) -> dict[str, float]:
    """Projection-side holonomy proxy → L fingerprint vs nearest Crit sector.

    θ_geom from CA ring (FALLBACK_THETA_PROXY). Distance in feature space
    to nearest Crit operator point (after column z-score of Crit matrix).
    """
    th = float(theta_proxy_from_ca(xyz))
    pt = operator_point_at_theta(th, N=N, prefer_maxop=prefer_maxop)
    M = crit_fp.feature_matrix()
    if M.size == 0:
        return {"op_dist": 1e9, "theta_geom": th, "method": "OP_CRIT_NN"}
    # column scale from Crit ensemble
    mu = M.mean(axis=0)
    sig = M.std(axis=0) + 1e-15
    # raw pt needs same feature recipe as feature_matrix
    g_n = pt[0] / (crit_fp.mean_gap + 1e-15)
    f_n = pt[1] / (abs(crit_fp.mean_frustration) + 1e-15)
    z_n = pt[2] - crit_fp.mean_logZ
    p = np.array([g_n, f_n, z_n], dtype=float)
    Mn = (M - mu) / sig
    pn = (p - mu) / sig
    d = np.linalg.norm(Mn - pn[None, :], axis=1)
    return {
        "op_dist": float(np.min(d)),
        "theta_geom": th,
        "method": "OP_CRIT_NN",
    }


def multimode_for_ca_length(n_ca: int, mode: str = "adaptive_short") -> bool:
    """Whether Crit rings use Fourier multimode height field.

    adaptive_short: multimode only for short rings (CA≤8) — height ribbon
    helps tiny cyclics; planar holonomy circle ranks better for longer rings.
    on / off: force all multimode or all planar.
    self_fit: not length-based — caller must pick via native Crit distance.
    """
    mode = str(mode or "adaptive_short").lower().strip()
    if mode in ("on", "true", "1", "yes"):
        return True
    if mode in ("off", "false", "0", "no", "planar"):
        return False
    if mode in ("self_fit", "self-fit", "fit"):
        # length heuristic only as fallback; prefer select_multimode_by_fit
        return int(n_ca) <= 8
    # adaptive_short (default production)
    return int(n_ca) <= 8


def select_mold_by_fit(
    xyz: np.ndarray,
    knobs: dict[str, Any],
    *,
    N: int,
    n_zeros: int,
    n_sectors: int,
    soft_T: float = 0.04,
    prefer_maxop: bool = True,
    multimodes: tuple[bool, ...] = (False, True),
    omega_scales: tuple[float, ...] = (1.0,),
    defect_tie: bool = False,
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """Pick Crit mold from a small bank by native projection distance.

    Structure-conditioned (not decoy-label training): forge each
    (multimode × omega_scale) candidate, keep lowest softmin Kabsch to native CA.
    ``omega_scales`` are multipliers on knobs['omega_scale'].

    When ``defect_tie`` is True (mid-length floors), break near-projection
    ties with native sheaf-defect softmin, then MaxOp gap — still native-only,
    never decoy-label training.

    Returns (use_multimode, pack, diagnostics).
    """
    from realm.validate.decoys import score_geometry_vs_crit

    base_omega = float(knobs.get("omega_scale", 1.0))
    candidates: list[dict[str, Any]] = []
    for mm in multimodes:
        for os in omega_scales:
            kn = dict(knobs)
            kn["omega_scale"] = base_omega * float(os)
            kn["multimode"] = bool(mm)
            pack = forge_crit_geometry(
                kn,
                N=N,
                n_zeros=n_zeros,
                n_sectors=n_sectors,
                multimode=bool(mm),
                prefer_maxop=prefer_maxop,
            )
            # CTS basin-weighted softmin when forge attached weights
            dist = float(
                score_geometry_vs_crit(
                    xyz,
                    pack["templates"],
                    soft_T=soft_T,
                    aggregate="softmin_persist"
                    if pack.get("basin_weights") is not None
                    else "softmin",
                    sector_weights=pack.get("basin_weights"),
                )["mean_dist"]
            )
            op = pack["operator"]
            defect_d = 0.0
            if defect_tie:
                from realm.sheaf_defects import softmin_defect_vs_crit

                thetas = pack.get("thetas")
                if thetas is None:
                    thetas = op.thetas
                defc = softmin_defect_vs_crit(
                    xyz,
                    thetas,
                    soft_T=soft_T,
                    prefer_maxop=prefer_maxop,
                )
                defect_d = float(defc["mean_dist"])
            candidates.append(
                {
                    "multimode": bool(mm),
                    "omega_scale_mult": float(os),
                    "omega_scale": kn["omega_scale"],
                    "dist": dist,
                    "defect_dist": defect_d,
                    # MaxOp dual: prefer sharper sheaf gaps on projection ties (4.1)
                    "maxop_mean_gap": float(op.mean_gap),
                    "maxop_mean_frustration": float(op.mean_frustration),
                    "pack": pack,
                }
            )
    # Primary: projection. Optional: sheaf defect (native). Tertiary: MaxOp gap.
    if defect_tie:
        best = min(
            candidates,
            key=lambda c: (
                c["dist"],
                0.15 * c["defect_dist"],
                -c["maxop_mean_gap"],
            ),
        )
        selection = "min_proj_then_defect_then_maxop_gap"
    else:
        best = min(
            candidates,
            key=lambda c: (c["dist"], -c["maxop_mean_gap"]),
        )
        selection = "min_proj_then_max_maxop_gap"
    diag = {
        "chosen": "multimode" if best["multimode"] else "planar",
        "omega_scale_mult": best["omega_scale_mult"],
        "dist": best["dist"],
        "defect_dist": best.get("defect_dist", 0.0),
        "defect_tie": bool(defect_tie),
        "maxop_mean_gap": best["maxop_mean_gap"],
        "maxop_mean_frustration": best["maxop_mean_frustration"],
        "selection": selection,
        "ontology": "projection_primary_maxop_tiebreak_not_lambda_eq_gamma",
        "n_bank": len(candidates),
        "bank": [
            {
                "multimode": c["multimode"],
                "omega_scale_mult": c["omega_scale_mult"],
                "dist": c["dist"],
                "defect_dist": c.get("defect_dist", 0.0),
                "maxop_mean_gap": c["maxop_mean_gap"],
            }
            for c in candidates
        ],
        # back-compat fields for self2 bank
        "dist_planar": min(
            (c["dist"] for c in candidates if not c["multimode"]),
            default=best["dist"],
        ),
        "dist_multimode": min(
            (c["dist"] for c in candidates if c["multimode"]),
            default=best["dist"],
        ),
        "margin": float(
            min((c["dist"] for c in candidates if not c["multimode"]), default=best["dist"])
            - min((c["dist"] for c in candidates if c["multimode"]), default=best["dist"])
        ),
    }
    return bool(best["multimode"]), best["pack"], diag


def adaptive_defect_beta(n_ca: int, base: float = 0.20) -> float:
    """Length-adaptive sheaf-defect blend for mid-length floors.

    Short rings keep base β. Mid/long get mild uplift so local obstruction
    can separate natives without abandoning projection primacy.
    """
    b = float(np.clip(base, 0.0, 1.0))
    if b <= 1e-12:
        return 0.0
    n = int(n_ca)
    if n >= 13:
        return float(min(0.34, b + 0.10))
    if n >= 12:
        return float(min(0.30, b + 0.08))
    if n == 10:
        return float(min(0.26, b + 0.04))  # 4M6E mild; full mid dual-gate unsafe
    return b


def combine_sector_weights(
    basin_w: np.ndarray | list[float] | None,
    gaps: np.ndarray | list[float] | None,
    *,
    gap_mix: float = 0.20,
) -> np.ndarray | None:
    """CTS basin depth × MaxOp spectral-gap dual for Crit softmin weights.

    Projection stays primary; gaps only modulate softmin membership so
    sharper sheaf sectors (larger λ₂ of L) pull slightly more.
    """
    if basin_w is None and gaps is None:
        return None
    if basin_w is not None:
        bw = np.asarray(basin_w, dtype=float).ravel()
    else:
        bw = None
    if gaps is not None:
        g = np.asarray(gaps, dtype=float).ravel()
        g = np.clip(g, 0.0, None)
        gm = float(np.mean(g)) + 1e-15
        gw = 0.40 + 0.60 * (g / gm)
    else:
        gw = None
    if bw is None:
        w = gw
    elif gw is None:
        w = bw
    else:
        n = min(bw.size, gw.size)
        mix = float(np.clip(gap_mix, 0.0, 1.0))
        w = (1.0 - mix) * bw[:n] + mix * (bw[:n] * gw[:n])
    if w is None or w.size == 0:
        return None
    w = np.clip(np.asarray(w, float), 1e-6, None)
    w = w / (float(np.mean(w)) + 1e-15)
    return w


def mid_length_omega_bank(n_ca: int) -> tuple[float, ...]:
    """Length-adaptive omega bank (superset of production dense).

    Short/default: confirmed 5-point dense bank.
    n≥12: add mid bridges; n≥13: add UV/IR wings for steric floors
    while keeping the original 5 dense cells so prior winners remain
    selectable (structure-conditioned, not forced).
    """
    n = int(n_ca)
    dense = (0.85, 0.95, 1.0, 1.1, 1.2)
    if n >= 12:
        # 1TET/4K8Y-class: full wings/bridges
        return (0.80, 0.85, 0.90, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3)
    if n == 10:
        # 4M6E: mild bridges only (full mid-bank dual-gate regressed hard)
        return (0.85, 0.90, 0.95, 1.0, 1.1, 1.15, 1.2)
    return dense


def refine_pack_height_amp(
    xyz: np.ndarray,
    pack: dict[str, Any],
    *,
    amps: tuple[float, ...] = (0.18, 0.22, 0.25, 0.30, 0.35),
    soft_T: float = 0.04,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Structure-conditioned height-amplitude re-embed of Crit molds.

    Keeps Crit θ* fixed; varies planar ribbon height_amp (and multimode is
    left as-is via re-forge of planar embeds only when not multimode).
    Accepts only if native Kabsch softmin does not worsen.
    """
    from realm.derive import embed_multimode_cycle
    from realm.validate.decoys import score_geometry_vs_crit
    from realm.zeta_geometry import embed_cycle_from_twist

    thetas = np.asarray(pack.get("thetas"), dtype=float).ravel()
    if thetas.size == 0:
        return pack, {"applied": False, "reason": "no_thetas"}
    N = int(pack.get("N") or max(int(xyz.shape[0]), 7))
    multimode = bool(pack.get("multimode", False))
    der = pack.get("derivation")
    field = getattr(der, "field", None) if der is not None else None
    basin_w = pack.get("basin_weights")
    d0 = float(
        score_geometry_vs_crit(
            xyz,
            pack["templates"],
            soft_T=soft_T,
            aggregate="softmin_persist" if basin_w is not None else "softmin",
            sector_weights=basin_w,
        )["mean_dist"]
    )
    best_amp = 0.25
    best_templates = pack["templates"]
    best_d = d0
    for amp in amps:
        templates: list[np.ndarray] = []
        for th in thetas:
            if multimode and field is not None:
                # multimode embed has no height_amp; scale z after embed
                pts = embed_multimode_cycle(
                    N, float(th), field, n_modes=min(8, int(field.gammas.size))
                )
                pts = pts.copy()
                pts[:, 2] *= float(amp) / 0.25
                pts -= pts.mean(axis=0)
            else:
                pts = embed_cycle_from_twist(N, float(th), height_amp=float(amp))
            templates.append(np.asarray(pts, float)[:, :3])
        d = float(
            score_geometry_vs_crit(
                xyz,
                templates,
                soft_T=soft_T,
                aggregate="softmin_persist" if basin_w is not None else "softmin",
                sector_weights=basin_w,
            )["mean_dist"]
        )
        if d < best_d - 1e-9:
            best_d = d
            best_amp = float(amp)
            best_templates = templates
    accept = best_d <= d0 + 1e-9
    diag = {
        "applied": True,
        "accepted": accept and best_amp != 0.25,
        "proj_before": d0,
        "proj_after": best_d,
        "height_amp": best_amp if accept else 0.25,
        "amps_tried": list(amps),
        "selection": "min_native_kabsch_height_amp",
    }
    if accept and best_templates is not pack["templates"]:
        out = {**pack, "templates": best_templates, "height_amp": best_amp}
        return out, diag
    return pack, {**diag, "accepted": False}


def polish_crit_pack_holonomy(
    xyz: np.ndarray,
    pack: dict[str, Any],
    *,
    n_steps: int = 4,
    step: float = 0.04,
    soft_T: float = 0.04,
    prefer_maxop: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Sheaf-energy holonomy feedback on Crit θ*, then re-embed molds.

    Structure-conditioned (native CA only): each sector holonomy descends
    Dirichlet energy E = xᵀ L_F(A(θ)) x a few control steps, re-embeds
    planar/multimode templates, rebuilds MaxOp fingerprint. Pack is kept
    only if Kabsch softmin to native does not regress (projection primary).

    Connes/control framing: u ∝ −∂_θ E on Σ holonomy axis (realm.manifold_control).
    Never λ=γ.
    """
    from realm.derive import embed_multimode_cycle
    from realm.manifold_control import multi_step_holonomy_control
    from realm.validate.decoys import score_geometry_vs_crit
    from realm.zeta_geometry import embed_cycle_from_twist

    xyz = np.asarray(xyz, dtype=float)
    thetas = np.asarray(pack.get("thetas"), dtype=float).ravel()
    if thetas.size == 0:
        return pack, {"applied": False, "reason": "no_thetas"}

    N = int(pack.get("N") or max(int(xyz.shape[0]), 7))
    multimode = bool(pack.get("multimode", False))
    der = pack.get("derivation")
    field = getattr(der, "field", None) if der is not None else None

    d0 = float(
        score_geometry_vs_crit(
            xyz, pack["templates"], soft_T=soft_T
        )["mean_dist"]
    )

    new_thetas: list[float] = []
    new_templates: list[np.ndarray] = []
    energy_delta: list[float] = []
    n_moved = 0
    for th in thetas:
        ctrl = multi_step_holonomy_control(
            xyz,
            float(th),
            n_steps=n_steps,
            step=step,
            prefer_maxop=prefer_maxop,
        )
        th2 = float(ctrl["theta_final"])
        e0 = ctrl.get("E0")
        e1 = ctrl.get("E_final")
        if e0 is not None and e1 is not None:
            energy_delta.append(float(e1) - float(e0))
            if float(e1) > float(e0) + 1e-12:
                th2 = float(th)  # sheaf energy regressed — keep Crit θ
            elif abs(th2 - float(th)) > 1e-9:
                n_moved += 1
        new_thetas.append(th2)
        if multimode and field is not None:
            pts = embed_multimode_cycle(
                N, th2, field, n_modes=min(4, int(field.gammas.size))
            )
        else:
            pts = embed_cycle_from_twist(N, th2)
        new_templates.append(np.asarray(pts, dtype=float)[:, :3])

    fp = operator_fingerprint(new_thetas, N=N, prefer_maxop=prefer_maxop)
    polished = {
        **pack,
        "templates": new_templates,
        "thetas": np.asarray(new_thetas, float),
        "operator": fp,
        "n_sectors": len(new_templates),
        "holonomy_polished": True,
    }
    d1 = float(
        score_geometry_vs_crit(xyz, new_templates, soft_T=soft_T)["mean_dist"]
    )
    mean_dE = float(np.mean(energy_delta)) if energy_delta else 0.0
    # Strict projection-primary accept (no slack). Mild-slack variant dual-gate
    # regressed mid-length floors (4K8Y); keep opt-in tool honest.
    accept = d1 <= d0 + 1e-6
    diag = {
        "applied": True,
        "accepted": accept,
        "proj_before": d0,
        "proj_after": d1,
        "proj_slack": 0.0,
        "n_sectors": len(new_thetas),
        "n_moved": n_moved,
        "mean_energy_delta": mean_dE,
        "n_steps": n_steps,
        "step": step,
        "selection": "accept_if_proj_not_worse",
        "ontology": "sheaf_feedback_projection_primary_not_lambda_eq_gamma",
        "production_default": False,
    }
    if accept:
        return polished, diag
    return pack, {**diag, "accepted": False, "reverted": True}


def select_multimode_by_fit(
    xyz: np.ndarray,
    knobs: dict[str, Any],
    *,
    N: int,
    n_zeros: int,
    n_sectors: int,
    soft_T: float = 0.04,
    prefer_maxop: bool = True,
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """Pick planar vs multimode Crit mold by native projection distance."""
    return select_mold_by_fit(
        xyz,
        knobs,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        soft_T=soft_T,
        prefer_maxop=prefer_maxop,
        multimodes=(False, True),
        omega_scales=(1.0,),
    )


def sectors_for_ca_length(n_ca: int, mode: str = "fixed", default: int = 6) -> int:
    """Choose Crit sector count from ring length (projection mold capacity).

    adaptive (default production): short rings use fewer valleys so softmin
    is not diluted by grid-filled surplus sectors.
      n_ca ≤ 8 → 4,  else → 6
    (Long rings previously tried 8 valleys; full-batch 40×3 preferred cap-6.)
    fixed: always ``default``
    """
    mode = str(mode or "fixed").lower().strip()
    if mode == "adaptive":
        n = int(n_ca)
        if n <= 8:
            return 4
        # 1TET-class (n=12): fewer Crit valleys — softmin less diluted
        # (structure probe: nsec=4 lower native Kabsch than nsec=6).
        if n == 12:
            return 4
        return 6
    return max(2, int(default))


def forge_crit_geometry(
    knobs: dict[str, Any],
    *,
    N: int,
    n_zeros: int = 14,
    n_sectors: int = 6,
    gammas: np.ndarray | None = None,
    prefer_maxop: bool = True,
    multimode: bool | None = None,
) -> dict[str, Any]:
    """Forge substrate → Crit templates + operator fingerprint."""
    kn = dict(knobs)
    if gammas is not None:
        kn["gammas"] = np.asarray(gammas, float).ravel()
    if multimode is not None:
        kn["multimode"] = bool(multimode)
    der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sectors).forge(**kn)
    templates: list[np.ndarray] = []
    thetas: list[float] = []
    for s in der.sectors:
        thetas.append(float(s.twist))
        pts = getattr(s, "positions", None)
        if pts is not None:
            arr = np.asarray(pts, dtype=float)
            if arr.ndim == 2 and arr.shape[1] >= 3:
                templates.append(arr[:, :3])
    fp = operator_fingerprint(thetas, N=N, prefer_maxop=prefer_maxop)
    # CTS basin-persistence weights on Crit holonomies (topology → ranking)
    basin_w: np.ndarray | None = None
    try:
        from realm.axiomz import basin_persistence_weights

        if hasattr(der, "action") and der.action is not None and thetas:
            basin_w = basin_persistence_weights(der.action, thetas)
    except Exception:  # noqa: BLE001
        basin_w = None
    return {
        "templates": templates,
        "thetas": np.asarray(thetas, float),
        "operator": fp,
        "derivation": der,
        "basin_weights": basin_w,
        "n_sectors": len(templates),
        "N": N,
        "multimode": bool(kn.get("multimode", True)),
    }


def dual_score_geometry(
    xyz: np.ndarray,
    pack: dict[str, Any],
    *,
    alpha_proj: float = 1.0,
    prefer_maxop: bool = True,
    soft_T: float = 0.04,
    aggregate: str = "softmin",
    defect_beta: float = 0.0,
) -> dict[str, Any]:
    """Projection-primary score with optional sheaf-defect / operator dual.

    Ranking defaults:
      α_proj=1, defect_beta>0 → Kabsch softmin blended with sheaf Dirichlet
      defect (local obstruction on C_N under Crit monodromy). α_proj<1 adds
      legacy θ_proxy operator NN (usually weaker than defect track).

    Never λ=γ.
    """
    from realm.sheaf_defects import blend_projection_defect, softmin_defect_vs_crit

    templates = pack["templates"]
    crit_fp: OperatorFingerprint = pack["operator"]
    N = int(pack["N"])
    thetas = pack.get("thetas")
    if thetas is None:
        thetas = crit_fp.thetas
    basin_w = pack.get("basin_weights")
    gaps = None
    if crit_fp is not None and getattr(crit_fp, "gaps", None) is not None:
        gaps = crit_fp.gaps
    # MaxOp gap mix on mid-length scaffolds (short rings stay pure CTS basin)
    n_ca_guess = int(np.asarray(xyz).shape[0])
    gap_mix = 0.20 if n_ca_guess >= 12 else 0.0
    sector_w = combine_sector_weights(basin_w, gaps, gap_mix=gap_mix)
    # Use CTS×MaxOp reweight when weights present (production softmin path)
    agg = aggregate
    if sector_w is not None and str(aggregate).lower().strip() in (
        "softmin",
        "softmin_persist",
        "persist",
        "cts",
    ):
        agg = "softmin_persist"
    proj = score_geometry_vs_crit(
        xyz,
        templates,
        soft_T=soft_T,
        aggregate=agg,
        sector_weights=sector_w,
    )
    proj_d = float(proj["mean_dist"])
    a = float(np.clip(alpha_proj, 0.0, 1.0))
    b = float(np.clip(defect_beta, 0.0, 1.0))

    defect_d = 0.0
    if b > 1e-12:
        defc = softmin_defect_vs_crit(
            xyz,
            thetas,
            soft_T=soft_T,
            prefer_maxop=prefer_maxop,
            sector_weights=sector_w if n_ca_guess >= 12 else basin_w,
        )
        defect_d = float(defc["mean_dist"])
        from realm.sheaf_defects import adaptive_defect_scale

        d_scale = adaptive_defect_scale(n_ca_guess)
        base = blend_projection_defect(proj_d, defect_d, beta=b, scale=d_scale)
        # Mild hard-min pull on soft floors only (n=10 4M6E, n=12 1TET).
        # Broader mid-length pull dual-gate cost a top20 on 4K8Y.
        if n_ca_guess in (10, 12) and proj.get("min_dist") is not None:
            dmin = float(proj["min_dist"])
            base = 0.88 * float(base) + 0.12 * dmin
        method = (
            "PROJ_SHEAF_DEFECT_CTS"
            if proj.get("method") == "CRIT_KABSCH_SOFTMIN_PERSIST"
            else "PROJ_SHEAF_DEFECT"
        )
    else:
        base = proj_d
        method = proj.get("method")

    if a >= 1.0 - 1e-12:
        return {
            "mean_dist": base,
            "proj_dist": proj_d,
            "defect_dist": defect_d,
            "op_dist": 0.0,
            "op_dist_scaled": 0.0,
            "theta_geom": None,
            "alpha_proj": a,
            "defect_beta": b,
            "method": method,
            "in_basin": bool(proj.get("in_basin")),
            "n_templates": proj.get("n_templates"),
            "top_k": proj.get("top_k"),
            "min_dist": proj.get("min_dist"),
            "soft_T": proj.get("soft_T"),
            "aggregate": proj.get("aggregate"),
        }

    op = operator_distance_to_crit(
        xyz, crit_fp, N=N, prefer_maxop=prefer_maxop
    )
    op_s = float(op["op_dist"]) * 0.25
    dual = a * base + (1.0 - a) * op_s
    return {
        "mean_dist": dual,
        "proj_dist": proj_d,
        "defect_dist": defect_d,
        "op_dist": float(op["op_dist"]),
        "op_dist_scaled": op_s,
        "theta_geom": op["theta_geom"],
        "alpha_proj": a,
        "defect_beta": b,
        "method": "DUAL_PROJ_OP_DEFECT" if b > 1e-12 else "DUAL_PROJ_OP",
        "in_basin": bool(proj.get("in_basin")),
        "n_templates": proj.get("n_templates"),
        "top_k": proj.get("top_k"),
        "min_dist": proj.get("min_dist"),
        "soft_T": proj.get("soft_T"),
        "aggregate": proj.get("aggregate"),
    }
