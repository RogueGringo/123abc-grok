"""Ultimate fold protocol skeleton — CTS of projected elements.

Pipeline (Witten-Morse + cellular sheaf + projection):

  substrate (ζ or control seed)
      → SpectralAction S_Λ (Morse potential on holonomy)
      → Crit(S) preferred monodromies
      → MaxOp L(A(θ*)) local net (operator dual)
      → geometric molds C_N ⊂ R³
      → structure-conditioned mold bank (self_fit_dense)
      → native-vs-decoy projection ranking

Never asserts λ=γ. Equal-budget *mold selection* across substrates;
knobs may still be ζ-seating defaults (reported honestly).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from realm.aqft_local import aqft_dual_report
from realm.axiomz import crit_action_filtration, run_term_series
from realm.lock_key import Keymaker
from realm.ontology import ONTOLOGY, ontology_note
from realm.validate.decoys import make_ca_decoys, score_geometry_vs_crit
from realm.validate.dual import (
    forge_crit_geometry,
    sectors_for_ca_length,
    select_mold_by_fit,
)
from realm.validate.pdb_io import fetch_pdb, load_ca_cyclic_band
from realm.validate.seeds import make_seed

# Production mold bank (projection-primary)
DENSE_OMEGA = (0.85, 0.95, 1.0, 1.1, 1.2)
SOFT_T = 0.04


def forge_with_substrate(
    knobs: dict[str, Any],
    *,
    kind: str,
    N: int,
    n_zeros: int,
    n_sectors: int,
    multimode: bool,
    omega_scale_mult: float = 1.0,
    rng: np.random.Generator | None = None,
) -> dict[str, Any]:
    """Forge Crit geometry from a named substrate seed (equal interface)."""
    rng = rng or np.random.default_rng(0)
    kn = dict(knobs)
    kn["omega_scale"] = float(knobs.get("omega_scale", 1.0)) * float(omega_scale_mult)
    kn["multimode"] = bool(multimode)
    if kind != "zeta":
        kn["gammas"] = make_seed(kind, n_zeros, rng)
    # zeta: omit gammas → real table via Keymaker/Deriver
    return forge_crit_geometry(
        kn,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        multimode=bool(multimode),
        prefer_maxop=True,
    )


def select_mold_for_substrate(
    xyz: np.ndarray,
    knobs: dict[str, Any],
    *,
    kind: str,
    n_zeros: int = 14,
    soft_T: float = SOFT_T,
    omega_scales: tuple[float, ...] = DENSE_OMEGA,
    rng: np.random.Generator | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Equal mold-bank budget: multimode × omega_scales, min proj dist.

    For non-ζ substrates, each bank cell gets an independent seed draw
    (same count of forges as ζ bank — equal selection budget).
    """
    rng = rng or np.random.default_rng(0)
    n_ca = int(xyz.shape[0])
    N = max(n_ca, 7)
    n_sec = sectors_for_ca_length(n_ca, mode="adaptive")
    base_omega = float(knobs.get("omega_scale", 1.0))
    candidates: list[dict[str, Any]] = []
    for mm in (False, True):
        for os in omega_scales:
            # independent RNG stream per cell for fair non-ζ draws
            cell_rng = np.random.default_rng(
                int(rng.integers(0, 2**31 - 1))
            )
            pack = forge_with_substrate(
                knobs,
                kind=kind,
                N=N,
                n_zeros=n_zeros,
                n_sectors=n_sec,
                multimode=mm,
                omega_scale_mult=float(os),
                rng=cell_rng,
            )
            dist = float(
                score_geometry_vs_crit(
                    xyz, pack["templates"], soft_T=soft_T
                )["mean_dist"]
            )
            op = pack["operator"]
            candidates.append(
                {
                    "multimode": mm,
                    "omega_scale_mult": float(os),
                    "dist": dist,
                    "maxop_mean_gap": float(op.mean_gap),
                    "pack": pack,
                }
            )
    best = min(candidates, key=lambda c: (c["dist"], -c["maxop_mean_gap"]))
    diag = {
        "kind": kind,
        "chosen_multimode": best["multimode"],
        "omega_scale_mult": best["omega_scale_mult"],
        "dist": best["dist"],
        "maxop_mean_gap": best["maxop_mean_gap"],
        "n_bank": len(candidates),
        "n_sectors": n_sec,
        "N": N,
        "selection": "equal_budget_min_proj_then_maxop_gap",
    }
    return best["pack"], diag


