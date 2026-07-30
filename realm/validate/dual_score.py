"""Projection + sheaf-defect scoring (Crit Kabsch, L=δ*δ dual).

ScorePipeline is the ranking scorer: Crit softmin ± sheaf defect ± optional
Coutsias blend. LengthPolicy supplies gap_mix / hardmin / defect_scale.
Never λ=γ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from realm.validate.decoys import score_geometry_vs_crit
from realm.validate.length_policy import LengthPolicy, policy_for


def combine_sector_weights(
    basin_w: np.ndarray | list[float] | None,
    gaps: np.ndarray | list[float] | None,
    *,
    gap_mix: float = 0.20,
) -> np.ndarray | None:
    """CTS basin depth × MaxOp spectral-gap dual for Crit softmin weights."""
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


def dual_score_geometry(
    xyz: np.ndarray,
    pack: dict[str, Any],
    *,
    alpha_proj: float = 1.0,
    prefer_maxop: bool = True,
    soft_T: float = 0.04,
    aggregate: str = "softmin",
    defect_beta: float = 0.0,
    policy: LengthPolicy | None = None,
    residue_weights: np.ndarray | list[float] | None = None,
) -> dict[str, Any]:
    """Projection-primary score with optional sheaf-defect / operator dual."""
    from realm.sheaf_defects import blend_projection_defect, softmin_defect_vs_crit
    from realm.validate.dual import OperatorFingerprint, operator_distance_to_crit

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
    n_ca_guess = int(np.asarray(xyz).shape[0])
    pol = policy if policy is not None else policy_for(
        n_ca_guess, base_beta=float(defect_beta)
    )
    sector_w = combine_sector_weights(basin_w, gaps, gap_mix=pol.gap_mix)
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
            chord_weight=float(pol.chord_weight),
            face_weight=float(pol.face_weight),
            residue_weights=residue_weights,
            sector_weights=sector_w if pol.gap_mix > 1e-12 else basin_w,
        )
        defect_d = float(defc["mean_dist"])
        base = blend_projection_defect(
            proj_d, defect_d, beta=b, scale=pol.defect_scale
        )
        hm = float(pol.hardmin_mix)
        if hm > 1e-12 and proj.get("min_dist") is not None:
            dmin = float(proj["min_dist"])
            base = (1.0 - hm) * float(base) + hm * dmin
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

    op = operator_distance_to_crit(xyz, crit_fp, N=N, prefer_maxop=prefer_maxop)
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


@dataclass
class ScorePipeline:
    """Crit Kabsch ± sheaf L dual ± optional Coutsias blend."""

    pack: dict[str, Any]
    policy: LengthPolicy
    alpha_proj: float = 1.0
    soft_T: float = 0.04
    aggregate: str = "softmin"
    prefer_maxop: bool = True
    coutsias_alpha: float = 0.0
    coutsias_bank: dict[str, Any] | None = None
    residue_weights: np.ndarray | None = None

    def score(self, pts: np.ndarray) -> dict[str, Any]:
        sc = dual_score_geometry(
            pts,
            self.pack,
            alpha_proj=self.alpha_proj,
            prefer_maxop=self.prefer_maxop,
            soft_T=self.soft_T,
            aggregate=self.aggregate,
            defect_beta=float(self.policy.defect_beta),
            policy=self.policy,
            residue_weights=self.residue_weights,
        )
        a = float(self.coutsias_alpha)
        bank = self.coutsias_bank
        if bank is not None and a > 1e-12 and not bank.get("empty"):
            from realm.prime_fold import (
                blend_crit_coutsias_dist,
                score_geometry_vs_coutsias,
            )

            ck = score_geometry_vs_coutsias(pts, bank, soft_T=self.soft_T)
            blended = blend_crit_coutsias_dist(
                float(sc["mean_dist"]),
                float(ck["mean_dist"]),
                alpha=a,
            )
            sc = {
                **sc,
                "mean_dist": blended,
                "crit_dist": float(sc["mean_dist"]),
                "coutsias_dist": float(ck["mean_dist"]),
                "coutsias_alpha": a,
                "method": f"{sc.get('method')}+COUTSIAS",
            }
        return sc

    @classmethod
    def build(
        cls,
        pack: dict[str, Any],
        policy: LengthPolicy,
        *,
        alpha_proj: float = 1.0,
        soft_T: float = 0.04,
        aggregate: str = "softmin",
        coutsias_alpha: float = 0.0,
        coutsias_starts: int = 12,
        resnames: list[str] | None = None,
    ) -> "ScorePipeline":
        """Build scorer; forge Coutsias bank only when policy.coutsias_scope."""
        c_alpha_req = float(np.clip(coutsias_alpha, 0.0, 1.0))
        c_alpha = c_alpha_req if policy.coutsias_scope else 0.0
        c_bank = None
        if c_alpha > 1e-12:
            from realm.prime_fold import forge_coutsias_mold_bank

            c_bank = forge_coutsias_mold_bank(
                policy.n_ca,
                max_roots=max(4, min(policy.n_sectors, 6)),
                n_starts=int(coutsias_starts),
                use_de=False,
                prefer_maxop=False,
                cache=True,
            )
        rw = None
        if resnames is not None and float(policy.seq_mix) > 1e-12:
            from realm.sequence_features import sequence_residue_weights

            rw = sequence_residue_weights(resnames, mix=float(policy.seq_mix))
        return cls(
            pack=pack,
            policy=policy,
            alpha_proj=float(np.clip(alpha_proj, 0.0, 1.0)),
            soft_T=float(soft_T),
            aggregate=aggregate,
            coutsias_alpha=c_alpha,
            coutsias_bank=c_bank,
            residue_weights=rw,
        )
