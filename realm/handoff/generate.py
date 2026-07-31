"""Generate Crit ∪ Coutsias mold ensembles for handoff export."""

from __future__ import annotations

import inspect
import logging
from typing import Any

import numpy as np

from realm.handoff.types import MoldRecord
from realm.validate.dual import forge_crit_geometry
from realm.validate.length_policy import mid_length_omega_bank, sectors_for_ca_length

logger = logging.getLogger(__name__)

# Sentinel when Kabsch scoring fails — keeps mold out of top ranks without silent index scores.
_SCORE_FAIL = 1e9


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
                # Length mismatch or degenerate: skip (keep requested N only)
                if xyz.shape[0] != N or xyz.shape[0] < 3:
                    continue
                tw = float(thetas[si]) if si < thetas.size else None
                # rank_score: prefer sharper MaxOp gap + lower |S| proxy via frustration
                fr = float(op.mean_frustration) if op is not None else 0.0
                score = float(fr) - 0.1 * (gap or 0.0) + 0.01 * abs(float(os) - 1.0)
                molds.append(
                    MoldRecord(
                        source="crit",
                        N=int(N),
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


def _load_native_ca(path: str | Any, *, lo: int = 6, hi: int = 40):
    """Load native CA (+ optional resnames) from cached PDB path.

    This branch's ``load_ca_cyclic_band`` returns ``(xyz, chain)`` only.
    If a future pdb_io adds ``with_resnames``, use it via signature probe
    (no TypeError control-flow). Sequence-mold weights stay dormant until then.
    """
    from pathlib import Path as _Path

    from realm.validate.pdb_io import load_ca_cyclic_band

    p = _Path(path)
    sig = inspect.signature(load_ca_cyclic_band)
    if "with_resnames" in sig.parameters:
        loaded = load_ca_cyclic_band(p, lo=lo, hi=hi, with_resnames=True)
        if isinstance(loaded, tuple) and len(loaded) == 3:
            xyz, resnames, chain = loaded
            return xyz, resnames, chain
        xyz, chain = loaded  # type: ignore[misc]
        return xyz, None, chain
    # Current API: (xyz, chain) — no residue names available
    xyz, chain = load_ca_cyclic_band(p, lo=lo, hi=hi)
    return xyz, None, chain


def _kabsch_rank_vs_native(
    native_xyz: np.ndarray,
    mold_xyz: np.ndarray,
    *,
    soft_T: float,
    label: str,
) -> float:
    """Kabsch softmin distance of mold to native; lower is better. Sentinel on failure."""
    from realm.validate.decoys import score_geometry_vs_crit

    try:
        return float(
            score_geometry_vs_crit(
                native_xyz, [mold_xyz], soft_T=float(soft_T)
            )["mean_dist"]
        )
    except Exception as exc:  # noqa: BLE001 — keep failure visible, do not use index scores
        logger.warning(
            "score_geometry_vs_crit failed for %s: %s; using rank_score=%g",
            label,
            exc,
            _SCORE_FAIL,
        )
        return float(_SCORE_FAIL)


def generate_structure_ensemble(
    pdb_id: str,
    knobs: dict[str, Any],
    *,
    n_zeros: int = 14,
    top_k: int = 8,
    include_coutsias: bool = True,
    soft_T: float | None = None,
    defect_beta: float = 0.20,
) -> list[MoldRecord]:
    """Structure mode: self_fit_dense mold pack vs native CA; export pack templates.

    Production path: ``soft_T=None`` uses ``policy_for(n_ca).soft_T`` for both pack
    and Kabsch rank (dual-gate length table — do not hardcode 0.04).
    """
    from realm.validate.length_policy import policy_for
    from realm.validate.mold_bank import forge_mold_pack
    from realm.validate.pdb_io import fetch_pdb

    path = fetch_pdb(pdb_id)
    xyz, resnames, _chain = _load_native_ca(path, lo=6, hi=40)
    n_ca = int(xyz.shape[0])
    pol = policy_for(n_ca, base_beta=float(defect_beta), sectors_mode="adaptive")
    # Dual-gate: pack and score at policy soft_T unless caller overrides
    pack_T = float(pol.soft_T)
    score_T = float(soft_T) if soft_T is not None else pack_T

    mold_rw = None
    if (
        resnames is not None
        and pol.defect_tie
        and float(pol.seq_mold_mix) > 1e-12
    ):
        try:
            from realm.sequence_features import sequence_residue_weights

            mold_rw = sequence_residue_weights(
                resnames, mix=float(pol.seq_mold_mix)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sequence_residue_weights failed for %s: %s; continuing without mold_rw",
                pdb_id,
                exc,
            )
            mold_rw = None

    _mm, pack, fit_diag, _h = forge_mold_pack(
        xyz,
        knobs,
        N=max(n_ca, 7),
        n_zeros=int(n_zeros),
        n_sectors=pol.n_sectors,
        soft_T=pack_T,
        multimode_mode="self_fit_dense",
        multimode=None,
        omega_scales=pol.omega_scales,
        defect_tie=pol.defect_tie,
        height_refine=pol.height_refine,
        residue_weights=mold_rw,
    )
    molds: list[MoldRecord] = []
    thetas = pack.get("thetas")
    th = np.asarray(thetas, dtype=float).ravel() if thetas is not None else np.zeros(0)
    op = pack.get("operator")
    gap = float(op.mean_gap) if op is not None else None
    for si, pts in enumerate(pack.get("templates") or []):
        arr = np.asarray(pts, float)[:, :3]
        if arr.shape[0] < 3 or arr.shape[1] < 3:
            continue
        # Kabsch softmin of native vs this Crit template — lower = better native fit
        rank_score = _kabsch_rank_vs_native(
            xyz, arr, soft_T=score_T, label=f"crit_sec{si}"
        )
        molds.append(
            MoldRecord(
                source="crit",
                N=int(arr.shape[0]),
                xyz=arr,
                rank_score=rank_score,
                method="structure_self_fit_dense",
                twist=float(th[si]) if si < th.size else None,
                maxop_gap=gap,
                meta={
                    "fit": fit_diag,
                    "pdb_id": pdb_id.upper(),
                    "sector": si,
                    "n_ca_native": n_ca,
                    "resnames": list(resnames) if resnames is not None else None,
                },
            )
        )
    if include_coutsias:
        # Re-score Coutsias on the same Kabsch-vs-native scale as Crit so merge_and_rank
        # can interleave sources fairly (spectral action kept in meta).
        for cm in generate_coutsias_ensemble(N=n_ca, n_starts=10, max_roots=4):
            spectral = float(cm.rank_score)
            meta = dict(cm.meta or {})
            meta["spectral_action"] = spectral
            meta["pdb_id"] = pdb_id.upper()
            meta["n_ca_native"] = n_ca
            meta["resnames"] = list(resnames) if resnames is not None else None
            arr = np.asarray(cm.xyz, float)[:, :3]
            if arr.shape[0] < 3:
                continue
            cm.rank_score = _kabsch_rank_vs_native(
                xyz,
                arr,
                soft_T=score_T,
                label=f"coutsias_bank{meta.get('bank_index', '?')}",
            )
            cm.xyz = arr
            cm.meta = meta
            molds.append(cm)
    return merge_and_rank(molds, top_k=top_k)