def rank_enrichment(
    xyz: np.ndarray,
    pack: dict[str, Any],
    *,
    n_decoys: int,
    n_seeds: int,
    soft_T: float = SOFT_T,
    noise: float = 0.45,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Multi-seed native-vs-decoy enrichment under a fixed Crit mold."""
    templates = pack["templates"]
    native = float(
        score_geometry_vs_crit(xyz, templates, soft_T=soft_T)["mean_dist"]
    )
    enrichments = []
    ranks = []
    tops = []
    for _ in range(max(1, n_seeds)):
        sub = np.random.default_rng(int(rng.integers(0, 2**31 - 1)))
        n_soft = max(n_decoys // 2, 1)
        n_hard = n_decoys - n_soft
        decoys = make_ca_decoys(xyz, n_soft, sub, noise=noise)
        decoys += make_ca_decoys(xyz, n_hard, sub, noise=noise * 1.8)
        scores = [
            float(score_geometry_vs_crit(d, templates, soft_T=soft_T)["mean_dist"])
            for d in decoys
        ]
        worse = sum(1 for s in scores if s > native)
        rank = 1 + sum(1 for s in scores if s < native)
        n_tot = n_decoys + 1
        enrichments.append(worse / max(n_decoys, 1))
        ranks.append(rank)
        tops.append(rank <= max(1, int(0.2 * n_tot)))
    return {
        "native_dist": native,
        "enrichment": float(np.mean(enrichments)),
        "enrichment_std": float(np.std(enrichments)) if len(enrichments) > 1 else 0.0,
        "native_rank": float(np.mean(ranks)),
        "top20": bool(np.mean(tops) >= 0.5),
        "n_seeds": n_seeds,
        "n_decoys": n_decoys,
    }


def substrate_projection_table(
    knobs: dict[str, Any],
    pdb_ids: list[str],
    *,
    kinds: tuple[str, ...] = ("zeta", "arith", "gue", "poisson", "scramble"),
    n_decoys: int = 24,
    n_seeds: int = 2,
    n_zeros: int = 14,
    soft_T: float = SOFT_T,
    rng_seed: int = 17,
) -> dict[str, Any]:
    """Equal mold-bank budget ranking table across substrates.

    Reports projection enrichment only. Does **not** claim ζ preference
    (knobs may be ζ-seating defaults — stated in note).
    """
    rng = np.random.default_rng(rng_seed)
    rows: list[dict[str, Any]] = []
    by_kind: dict[str, list[float]] = {k: [] for k in kinds}

    for pid in pdb_ids:
        path = fetch_pdb(pid)
        xyz, chain = load_ca_cyclic_band(path, lo=6, hi=40)
        entry: dict[str, Any] = {
            "pdb": pid,
            "n_ca": int(xyz.shape[0]),
            "chain": chain,
            "substrates": {},
        }
        for kind in kinds:
            pack, diag = select_mold_for_substrate(
                xyz,
                knobs,
                kind=kind,
                n_zeros=n_zeros,
                soft_T=soft_T,
                rng=rng,
            )
            enr = rank_enrichment(
                xyz,
                pack,
                n_decoys=n_decoys,
                n_seeds=n_seeds,
                soft_T=soft_T,
                rng=rng,
            )
            aqft = aqft_dual_report(pack["operator"])
            entry["substrates"][kind] = {
                **enr,
                "mold": diag,
                "aqft_net": aqft["net"],
            }
            by_kind[kind].append(float(enr["enrichment"]))
        rows.append(entry)

    summary = {
        k: {
            "mean_enrichment": float(np.mean(v)) if v else 0.0,
            "std": float(np.std(v)) if len(v) > 1 else 0.0,
            "n": len(v),
        }
        for k, v in by_kind.items()
    }
    return {
        "rows": rows,
        "summary": summary,
        "config": {
            "kinds": list(kinds),
            "pdb_ids": list(pdb_ids),
            "n_decoys": n_decoys,
            "n_seeds": n_seeds,
            "n_zeros": n_zeros,
            "soft_T": soft_T,
            "omega_scales": list(DENSE_OMEGA),
            "equal_budget": "mold_bank_cells_per_substrate",
        },
        "note": (
            "Equal mold-selection budget per substrate. Knobs may be "
            "ζ-seating defaults — not equal-budget knob refit. "
            "No ζ-preference claim."
        ),
        "ontology": ontology_note(),
    }


def fold_one_structure(
    pdb_id: str,
    knobs: dict[str, Any],
    *,
    n_decoys: int = 40,
    n_seeds: int = 3,
    n_zeros: int = 14,
    soft_T: float = SOFT_T,
    rng: np.random.Generator | None = None,
) -> dict[str, Any]:
    """Full fold protocol elements for one RCSB cyclic structure (ζ substrate)."""
    rng = rng or np.random.default_rng(0)
    path = fetch_pdb(pdb_id)
    xyz, chain = load_ca_cyclic_band(path, lo=6, hi=40)
    n_ca = int(xyz.shape[0])
    N = max(n_ca, 7)
    n_sec = sectors_for_ca_length(n_ca, mode="adaptive")

    # CTS-lite: substrate ζ forge + Crit filtration
    der = Keymaker(N=N, n_zeros=n_zeros, n_sectors=n_sec).forge(**knobs)
    filt = crit_action_filtration(der.action)

    pack, mold_diag = select_mold_for_substrate(
        xyz,
        knobs,
        kind="zeta",
        n_zeros=n_zeros,
        soft_T=soft_T,
        rng=rng,
    )
    enr = rank_enrichment(
        xyz, pack, n_decoys=n_decoys, n_seeds=n_seeds, soft_T=soft_T, rng=rng
    )
    aqft = aqft_dual_report(pack["operator"])

    return {
        "pdb": pdb_id,
        "n_ca": n_ca,
        "chain": chain,
        "N_scaffold": N,
        "n_sectors": n_sec,
        "crit_filtration": {
            "n_persistent": filt.get("n_persistent"),
            "max_persistence": filt.get("max_persistence"),
            "n_essential": filt.get("n_essential"),
        },
        "mold": mold_diag,
        "ranking": enr,
        "aqft_dual": aqft,
        "witten_morse": {
            "potential": "SpectralAction_S_Lambda",
            "critical_set": "Crit(S)→sector holonomies",
            "note": "Morse-type selection of preferred monodromies; not SUSY QFT proof",
        },
        "sheaf": {
            "operator": "L=delta*delta connection Laplacian",
            "backend": "MaxOp CellularSheaf or numpy",
            "fiber": "R^d stalks with SO(2) monodromy on cut edge",
        },
        "ontology": ontology_note(),
    }
