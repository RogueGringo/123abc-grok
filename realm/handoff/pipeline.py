"""Production dual-gate → multi-level handoff export.

Bridges locked LengthPolicy / self_fit_dense ranking into openable CA+bb PDBs
with ontology REMARKs. Does **not** change dual-gate production numbers.

Ontology: ζ substrate → Crit projection molds; never λ=γ.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from realm.handoff.decorate import select_adapter
from realm.handoff.generate import generate_structure_ensemble, merge_and_rank
from realm.handoff.physics import get_physics_adapter
from realm.handoff.types import BackboneArtifact, DecorateRequest, MoldRecord
from realm.validate.length_policy import PRODUCTION_RANK, policy_for
from realm.validate.pdb_write import write_mold_pair

logger = logging.getLogger(__name__)


def policy_stamp(n_ca: int, *, base_beta: float = 0.20) -> dict[str, Any]:
    """Snapshot of dual-gate levers for index.json (read-only)."""
    pol = policy_for(int(n_ca), base_beta=float(base_beta), sectors_mode="adaptive")
    return {
        "length_policy": pol.to_dict(),
        "production_rank": dict(PRODUCTION_RANK),
        "ontology": "dual_gate_production_stamp_not_lambda_eq_gamma",
        "note": "soft_T/defect_beta/face/seq from policy_for — not overridden for export",
    }


def export_structure_handoff(
    pdb_id: str,
    knobs: dict[str, Any],
    *,
    out_dir: Path | str,
    top_k: int = 6,
    n_zeros: int = 14,
    include_coutsias: bool = False,
    decorate: str = "null",
    physics: str = "geometry",
    defect_beta: float = 0.20,
) -> dict[str, Any]:
    """Rank native structure under dual-gate policy and write multi-level PDBs.

    Uses production ``policy_for`` soft_T (via generate_structure_ensemble soft_T=None).
    """
    out = Path(out_dir)
    molds_dir = out / "molds"
    molds_dir.mkdir(parents=True, exist_ok=True)

    molds = generate_structure_ensemble(
        pdb_id,
        knobs,
        n_zeros=int(n_zeros),
        top_k=int(top_k),
        include_coutsias=bool(include_coutsias),
        soft_T=None,  # production LengthPolicy
        defect_beta=float(defect_beta),
    )
    if not molds:
        return {
            "pdb": pdb_id.upper(),
            "status": "EMPTY",
            "n_molds": 0,
            "out_dir": str(out),
        }

    n_ca = int((molds[0].meta or {}).get("n_ca_native") or molds[0].N)
    stamp = policy_stamp(n_ca, base_beta=float(defect_beta))

    decorate_ad = select_adapter(decorate)
    physics_ad = get_physics_adapter(physics)

    index_molds: list[dict[str, Any]] = []
    for i, m in enumerate(molds):
        stem = f"{i:03d}_{m.source}"
        paths = write_mold_pair(
            molds_dir,
            stem,
            m.xyz,
            source=m.source,
            rank_score=m.rank_score,
            method=m.method,
            twist=m.twist,
            maxop_gap=m.maxop_gap,
        )
        art = BackboneArtifact(
            path_ca=Path(paths["path_ca"]),
            path_bb=Path(paths["path_bb"]),
            meta=dict(m.meta or {}),
        )
        dec = decorate_ad.decorate(DecorateRequest(backbone=art, poly_ala=True))
        phys_report = None
        if physics_ad is not None:
            phys = physics_ad.filter(art.path_bb)
            phys_dir = out / "physics"
            phys_dir.mkdir(parents=True, exist_ok=True)
            (phys_dir / f"{stem}.json").write_text(
                json.dumps(phys.to_dict(), indent=2), encoding="utf-8"
            )
            phys_report = phys.to_dict()
        # REMARK ontology already in PDB via write_mold_pair / build_remarks
        ca_text = Path(paths["path_ca"]).read_text(encoding="utf-8")
        index_molds.append(
            {
                "stem": stem,
                "source": m.source,
                "N": m.N,
                "rank_score": m.rank_score,
                "method": m.method,
                "path_ca": paths["path_ca"],
                "path_bb": paths["path_bb"],
                "path_decorated": str(dec.path_decorated) if dec.path_decorated else None,
                "decorate_status": dec.status,
                "physics": phys_report,
                "ontology_remark_ok": "not_lambda_eq_gamma" in ca_text,
            }
        )

    index = {
        "pdb": pdb_id.upper(),
        "status": "OK",
        "n_molds": len(index_molds),
        "molds": index_molds,
        "dual_gate": stamp,
        "out_dir": str(out.resolve()),
        "ontology": "handoff_dual_gate_structure_not_lambda_eq_gamma",
        "note": (
            "Production LengthPolicy self_fit_dense pack; Kabsch rank at policy soft_T. "
            "Export-only — ranking table numbers not modified."
        ),
    }
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "dual-gate handoff %s: %d molds soft_T=%s → %s",
        pdb_id,
        len(index_molds),
        stamp["length_policy"].get("soft_T"),
        out,
    )
    return index


def export_structure_batch(
    pdb_ids: list[str],
    knobs: dict[str, Any],
    *,
    out_root: Path | str,
    top_k: int = 4,
    **kwargs: Any,
) -> dict[str, Any]:
    """Export dual-gate handoff for each PDB id under out_root/<PDB>/."""
    root = Path(out_root)
    rows = []
    for pid in pdb_ids:
        pid = str(pid).strip().upper()
        if not pid:
            continue
        sub = root / pid
        try:
            row = export_structure_handoff(pid, knobs, out_dir=sub, top_k=top_k, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("handoff failed for %s", pid)
            row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
        rows.append(row)
    summary = {
        "n_ids": len(rows),
        "n_ok": sum(1 for r in rows if r.get("status") == "OK"),
        "rows": rows,
        "ontology": "handoff_dual_gate_batch_not_lambda_eq_gamma",
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "batch_index.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary
