"""Production dual-gate → multi-level handoff export.

Bridges locked LengthPolicy / self_fit_dense ranking into openable CA+bb PDBs
with ontology REMARKs, commercial manifest, and optional enrichment stamp.

Does **not** change dual-gate production numbers.
Ontology: ζ substrate → Crit projection molds; never λ=γ.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from realm.handoff.decorate import select_adapter
from realm.handoff.generate import generate_structure_ensemble
from realm.handoff.physics import get_physics_adapter, write_physics_rollup
from realm.handoff.types import BackboneArtifact, DecorateRequest
from realm.validate.length_policy import PRODUCTION_RANK, policy_for
from realm.validate.pdb_write import write_mold_pair

logger = logging.getLogger(__name__)

def _load_campaign_ids() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Single source of truth: prefer pdb_batch lists when importable."""
    try:
        from pdb_batch import DEFAULT_CYCLIC_IDS, HOLDOUT_IDS, PROBE_IDS

        return (
            tuple(DEFAULT_CYCLIC_IDS),
            tuple(PROBE_IDS),
            tuple(HOLDOUT_IDS),
        )
    except Exception:  # noqa: BLE001
        default = (
            "1CSA",
            "1IKF",
            "2X2C",
            "4M6E",
            "3WNE",
            "4K8Y",
            "1JBL",
            "5EOC",
            "3AVB",
            "3AV9",
            "5LSO",
            "1TET",
        )
        probe = ("1CSA", "2X2C", "4M6E", "3WNE")
        hold = tuple(x for x in default if x not in probe)
        return default, probe, hold


DEFAULT_HANDOFF_IDS, PROBE_HANDOFF_IDS, HOLDOUT_HANDOFF_IDS = _load_campaign_ids()


def policy_stamp(n_ca: int, *, base_beta: float = 0.20) -> dict[str, Any]:
    """Snapshot of dual-gate levers for index.json (read-only)."""
    pol = policy_for(int(n_ca), base_beta=float(base_beta), sectors_mode="adaptive")
    return {
        "length_policy": pol.to_dict(),
        "production_rank": dict(PRODUCTION_RANK),
        "ontology": "dual_gate_production_stamp_not_lambda_eq_gamma",
        "note": "soft_T/defect_beta/face/seq from policy_for — not overridden for export",
    }


