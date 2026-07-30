"""Generate Crit ∪ Coutsias mold ensembles for handoff export."""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.handoff.types import MoldRecord
from realm.validate.dual import forge_crit_geometry
from realm.validate.length_policy import mid_length_omega_bank, sectors_for_ca_length


def generate_crit_ensemble(
    knobs: dict[str, Any],
    *,
    N: int,
    n_zeros: int = 14,
    n_sectors: int | None = None,
    multimodes: tuple[bool, ...] = (False, True),
    omega_scales: tuple[float, ...] | None = None,
    prefer_maxop: bool = True,
) -> list[MoldRecord]:
    """Proposal-mode Crit bank: multimode × omega grid (no native self_fit)."""
    n_sec = int(
        n_sectors
        if n_sectors is not None
        else sectors_for_ca_length(N, mode="adaptive", default=6)
    )
    omegas = omega_scales if omega_scales is not None else mid_length_omega_bank(N)
    base_omega = float(knobs.get("omega_scale", 1.0))
    molds: list[MoldRecord] = []
    for mm in multimodes:
        for os in omegas:
            kn = dict(knobs)
            kn["omega_scale"] = base_omega * float(os)
            kn["multimode"] = bool(mm)
            pack = forge_crit_geometry(
                kn,
                N=int(N),
                n_zeros=int(n_zeros),
                n_sectors=n_sec,
                multimode=bool(mm),
                prefer_maxop=prefer_maxop,
            )
            templates = pack.get("templates") or []
            if not templates:
                continue
            # Use first sector template as mold representative; bank is Crit set
            # Export each sector as its own mold for diversity
            thetas = np.asarray(pack.get("thetas"), dtype=float).ravel()
            op = pack.get("operator")
            gap = float(op.mean_gap) if op is not None else None
            for si, pts in enumerate(templates):
                xyz = np.asarray(pts, dtype=float)[:, :3]
                if xyz.shape[0] != N:
                    # resample length mismatch: skip
                    if xyz.shape[0] < 3:
                        continue
                tw = float(thetas[si]) if si < thetas.size else None
                # rank_score: prefer sharper MaxOp gap + lower |S| proxy via frustration
                fr = float(op.mean_frustration) if op is not None else 0.0
                score = float(fr) - 0.1 * (gap or 0.0) + 0.01 * abs(float(os) - 1.0)
                molds.append(
                    MoldRecord(
                        source="crit",
                        N=int(xyz.shape[0]),
                        xyz=xyz,
                        rank_score=score,
                        method=f"crit_mm{int(mm)}_om{os:.3g}_sec{si}",
                        twist=tw,
                        maxop_gap=gap,
                        meta={
                            "multimode": bool(mm),
                            "omega_scale_mult": float(os),
                            "sector": si,
                        },
                    )
                )
    return molds


def generate_coutsias_ensemble(
    *,
    N: int,
    n_starts: int = 14,
    max_roots: int = 6,
    prefer_maxop: bool = False,
) -> list[MoldRecord]:
    """Coutsias multi-start closures as mold records."""
    from realm.prime_fold import forge_coutsias_mold_bank

    bank = forge_coutsias_mold_bank(
        int(N),
        max_roots=int(max_roots),
        n_starts=int(n_starts),
        use_de=False,
        prefer_maxop=prefer_maxop,
        cache=True,
    )
    if bank.get("empty") or not bank.get("templates"):
        return []
    molds: list[MoldRecord] = []
    scores = np.asarray(bank.get("scores"), dtype=float).ravel()
    twists = bank.get("twists") or []
    residuals = bank.get("residuals") or []
    for i, pts in enumerate(bank["templates"]):
        xyz = np.asarray(pts, dtype=float)[:, :3]
        sc = float(scores[i]) if i < scores.size else 1e9
        tw = float(twists[i]) if i < len(twists) else None
        res = float(residuals[i]) if i < len(residuals) else None
        molds.append(
            MoldRecord(
                source="coutsias",
                N=int(xyz.shape[0]),
                xyz=xyz,
                rank_score=sc,
                method="coutsias_spectral_action",
                twist=tw,
                maxop_gap=None,
                meta={"residual": res, "bank_index": i},
            )
        )
    return molds


def merge_and_rank(
    molds: list[MoldRecord],
    *,
    top_k: int = 8,
) -> list[MoldRecord]:
    """Sort by rank_score ascending; take top_k."""
    ordered = sorted(molds, key=lambda m: float(m.rank_score))
    k = max(1, int(top_k))
    return ordered[:k]
