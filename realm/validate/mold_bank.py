"""Crit mold bank: structure-conditioned select, height refine, holonomy polish.

Projection-primary mold pick (native CA only). Never decoy-label training.
Never λ=γ.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def multimode_for_ca_length(n_ca: int, mode: str = "adaptive_short") -> bool:
    """Whether Crit rings use Fourier multimode height field.

    adaptive_short: multimode only for short rings (CA≤8).
    on / off: force all multimode or all planar.
    """
    mode = str(mode or "adaptive_short").lower().strip()
    if mode in ("on", "true", "1", "yes"):
        return True
    if mode in ("off", "false", "0", "no", "planar"):
        return False
    if mode in ("self_fit", "self-fit", "fit"):
        return int(n_ca) <= 8
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
    residue_weights: np.ndarray | list[float] | None = None,
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """Pick Crit mold from (multimode × omega) bank by native projection distance.

    When ``defect_tie`` is True, break near-projection ties with native
    sheaf-defect softmin (optional sequence residue_weights), then MaxOp gap.
    """
    from realm.validate.decoys import score_geometry_vs_crit
    from realm.validate.dual import forge_crit_geometry

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
                    residue_weights=residue_weights,
                )
                defect_d = float(defc["mean_dist"])
            candidates.append(
                {
                    "multimode": bool(mm),
                    "omega_scale_mult": float(os),
                    "omega_scale": kn["omega_scale"],
                    "dist": dist,
                    "defect_dist": defect_d,
                    "maxop_mean_gap": float(op.mean_gap),
                    "maxop_mean_frustration": float(op.mean_frustration),
                    "pack": pack,
                }
            )
    if defect_tie:
        best = min(
            candidates,
            key=lambda c: (c["dist"], 0.15 * c["defect_dist"], -c["maxop_mean_gap"]),
        )
        selection = (
            "min_proj_then_seq_defect_then_maxop_gap"
            if residue_weights is not None
            else "min_proj_then_defect_then_maxop_gap"
        )
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
        "sequence_mold_tie": residue_weights is not None,
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
        "dist_planar": min(
            (c["dist"] for c in candidates if not c["multimode"]),
            default=best["dist"],
        ),
        "dist_multimode": min(
            (c["dist"] for c in candidates if c["multimode"]),
            default=best["dist"],
        ),
        "margin": float(
            min(
                (c["dist"] for c in candidates if not c["multimode"]),
                default=best["dist"],
            )
            - min(
                (c["dist"] for c in candidates if c["multimode"]),
                default=best["dist"],
            )
        ),
    }
    return bool(best["multimode"]), best["pack"], diag


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


def refine_pack_height_amp(
    xyz: np.ndarray,
    pack: dict[str, Any],
    *,
    amps: tuple[float, ...] = (0.18, 0.22, 0.25, 0.30, 0.35),
    soft_T: float = 0.04,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Structure-conditioned height-amplitude re-embed of Crit molds."""
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
    """Sheaf-energy holonomy feedback on Crit θ*, then re-embed molds."""
    from realm.derive import embed_multimode_cycle
    from realm.manifold_control import multi_step_holonomy_control
    from realm.validate.decoys import score_geometry_vs_crit
    from realm.validate.dual import operator_fingerprint
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
        score_geometry_vs_crit(xyz, pack["templates"], soft_T=soft_T)["mean_dist"]
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
                th2 = float(th)
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


def forge_mold_pack(
    xyz: np.ndarray,
    knobs: dict[str, Any],
    *,
    N: int,
    n_zeros: int,
    n_sectors: int,
    soft_T: float,
    multimode_mode: str,
    multimode: bool | None,
    omega_scales: tuple[float, ...],
    defect_tie: bool,
    height_refine: bool,
    holonomy_polish: bool = False,
    residue_weights: np.ndarray | list[float] | None = None,
) -> tuple[bool, dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    """Single mold pipeline: select → optional polish → optional height refine.

    Returns (use_multimode, pack, fit_diag, height_diag).
    """
    from realm.validate.dual import forge_crit_geometry
    from realm.validate.length_policy import mid_length_omega_bank

    mm_mode = str(multimode_mode or "adaptive_short").lower().strip()
    fit_diag = None
    polish_diag = None
    height_diag = None
    # Sequence weights only enter defect_tie mold selection (not scoring).
    rw = residue_weights if defect_tie else None

    if multimode is not None:
        use_mm = bool(multimode)
        pack = forge_crit_geometry(
            knobs, N=N, n_zeros=n_zeros, n_sectors=n_sectors, multimode=use_mm
        )
    elif mm_mode in ("self_fit", "self-fit", "fit"):
        use_mm, pack, fit_diag = select_multimode_by_fit(
            xyz, knobs, N=N, n_zeros=n_zeros, n_sectors=n_sectors, soft_T=soft_T
        )
    elif mm_mode in ("self_fit_omega", "self_fit_bank", "bank"):
        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sectors,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=(0.9, 1.0, 1.15),
        )
    elif mm_mode in ("self_fit_dense", "dense"):
        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sectors,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=omega_scales,
            defect_tie=defect_tie,
            residue_weights=rw,
        )
    elif mm_mode in ("self_fit_mid", "mid"):
        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sectors,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=mid_length_omega_bank(max(int(xyz.shape[0]), 12)),
            defect_tie=True,
            residue_weights=rw,
        )
    elif mm_mode in ("self_fit_wide", "wide"):
        use_mm, pack, fit_diag = select_mold_by_fit(
            xyz,
            knobs,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sectors,
            soft_T=soft_T,
            multimodes=(False, True),
            omega_scales=(0.8, 0.9, 1.0, 1.15, 1.3),
        )
    else:
        use_mm = multimode_for_ca_length(int(xyz.shape[0]), mode=mm_mode)
        pack = forge_crit_geometry(
            knobs, N=N, n_zeros=n_zeros, n_sectors=n_sectors, multimode=use_mm
        )

    moldish = mm_mode in (
        "self_fit_dense",
        "dense",
        "self_fit_mid",
        "mid",
        "self_fit_wide",
        "wide",
        "self_fit_omega",
        "self_fit",
        "self-fit",
        "fit",
        "bank",
    )
    n_ca = int(xyz.shape[0])
    if holonomy_polish and n_ca >= 12 and moldish:
        pack, polish_diag = polish_crit_pack_holonomy(
            xyz, pack, n_steps=4, step=0.04, soft_T=soft_T, prefer_maxop=True
        )
    if height_refine and moldish:
        pack, height_diag = refine_pack_height_amp(xyz, pack, soft_T=soft_T)

    # attach polish_diag on pack meta for callers that want both
    if polish_diag is not None:
        pack = {**pack, "_polish_diag": polish_diag}
    return use_mm, pack, fit_diag, height_diag