def biopython_open_check(path: Path | str) -> dict[str, Any]:
    """Try opening a PDB with BioPython if installed (optional commercial metric)."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "path": str(p), "error": "missing_file", "engine": None}
    try:
        from Bio.PDB import PDBParser  # type: ignore[import-untyped]
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": None,
            "path": str(p),
            "error": f"biopython_unavailable: {exc}",
            "engine": None,
        }
    try:
        parser = PDBParser(QUIET=True)
        struct = parser.get_structure("m", str(p))
        n_atoms = sum(1 for _ in struct.get_atoms())
        return {
            "ok": True,
            "path": str(p),
            "n_atoms": int(n_atoms),
            "engine": "Bio.PDB.PDBParser",
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "path": str(p),
            "error": str(exc),
            "engine": "Bio.PDB.PDBParser",
        }


def enrichment_stamp(
    pdb_id: str,
    knobs: dict[str, Any],
    *,
    n_zeros: int = 14,
    n_decoys: int = 24,
    n_seeds: int = 1,
    seed: int = 0,
) -> dict[str, Any]:
    """Read-only dual-gate rank_one metrics (does not alter LengthPolicy)."""
    from pdb_batch import rank_one

    # Production kwargs from single table; rank_one may length-adapt further.
    pr = dict(PRODUCTION_RANK)
    row = rank_one(
        pdb_id.upper(),
        knobs,
        n_decoys=int(n_decoys),
        n_zeros=int(n_zeros),
        n_sectors=6,
        noise=0.45,
        rng=np.random.default_rng(int(seed)),
        n_seeds=int(n_seeds),
        alpha_proj=float(pr["alpha_proj"]),
        soft_T=float(pr["soft_T"]),
        aggregate=str(pr["aggregate"]),
        sectors_mode=str(pr["sectors_mode"]),
        multimode_mode=str(pr["multimode_mode"]),
        defect_beta=float(pr["defect_beta"]),
        holonomy_polish=bool(pr["holonomy_polish"]),
        coutsias_alpha=float(pr["coutsias_alpha"]),
    )
    # slim: drop heavy operator banks
    slim = {
        k: row[k]
        for k in (
            "pdb",
            "status",
            "n_ca",
            "chain",
            "enrichment",
            "enrichment_std",
            "top20",
            "native_rank",
            "native_dist",
            "method",
            "soft_T",
            "soft_T_effective",
            "defect_beta",
            "defect_beta_effective",
            "n_sectors_used",
            "sectors_mode",
            "multimode_mode",
        )
        if k in row
    }
    slim["read_only"] = True
    slim["ontology"] = "enrichment_stamp_not_lambda_eq_gamma"
    return slim


def write_manifest_tsv(
    index: dict[str, Any],
    path: Path | str,
) -> Path:
    """Commercial manifest: one row per mold file pair."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "pdb",
        "stem",
        "source",
        "N",
        "rank_score",
        "method",
        "path_ca",
        "path_bb",
        "path_decorated",
        "soft_T",
        "ontology_remark_ok",
        "biopython_ca_ok",
        "biopython_bb_ok",
    ]
    soft_T = None
    try:
        soft_T = index.get("dual_gate", {}).get("length_policy", {}).get("soft_T")
    except Exception:  # noqa: BLE001
        soft_T = None
    rows = index.get("molds") or []
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        for m in rows:
            bio = m.get("biopython") or {}
            w.writerow(
                {
                    "pdb": index.get("pdb"),
                    "stem": m.get("stem"),
                    "source": m.get("source"),
                    "N": m.get("N"),
                    "rank_score": m.get("rank_score"),
                    "method": m.get("method"),
                    "path_ca": m.get("path_ca"),
                    "path_bb": m.get("path_bb"),
                    "path_decorated": m.get("path_decorated") or "",
                    "soft_T": soft_T,
                    "ontology_remark_ok": m.get("ontology_remark_ok"),
                    "biopython_ca_ok": (bio.get("ca") or {}).get("ok"),
                    "biopython_bb_ok": (bio.get("bb") or {}).get("ok"),
                }
            )
    return dest


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
    with_enrichment: bool = False,
    with_biopython_check: bool = True,
    n_decoys: int = 24,
    n_seeds: int = 1,
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
    n_bio_ok = 0
    n_bio_checked = 0
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
            phys_report["stem"] = stem
            phys_report["pdb"] = pdb_id.upper()
        ca_text = Path(paths["path_ca"]).read_text(encoding="utf-8")
        bio: dict[str, Any] = {}
        if with_biopython_check:
            bio["ca"] = biopython_open_check(paths["path_ca"])
            bio["bb"] = biopython_open_check(paths["path_bb"])
            for side in ("ca", "bb"):
                if bio[side].get("ok") is not None:
                    n_bio_checked += 1
                if bio[side].get("ok") is True:
                    n_bio_ok += 1
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
                "biopython": bio or None,
            }
        )

    enrich = None
    if with_enrichment:
        try:
            enrich = enrichment_stamp(
                pdb_id, knobs, n_zeros=int(n_zeros), n_decoys=int(n_decoys), n_seeds=int(n_seeds)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("enrichment_stamp failed for %s: %s", pdb_id, exc)
            enrich = {"status": "ERROR", "error": str(exc), "read_only": True}

    phys_reports = [
        dict(m["physics"])
        for m in index_molds
        if m.get("physics")
    ]
    physics_rollup = None
    if phys_reports:
        try:
            pr_path = write_physics_rollup(
                phys_reports, out / "PHYSICS_ROLLUP.json", scope=pdb_id.upper()
            )
            physics_rollup = json.loads(pr_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("physics rollup failed for %s: %s", pdb_id, exc)

    index: dict[str, Any] = {
        "pdb": pdb_id.upper(),
        "status": "OK",
        "n_molds": len(index_molds),
        "molds": index_molds,
        "dual_gate": stamp,
        "enrichment": enrich,
        "physics_rollup": physics_rollup,
        "biopython_summary": {
            "n_checked": n_bio_checked,
            "n_ok": n_bio_ok,
            "all_ok": bool(n_bio_checked > 0 and n_bio_ok == n_bio_checked),
            "skipped": n_bio_checked == 0 and with_biopython_check,
        },
        "out_dir": str(out.resolve()),
        "ontology": "handoff_dual_gate_structure_not_lambda_eq_gamma",
        "note": (
            "Production LengthPolicy self_fit_dense pack; Kabsch rank at policy soft_T. "
            "Export-only — ranking table numbers not modified."
        ),
    }
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    write_manifest_tsv(index, out / "manifest.tsv")
    logger.info(
        "dual-gate handoff %s: %d molds soft_T=%s bio_ok=%s/%s → %s",
        pdb_id,
        len(index_molds),
        stamp["length_policy"].get("soft_T"),
        n_bio_ok,
        n_bio_checked,
        out,
    )
    return index


def write_enrichment_summary_tsv(rows: list[dict[str, Any]], path: Path | str) -> Path:
    """One row per PDB: enrichment / top20 / soft_T / mold counts (commercial table)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "pdb",
        "status",
        "n_molds",
        "soft_T",
        "n_ca",
        "enrichment",
        "enrichment_std",
        "top20",
        "native_rank",
        "native_dist",
        "method",
        "set",
        "error",
    ]
    probe = set(PROBE_HANDOFF_IDS)
    hold = set(HOLDOUT_HANDOFF_IDS)
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        for r in rows:
            en = r.get("enrichment") or {}
            pid = str(r.get("pdb") or "")
            if pid in probe:
                which = "probe"
            elif pid in hold:
                which = "holdout"
            else:
                which = ""
            w.writerow(
                {
                    "pdb": pid,
                    "status": r.get("status"),
                    "n_molds": r.get("n_molds"),
                    "soft_T": (r.get("dual_gate") or {}).get("length_policy", {}).get(
                        "soft_T"
                    ),
                    "n_ca": en.get("n_ca"),
                    "enrichment": en.get("enrichment"),
                    "enrichment_std": en.get("enrichment_std"),
                    "top20": en.get("top20"),
                    "native_rank": en.get("native_rank"),
                    "native_dist": en.get("native_dist"),
                    "method": en.get("method"),
                    "set": which,
                    "error": r.get("error") or en.get("error") or "",
                }
            )
    return dest


def resolve_pdb_id_list(spec: str | None) -> list[str]:
    """Parse --pdb-ids: comma list, or tokens default|probe|holdout|all."""
    if not spec or not str(spec).strip():
        return []
    tokens = [t.strip().lower() for t in str(spec).replace(";", ",").split(",") if t.strip()]
    out: list[str] = []
    for t in tokens:
        if t in ("default", "all", "campaign"):
            out.extend(DEFAULT_HANDOFF_IDS)
        elif t == "probe":
            out.extend(PROBE_HANDOFF_IDS)
        elif t in ("holdout", "hold"):
            out.extend(HOLDOUT_HANDOFF_IDS)
        else:
            out.append(t.upper())
    # stable unique
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _existing_ok_index(sub: Path) -> dict[str, Any] | None:
    """Load prior OK export if present (resume)."""
    idx = sub / "index.json"
    if not idx.is_file():
        return None
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if data.get("status") != "OK" or not data.get("molds"):
        return None
    return data


def export_structure_batch(
    pdb_ids: list[str],
    knobs: dict[str, Any],
    *,
    out_root: Path | str,
    top_k: int = 4,
    resume: bool = False,
    dry_run: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Export dual-gate handoff for each PDB id under out_root/<PDB>/ + root manifest.

    resume: skip IDs that already have a successful index.json.
    dry_run: resolve IDs and policy pins only — no forge/export.
    """
    root = Path(out_root)
    rows = []
    n_skipped = 0
    if dry_run:
        from realm.validate.length_policy import policy_for as _pf

        pin = {
            "soft_T_n12": float(_pf(12, base_beta=0.20).soft_T),
            "seq_mix": float(_pf(12, base_beta=0.20).seq_mix),
            "face_weight": float(_pf(12, base_beta=0.20).face_weight),
        }
        return {
            "n_ids": len(pdb_ids),
            "n_ok": 0,
            "n_skipped": 0,
            "dry_run": True,
            "ids": [str(p).strip().upper() for p in pdb_ids if str(p).strip()],
            "dual_gate_pin": pin,
            "rows": [],
            "ontology": "handoff_dual_gate_batch_dry_run_not_lambda_eq_gamma",
        }

    for pid in pdb_ids:
        pid = str(pid).strip().upper()
        if not pid:
            continue
        sub = root / pid
        if resume:
            prior = _existing_ok_index(sub)
            if prior is not None:
                logger.info("resume skip %s (existing OK export)", pid)
                rows.append(prior)
                n_skipped += 1
                continue
        try:
            row = export_structure_handoff(pid, knobs, out_dir=sub, top_k=top_k, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("handoff failed for %s", pid)
            row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
        rows.append(row)

    # Flatten commercial root manifest
    root.mkdir(parents=True, exist_ok=True)
    flat_fields = [
        "pdb",
        "status",
        "stem",
        "source",
        "N",
        "rank_score",
        "method",
        "path_ca",
        "path_bb",
        "soft_T",
        "enrichment",
        "top20",
        "ontology_remark_ok",
    ]
    with (root / "manifest.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flat_fields, delimiter="\t")
        w.writeheader()
        for row in rows:
            if row.get("status") != "OK":
                w.writerow(
                    {
                        "pdb": row.get("pdb"),
                        "status": row.get("status"),
                        "stem": "",
                        "source": "",
                        "N": "",
                        "rank_score": "",
                        "method": "",
                        "path_ca": "",
                        "path_bb": "",
                        "soft_T": "",
                        "enrichment": "",
                        "top20": "",
                        "ontology_remark_ok": "",
                    }
                )
                continue
            soft_T = (row.get("dual_gate") or {}).get("length_policy", {}).get("soft_T")
            enr = (row.get("enrichment") or {}).get("enrichment")
            top20 = (row.get("enrichment") or {}).get("top20")
            for m in row.get("molds") or []:
                w.writerow(
                    {
                        "pdb": row.get("pdb"),
                        "status": "OK",
                        "stem": m.get("stem"),
                        "source": m.get("source"),
                        "N": m.get("N"),
                        "rank_score": m.get("rank_score"),
                        "method": m.get("method"),
                        "path_ca": m.get("path_ca"),
                        "path_bb": m.get("path_bb"),
                        "soft_T": soft_T,
                        "enrichment": enr,
                        "top20": top20,
                        "ontology_remark_ok": m.get("ontology_remark_ok"),
                    }
                )

    enr_path = write_enrichment_summary_tsv(rows, root / "enrichment_summary.tsv")

    ok_rows = [r for r in rows if r.get("status") == "OK"]
    enrs = [
        float((r.get("enrichment") or {}).get("enrichment"))
        for r in ok_rows
        if (r.get("enrichment") or {}).get("enrichment") is not None
    ]
    top20_n = sum(
        1
        for r in ok_rows
        if (r.get("enrichment") or {}).get("top20") is True
    )

    summary = {
        "n_ids": len(rows),
        "n_ok": sum(1 for r in rows if r.get("status") == "OK"),
        "n_skipped_resume": int(n_skipped),
        "rows": [
            {
                "pdb": r.get("pdb"),
                "status": r.get("status"),
                "n_molds": r.get("n_molds"),
                "soft_T": (r.get("dual_gate") or {}).get("length_policy", {}).get("soft_T"),
                "enrichment": (r.get("enrichment") or {}).get("enrichment"),
                "top20": (r.get("enrichment") or {}).get("top20"),
                "error": r.get("error"),
            }
            for r in rows
        ],
        "enrichment_aggregate": {
            "n_with_enrichment": len(enrs),
            "mean_enrichment": float(sum(enrs) / len(enrs)) if enrs else None,
            "top20_count": int(top20_n),
        },
        "manifest": str((root / "manifest.tsv").resolve()),
        "enrichment_summary": str(enr_path.resolve()),
        "ontology": "handoff_dual_gate_batch_not_lambda_eq_gamma",
    }
    (root / "batch_index.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    write_partner_summary_md(summary, root / "SUMMARY.md")
    return summary


def write_partner_summary_md(summary: dict[str, Any], path: Path | str) -> Path:
    """Human-readable campaign summary for partners / internal release notes."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    agg = summary.get("enrichment_aggregate") or {}
    lines = [
        "# Dual-gate handoff campaign summary",
        "",
        f"- Structures OK: **{summary.get('n_ok')}** / {summary.get('n_ids')}",
        f"- Resume skips: {summary.get('n_skipped_resume', 0)}",
        f"- Mean enrichment (if stamped): {agg.get('mean_enrichment')}",
        f"- top20 count (if stamped): {agg.get('top20_count')}",
        f"- Manifest: `{summary.get('manifest')}`",
        f"- Enrichment table: `{summary.get('enrichment_summary')}`",
        "",
        "Ontology: Crit projection molds only -- **not** lambda=gamma.",
        "LengthPolicy production pins were not modified by this export.",
        "",
        "| PDB | status | n_molds | soft_T | enrichment | top20 |",
        "|-----|--------|---------|--------|------------|-------|",
    ]
    for r in summary.get("rows") or []:
        lines.append(
            f"| {r.get('pdb')} | {r.get('status')} | {r.get('n_molds')} | "
            f"{r.get('soft_T')} | {r.get('enrichment')} | {r.get('top20')} |"
        )
    lines.append("")
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest
