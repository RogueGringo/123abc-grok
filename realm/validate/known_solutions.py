"""Known-solutions report: dual-gate rank_one on public natives + Kabsch subset.

Produces internal ledger + thin partner science annex.
Report-only: weak enrichment does not fail; pin failure does.
Never retunes LengthPolicy. Never λ=γ.
"""

from __future__ import annotations

import csv
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from realm.handoff.verify import verify_dual_gate_pin
from realm.validate.known_solutions_ids import resolve_universe
from realm.validate.length_policy import PRODUCTION_RANK
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger(__name__)

_SLIM_RANK_KEYS = (
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
    "n_seeds",
    "decoy_mode",
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slim_rank_row(row: dict[str, Any], *, tag: str, source: str) -> dict[str, Any]:
    slim = {k: row[k] for k in _SLIM_RANK_KEYS if k in row}
    slim["tag"] = tag
    slim["source"] = source
    slim["read_only"] = True
    slim["ontology"] = "known_solutions_rank_not_lambda_eq_gamma"
    if row.get("status") != "OK" and "note" in row:
        slim["note"] = row["note"]
    if "error" in row:
        slim["error"] = row["error"]
    return slim


def run_rank_one(
    pdb_id: str,
    knobs: dict[str, Any],
    *,
    n_decoys: int,
    n_seeds: int,
    n_zeros: int = 14,
    seed: int = 0,
    noise: float = 0.45,
    decoy_mode: str = "soft",
) -> dict[str, Any]:
    """Production dual-gate rank_one (no pin retune)."""
    from pdb_batch import rank_one

    pr = dict(PRODUCTION_RANK)
    try:
        row = rank_one(
            pdb_id.upper(),
            knobs,
            n_decoys=int(n_decoys),
            n_zeros=int(n_zeros),
            n_sectors=6,
            noise=float(noise),
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
            decoy_mode=str(decoy_mode or "soft"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("rank_one failed for %s", pdb_id)
        return {
            "pdb": pdb_id.upper(),
            "status": "ERROR_RANK",
            "error": str(exc),
        }
    return row


def run_kabsch_subset(
    pdb_id: str,
    knobs: dict[str, Any],
    *,
    top_k: int = 8,
    n_zeros: int = 14,
    defect_beta: float = 0.20,
) -> dict[str, Any]:
    """Structure-mode Kabsch softmin vs native (scores only by default)."""
    from realm.handoff.generate import generate_structure_ensemble

    try:
        molds = generate_structure_ensemble(
            pdb_id.upper(),
            knobs,
            n_zeros=int(n_zeros),
            top_k=int(top_k),
            include_coutsias=True,
            soft_T=None,
            defect_beta=float(defect_beta),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("kabsch subset failed for %s: %s", pdb_id, exc)
        return {
            "pdb": pdb_id.upper(),
            "status": "ERROR_KABSCH",
            "error": str(exc),
        }
    if not molds:
        return {
            "pdb": pdb_id.upper(),
            "status": "EMPTY_MOLDS",
            "n_molds": 0,
        }
    scores = [float(m.rank_score) for m in molds]
    best = min(scores)
    n_ca = None
    if molds[0].meta:
        n_ca = molds[0].meta.get("n_ca_native")
    return {
        "pdb": pdb_id.upper(),
        "status": "OK",
        "n_molds": len(molds),
        "best_rank_score": best,
        "mean_rank_score": float(np.mean(scores)),
        "n_ca": n_ca,
        "method": "structure_kabsch_softmin",
        "ontology": "known_solutions_kabsch_not_lambda_eq_gamma",
    }


def _seeds_for_tag(tag: str, n_seeds: int, full_seeds: bool) -> int:
    if full_seeds:
        return max(1, int(n_seeds))
    if tag in ("curated_probe", "curated_holdout"):
        return max(1, int(n_seeds))
    return 1


def _kabsch_candidate_ids(
    universe: list[dict[str, Any]],
    *,
    kabsch_set: str,
    kabsch_max: int,
) -> list[str]:
    mode = (kabsch_set or "curated").lower().strip()
    if mode == "none":
        return []
    if mode == "probe":
        tags = {"curated_probe"}
    elif mode == "holdout":
        tags = {"curated_holdout"}
    elif mode == "all":
        tags = None
    else:  # curated
        tags = {"curated_probe", "curated_holdout"}
    out: list[str] = []
    for e in universe:
        if tags is not None and e["tag"] not in tags:
            continue
        out.append(e["id"])
        if len(out) >= max(0, int(kabsch_max)):
            break
    return out


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-tag and all_ok enrichment aggregates (no dilution of holdout)."""
    by_tag: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("status") != "OK" or "enrichment" not in r:
            continue
        tag = str(r.get("tag") or "unknown")
        by_tag.setdefault(tag, []).append(r)

    def _agg(group: list[dict[str, Any]]) -> dict[str, Any]:
        if not group:
            return {"n": 0}
        enr = [float(x["enrichment"]) for x in group]
        ranks = [float(x["native_rank"]) for x in group if "native_rank" in x]
        top20 = [1.0 if x.get("top20") else 0.0 for x in group]
        return {
            "n": len(group),
            "mean_enrichment": float(np.mean(enr)),
            "mean_enrichment_std": float(np.mean([float(x.get("enrichment_std") or 0.0) for x in group])),
            "top20_rate": float(np.mean(top20)),
            "mean_native_rank": float(np.mean(ranks)) if ranks else None,
        }

    out: dict[str, Any] = {tag: _agg(g) for tag, g in sorted(by_tag.items())}
    all_ok = [r for r in rows if r.get("status") == "OK" and "enrichment" in r]
    out["all_ok"] = _agg(all_ok)
    out["n_attempted"] = len(rows)
    out["n_ok"] = len(all_ok)
    out["n_fail"] = len(rows) - len(all_ok)
    return out


def aggregate_kabsch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("status") == "OK" and "best_rank_score" in r]
    if not ok:
        return {"n_kabsch_ok": 0, "n_attempted": len(rows)}
    scores = [float(r["best_rank_score"]) for r in ok]
    return {
        "n_kabsch_ok": len(ok),
        "n_attempted": len(rows),
        "mean_best_rank_score": float(np.mean(scores)),
        "min_best_rank_score": float(min(scores)),
        "max_best_rank_score": float(max(scores)),
    }


def write_internal_md(report: dict[str, Any], path: Path) -> Path:
    pin = report.get("pin") or {}
    agg = report.get("aggregates") or {}
    lines = [
        "# Known solutions report (internal)",
        "",
        f"- stamp: `{report.get('stamp')}`",
        f"- ontology: `{report.get('ontology')}`",
        f"- dual-gate pin ok: **{pin.get('ok')}** soft_T(n=12)={pin.get('soft_T')} (expect 0.036)",
        f"- seq_mix={pin.get('seq_mix')} face_weight={pin.get('face_weight')}",
        "",
        "## Aggregates (OK rows only)",
        "",
    ]
    for key in (
        "curated_probe",
        "curated_holdout",
        "rcsb_expand",
        "cpsea2_demo",
        "cli_override",
        "all_ok",
    ):
        block = agg.get(key)
        if not block or not block.get("n"):
            continue
        lines.append(
            f"- **{key}**: n={block['n']} mean_enrichment={block.get('mean_enrichment', 0):.1%} "
            f"top20_rate={block.get('top20_rate', 0):.1%} "
            f"mean_rank={block.get('mean_native_rank')}"
        )
    lines.extend(
        [
            "",
            f"- attempted={agg.get('n_attempted')} ok={agg.get('n_ok')} fail={agg.get('n_fail')}",
            "",
            "## Kabsch subset",
            "",
        ]
    )
    kagg = report.get("kabsch_aggregates") or {}
    lines.append(
        f"- n_ok={kagg.get('n_kabsch_ok', 0)} / attempted={kagg.get('n_attempted', 0)} "
        f"mean_best_rank_score={kagg.get('mean_best_rank_score')}"
    )
    lines.extend(
        [
            "",
            "## Note",
            "",
            "- Report-only: weak enrichment does **not** fail this report.",
            "- Commercial success remains openable PDBs + dual-gate pin (not enrichment).",
            "- Never λ=γ.",
            "",
        ]
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def attach_report_to_dir(
    report_dir: Path | str,
    dest_dir: Path | str,
    *,
    include_full_ledger: bool = True,
) -> dict[str, Any]:
    """Copy science annex (+ optional full ledger) into a commercial out dir.

    Does not change ACCEPTANCE/SHIP success. Report-only science evidence.
    """
    src = Path(report_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    # Resolve LATEST pointer file if given a parent with LATEST
    if (src / "PARTNER_SCIENCE_ANNEX.json").is_file():
        root = src
    elif src.is_file() and src.name == "LATEST":
        root = Path(src.read_text(encoding="utf-8").strip())
    elif (src / "LATEST").is_file():
        root = Path((src / "LATEST").read_text(encoding="utf-8").strip())
    else:
        root = src

    copied: list[str] = []
    missing: list[str] = []
    names = [
        "PARTNER_SCIENCE_ANNEX.json",
        "PARTNER_SCIENCE_ANNEX.md",
        "pin.json",
        # multi-mode compare (optional; present when --compare-modes used)
        "DECOY_MODE_COMPARE.json",
        "DECOY_MODE_COMPARE.md",
        "KNOWN_SOLUTIONS_COMPARE.json",
        "PARTNER_SCIENCE_ONEPAGER.pdf",
    ]
    if include_full_ledger:
        names.extend(
            [
                "KNOWN_SOLUTIONS.json",
                "KNOWN_SOLUTIONS.md",
                "summary.tsv",
                "id_universe.json",
            ]
        )
    science_dest = dest / "known_solutions"
    science_dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        sp = root / name
        if not sp.is_file():
            # compare files optional — only note missing for core annex
            if name not in (
                "DECOY_MODE_COMPARE.json",
                "DECOY_MODE_COMPARE.md",
                "KNOWN_SOLUTIONS_COMPARE.json",
                "PARTNER_SCIENCE_ONEPAGER.pdf",
                "KNOWN_SOLUTIONS.json",
                "KNOWN_SOLUTIONS.md",
                "summary.tsv",
                "id_universe.json",
            ):
                missing.append(name)
            continue
        dp = science_dest / name
        shutil.copy2(sp, dp)
        try:
            copied.append(str(dp.relative_to(dest)))
        except ValueError:
            copied.append(str(dp))

    # Also place thin annex (+ compare) at dest root for partner glance
    for name in (
        "PARTNER_SCIENCE_ANNEX.json",
        "PARTNER_SCIENCE_ANNEX.md",
        "DECOY_MODE_COMPARE.json",
        "DECOY_MODE_COMPARE.md",
        "PARTNER_SCIENCE_ONEPAGER.pdf",
    ):
        sp = science_dest / name
        if sp.is_file():
            shutil.copy2(sp, dest / name)
            if name not in copied:
                copied.append(name)

    pin_ok = None
    pin_path = science_dest / "pin.json"
    if pin_path.is_file():
        try:
            pin_ok = json.loads(pin_path.read_text(encoding="utf-8")).get("ok")
        except Exception:  # noqa: BLE001
            pin_ok = None

    has_compare = (science_dest / "DECOY_MODE_COMPARE.json").is_file() or (
        dest / "DECOY_MODE_COMPARE.json"
    ).is_file()
    has_pdf = (science_dest / "PARTNER_SCIENCE_ONEPAGER.pdf").is_file() or (
        dest / "PARTNER_SCIENCE_ONEPAGER.pdf"
    ).is_file()
    annex_ok = (science_dest / "PARTNER_SCIENCE_ANNEX.json").is_file() or (
        dest / "PARTNER_SCIENCE_ANNEX.json"
    ).is_file()
    meta = {
        "ok": annex_ok,
        "source": str(root.resolve()) if root.exists() else str(root),
        "dest": str(dest.resolve()),
        "copied": copied,
        "missing": missing,
        "pin_ok": pin_ok,
        "has_decoy_mode_compare": has_compare,
        "has_science_pdf": has_pdf,
        "ontology": "known_solutions_attach_not_lambda_eq_gamma",
        "note": "Science annex attached for partner glance; not ACCEPTANCE/SHIP gate.",
    }
    write_json(dest / "KNOWN_SOLUTIONS_ATTACH.json", meta)
    return meta


def _write_latest_pointer(out_dir: Path | str, stamp_dir: Path | str) -> None:
    """Windows-friendly LATEST pointer file under out_dir → stamp_dir."""
    latest = Path(out_dir) / "LATEST"
    root = Path(stamp_dir)
    try:
        if latest.is_symlink() or latest.is_file():
            latest.unlink()
        if latest.is_dir() and not any(latest.iterdir()):
            latest.rmdir()
        latest.write_text(str(root.resolve()), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("LATEST pointer: %s", exc)


def update_known_solutions_index(out_dir: Path | str) -> Path:
    """Catalog stamp dirs under out_dir (LATEST pointer + INDEX.json)."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if not child.is_dir():
            continue
        if child.name in ("modes",):
            continue
        pin_p = child / "pin.json"
        annex_p = child / "PARTNER_SCIENCE_ANNEX.json"
        compare_p = child / "DECOY_MODE_COMPARE.json"
        ks_p = child / "KNOWN_SOLUTIONS.json"
        if not (annex_p.is_file() or ks_p.is_file() or compare_p.is_file()):
            continue
        pin_ok = None
        soft_T = None
        if pin_p.is_file():
            try:
                pin = json.loads(pin_p.read_text(encoding="utf-8"))
                pin_ok = pin.get("ok")
                soft_T = pin.get("soft_T")
            except Exception:  # noqa: BLE001
                pass
        kind = "compare" if compare_p.is_file() else "single"
        entries.append(
            {
                "stamp": child.name,
                "path": str(child.resolve()),
                "kind": kind,
                "pin_ok": pin_ok,
                "soft_T": soft_T,
                "has_annex": annex_p.is_file(),
                "has_compare": compare_p.is_file(),
            }
        )
    latest = None
    if (root / "LATEST").is_file():
        try:
            latest = (root / "LATEST").read_text(encoding="utf-8").strip()
        except Exception:  # noqa: BLE001
            latest = None
    idx = {
        "ontology": "known_solutions_index_not_lambda_eq_gamma",
        "n_stamps": len(entries),
        "latest": latest,
        "entries": entries[:50],
        "note": "Catalog of science ledgers; not commercial ACCEPTANCE.",
    }
    dest = root / "INDEX.json"
    write_json(dest, idx)
    return dest


def write_summary_tsv(report: dict[str, Any], path: Path | str) -> Path:
    """One row per ranked ID for ops glance."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "pdb",
        "tag",
        "status",
        "n_ca",
        "enrichment",
        "enrichment_std",
        "top20",
        "native_rank",
        "native_dist",
        "soft_T_effective",
        "method",
        "n_seeds",
    ]
    rows = report.get("rows") or []
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    return dest


def write_partner_annex(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Thin partner-facing science annex (not ACCEPTANCE / not SHIP)."""
    pin = report.get("pin") or {}
    agg = report.get("aggregates") or {}
    kagg = report.get("kabsch_aggregates") or {}
    src = (report.get("id_universe") or {}).get("sources") or {}

    def _mean(tag: str) -> dict[str, Any]:
        b = agg.get(tag) or {}
        return {
            "n": int(b.get("n") or 0),
            "mean_enrichment": b.get("mean_enrichment"),
        }

    annex = {
        "kind": "partner_science_annex",
        "ontology": "partner_science_annex_not_lambda_eq_gamma",
        "stamp": report.get("stamp"),
        "pin": {
            "ok": pin.get("ok"),
            "soft_T": pin.get("soft_T"),
            "expected_soft_T": pin.get("expected_soft_T", 0.036),
            "seq_mix": pin.get("seq_mix"),
            "face_weight": pin.get("face_weight"),
        },
        "counts": {
            "n_attempted": agg.get("n_attempted"),
            "n_ranked_ok": agg.get("n_ok"),
            "n_fail": agg.get("n_fail"),
            "n_universe": (report.get("id_universe") or {}).get("n_total"),
        },
        "mean_enrichment_by_tag": {
            "curated_probe": _mean("curated_probe"),
            "curated_holdout": _mean("curated_holdout"),
            "rcsb_expand": _mean("rcsb_expand"),
            "cpsea2_demo": _mean("cpsea2_demo"),
            "all_ok": _mean("all_ok"),
        },
        "kabsch_subset": {
            "n_ok": kagg.get("n_kabsch_ok", 0),
            "mean_best_rank_score": kagg.get("mean_best_rank_score"),
        },
        "sources": {
            "rcsb_list_status": src.get("rcsb_list_status"),
            "cpsea2_status": (src.get("cpsea2") or {}).get("status"),
            "skip_expand": src.get("skip_expand"),
        },
        "disclaimers": [
            "This annex is science evidence under locked dual-gate pins.",
            "It is NOT ACCEPTANCE and does NOT gate commercial SHIP success.",
            "Commercial transfer success = openable PDBs + dual-gate pin seal.",
            "Enrichment is informational; weak enrichment does not invalidate a pin-sealed package.",
            "Never λ=γ.",
            "Partner receipt verify remains: python handoff_ship.py --verify-bundle <partner_receipts_*.zip>",
        ],
        "note": "Thin partner science annex; mold PDBs not included.",
    }
    out_dir = Path(out_dir)
    jp = write_json(out_dir / "PARTNER_SCIENCE_ANNEX.json", annex)
    md_lines = [
        "# Partner science annex (known solutions)",
        "",
        "Dual-gate ranking evidence on public experimental structures.",
        "",
        "## Dual-gate pin (locked)",
        "",
        f"- pin ok: **{pin.get('ok')}**",
        f"- soft_T(n=12): **{pin.get('soft_T')}** (expect 0.036)",
        f"- seq_mix: **{pin.get('seq_mix')}**",
        f"- face_weight: **{pin.get('face_weight')}**",
        "",
        "## Summary",
        "",
        f"- ranked OK: {agg.get('n_ok')} / attempted {agg.get('n_attempted')} "
        f"(universe n={annex['counts']['n_universe']})",
    ]
    for tag, label in (
        ("curated_probe", "probe"),
        ("curated_holdout", "holdout"),
        ("rcsb_expand", "RCSB expand"),
        ("cpsea2_demo", "CPSea2 demo"),
        ("all_ok", "all OK"),
    ):
        m = _mean(tag)
        if m["n"]:
            enr = m["mean_enrichment"]
            enr_s = f"{enr:.1%}" if enr is not None else "n/a"
            md_lines.append(f"- mean enrichment ({label}): **{enr_s}** (n={m['n']})")
    md_lines.extend(
        [
            "",
            "## Kabsch subset (structure fit, capped)",
            "",
            f"- n_ok: {kagg.get('n_kabsch_ok', 0)}",
            f"- mean best rank score (lower better): {kagg.get('mean_best_rank_score')}",
            "",
            "## Important",
            "",
            "- **Not ACCEPTANCE / not SHIP success.**",
            "- Commercial success metric remains **openable PDBs + dual-gate pin**.",
            "- Enrichment is informational only.",
            "- Never λ=γ.",
            "- To verify a commercial proof zip: "
            "`python handoff_ship.py --verify-bundle partner_receipts_….zip`",
            "",
        ]
    )
    mp = out_dir / "PARTNER_SCIENCE_ANNEX.md"
    mp.write_text("\n".join(md_lines), encoding="utf-8")
    return jp, mp


def run_known_solutions(
    *,
    knobs_path: Path | str,
    out_dir: Path | str,
    n_decoys: int = 24,
    n_seeds: int = 3,
    n_zeros: int = 14,
    noise: float = 0.45,
    skip_expand: bool = False,
    allow_hf: bool = False,
    rcsb_list: Path | str | None = None,
    extra_ids: list[str] | None = None,
    only_ids: bool = False,
    max_expand: int | None = None,
    full_seeds: bool = False,
    kabsch_set: str = "curated",
    kabsch_max: int = 12,
    decoy_mode: str = "soft",
    dry_run: bool = False,
    seed: int = 0,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Full known-solutions pipeline. Returns report dict (also written unless dry_run partial)."""
    pin = verify_dual_gate_pin()
    universe_doc = resolve_universe(
        skip_expand=skip_expand,
        allow_hf=allow_hf,
        rcsb_list=rcsb_list,
        extra_ids=extra_ids,
        only_ids=only_ids,
        max_expand=max_expand,
    )
    stamp = stamp or _utc_stamp()
    root = Path(out_dir) / stamp
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "pin.json", pin)
    write_json(root / "id_universe.json", universe_doc)

    base: dict[str, Any] = {
        "ontology": "known_solutions_report_not_lambda_eq_gamma",
        "stamp": stamp,
        "pin": pin,
        "production_rank": dict(PRODUCTION_RANK),
        "id_universe": universe_doc,
        "config": {
            "n_decoys": int(n_decoys),
            "n_seeds": int(n_seeds),
            "n_zeros": int(n_zeros),
            "noise": float(noise),
            "full_seeds": bool(full_seeds),
            "kabsch_set": kabsch_set,
            "kabsch_max": int(kabsch_max),
            "decoy_mode": str(decoy_mode or "soft"),
            "skip_expand": bool(skip_expand),
            "allow_hf": bool(allow_hf),
            "only_ids": bool(only_ids),
            "max_expand": max_expand,
            "knobs_path": str(knobs_path),
            "dry_run": bool(dry_run),
            "seed": int(seed),
        },
        "note": (
            "Report-only science ledger; not ACCEPTANCE/SHIP gate. "
            "Never enrichment score-chase; never λ=γ."
        ),
    }

    def _write_all(payload: dict[str, Any]) -> None:
        write_json(root / "KNOWN_SOLUTIONS.json", payload)
        write_internal_md(payload, root / "KNOWN_SOLUTIONS.md")
        write_partner_annex(payload, root)
        write_summary_tsv(payload, root / "summary.tsv")

    if not pin.get("ok"):
        base["status"] = "PIN_FAIL"
        base["out_dir"] = str(root)
        _write_all(base)
        _write_latest_pointer(out_dir, root)
        try:
            update_known_solutions_index(out_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("known_solutions INDEX: %s", exc)
        return base

    if dry_run:
        base["status"] = "DRY_RUN"
        base["rows"] = []
        base["kabsch_rows"] = []
        base["aggregates"] = aggregate_rows([])
        base["kabsch_aggregates"] = aggregate_kabsch([])
        base["out_dir"] = str(root)
        _write_all(base)
        _write_latest_pointer(out_dir, root)
        try:
            update_known_solutions_index(out_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("known_solutions INDEX: %s", exc)
        return base

    if universe_doc.get("n_total", 0) < 1:
        base["status"] = "EMPTY_UNIVERSE"
        base["out_dir"] = str(root)
        _write_all(base)
        _write_latest_pointer(out_dir, root)
        try:
            update_known_solutions_index(out_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("known_solutions INDEX: %s", exc)
        return base

    knobs = load_knobs(knobs_path)
    rows: list[dict[str, Any]] = []
    for i, ent in enumerate(universe_doc["universe"]):
        pid = ent["id"]
        tag = ent["tag"]
        n_s = _seeds_for_tag(tag, n_seeds, full_seeds)
        logger.info(
            "rank_one %s tag=%s seeds=%s (%s/%s)",
            pid,
            tag,
            n_s,
            i + 1,
            len(universe_doc["universe"]),
        )
        raw = run_rank_one(
            pid,
            knobs,
            n_decoys=n_decoys,
            n_seeds=n_s,
            n_zeros=n_zeros,
            seed=int(seed) + i * 17,
            noise=noise,
            decoy_mode=decoy_mode,
        )
        rows.append(_slim_rank_row(raw, tag=tag, source=ent.get("source", "")))

    kabsch_ids = _kabsch_candidate_ids(
        universe_doc["universe"],
        kabsch_set=kabsch_set,
        kabsch_max=kabsch_max,
    )
    kabsch_rows: list[dict[str, Any]] = []
    for j, pid in enumerate(kabsch_ids):
        logger.info("kabsch %s (%s/%s)", pid, j + 1, len(kabsch_ids))
        kabsch_rows.append(
            run_kabsch_subset(
                pid,
                knobs,
                n_zeros=n_zeros,
                defect_beta=float(PRODUCTION_RANK.get("defect_beta", 0.20)),
            )
        )

    base["status"] = "OK"
    base["rows"] = rows
    base["kabsch_rows"] = kabsch_rows
    base["aggregates"] = aggregate_rows(rows)
    base["kabsch_aggregates"] = aggregate_kabsch(kabsch_rows)
    base["out_dir"] = str(root)

    _write_all(base)
    _write_latest_pointer(out_dir, root)

    try:
        update_known_solutions_index(out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("known_solutions INDEX: %s", exc)

    try:
        from realm.validate.known_solutions_pdf import write_partner_science_pdf

        write_partner_science_pdf(root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("partner science PDF skipped: %s", exc)

    return base


def _tag_slice(agg: dict[str, Any], tag: str) -> dict[str, Any]:
    b = agg.get(tag) or {}
    return {
        "n": int(b.get("n") or 0),
        "mean_enrichment": b.get("mean_enrichment"),
        "top20_rate": b.get("top20_rate"),
        "mean_native_rank": b.get("mean_native_rank"),
    }


def build_decoy_mode_compare(
    mode_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compare aggregates across decoy modes (soft / mixed / hard)."""
    by_mode: dict[str, Any] = {}
    for mode, rep in mode_reports.items():
        agg = rep.get("aggregates") or {}
        by_mode[mode] = {
            "status": rep.get("status"),
            "decoy_mode": mode,
            "n_ok": agg.get("n_ok"),
            "n_attempted": agg.get("n_attempted"),
            "curated_probe": _tag_slice(agg, "curated_probe"),
            "curated_holdout": _tag_slice(agg, "curated_holdout"),
            "rcsb_expand": _tag_slice(agg, "rcsb_expand"),
            "all_ok": _tag_slice(agg, "all_ok"),
            "out_dir": rep.get("out_dir"),
        }

    # deltas vs soft baseline when present
    soft = by_mode.get("soft") or {}
    deltas: dict[str, Any] = {}
    soft_all = (soft.get("all_ok") or {}).get("mean_enrichment")
    soft_hold = (soft.get("curated_holdout") or {}).get("mean_enrichment")
    for mode, block in by_mode.items():
        if mode == "soft":
            continue
        all_m = (block.get("all_ok") or {}).get("mean_enrichment")
        hold_m = (block.get("curated_holdout") or {}).get("mean_enrichment")
        deltas[mode] = {
            "delta_all_vs_soft": (
                None
                if soft_all is None or all_m is None
                else float(all_m) - float(soft_all)
            ),
            "delta_holdout_vs_soft": (
                None
                if soft_hold is None or hold_m is None
                else float(hold_m) - float(soft_hold)
            ),
        }

    return {
        "ontology": "decoy_mode_compare_not_lambda_eq_gamma",
        "by_mode": by_mode,
        "deltas_vs_soft": deltas,
        "note": (
            "Harder decoys are a science stress test only. "
            "Commercial accept/ship never uses enrichment or decoy mode."
        ),
    }


def write_decoy_mode_compare_md(compare: dict[str, Any], path: Path | str) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Decoy mode comparison (known solutions)",
        "",
        "Report-only stress test: soft (production) vs mixed/hard structured decoys.",
        "",
        "| mode | probe enr | holdout enr | expand enr | all enr | top20 all |",
        "|------|-----------|-------------|------------|---------|-----------|",
    ]
    by = compare.get("by_mode") or {}
    for mode in sorted(by.keys(), key=lambda m: {"soft": 0, "mixed": 1, "hard": 2}.get(m, 9)):
        b = by[mode]

        def _pct(tag: str) -> str:
            v = (b.get(tag) or {}).get("mean_enrichment")
            return f"{v:.1%}" if v is not None else "—"

        def _t20() -> str:
            v = (b.get("all_ok") or {}).get("top20_rate")
            return f"{v:.1%}" if v is not None else "—"

        lines.append(
            f"| {mode} | {_pct('curated_probe')} | {_pct('curated_holdout')} | "
            f"{_pct('rcsb_expand')} | {_pct('all_ok')} | {_t20()} |"
        )
    deltas = compare.get("deltas_vs_soft") or {}
    if deltas:
        lines.extend(["", "## Δ vs soft (negative = harder decoys hurt enrichment)", ""])
        for mode, d in sorted(deltas.items()):
            da = d.get("delta_all_vs_soft")
            dh = d.get("delta_holdout_vs_soft")
            da_s = f"{da:+.1%}" if da is not None else "—"
            dh_s = f"{dh:+.1%}" if dh is not None else "—"
            lines.append(f"- **{mode}**: all {da_s}, holdout {dh_s}")
    lines.extend(
        [
            "",
            "## Disclaimers",
            "",
            "- Not ACCEPTANCE / not SHIP success.",
            "- Pin remains soft_T(n=12)=0.036; never retuned for decoy mode.",
            "- Never λ=γ.",
            "",
        ]
    )
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def run_compare_modes(
    *,
    knobs_path: Path | str,
    out_dir: Path | str,
    modes: list[str] | tuple[str, ...] = ("soft", "mixed", "hard"),
    n_decoys: int = 24,
    n_seeds: int = 1,
    n_zeros: int = 14,
    noise: float = 0.45,
    skip_expand: bool = False,
    allow_hf: bool = False,
    rcsb_list: Path | str | None = None,
    extra_ids: list[str] | None = None,
    only_ids: bool = False,
    max_expand: int | None = None,
    full_seeds: bool = False,
    kabsch_set: str = "curated",
    kabsch_max: int = 4,
    seed: int = 0,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Run known-solutions for each decoy mode; write comparison ledger.

    Kabsch runs only for the first mode (cost control); later modes use kabsch none.
    """
    stamp = stamp or _utc_stamp()
    root = Path(out_dir) / stamp
    root.mkdir(parents=True, exist_ok=True)
    pin = verify_dual_gate_pin()
    write_json(root / "pin.json", pin)

    mode_reports: dict[str, dict[str, Any]] = {}
    modes_clean = [str(m).lower().strip() for m in modes if str(m).strip()]
    if not modes_clean:
        modes_clean = ["soft", "mixed", "hard"]

    for i, mode in enumerate(modes_clean):
        logger.info("=== compare decoy_mode=%s (%s/%s) ===", mode, i + 1, len(modes_clean))
        rep = run_known_solutions(
            knobs_path=knobs_path,
            out_dir=root / "modes",
            n_decoys=n_decoys,
            n_seeds=n_seeds,
            n_zeros=n_zeros,
            noise=noise,
            skip_expand=skip_expand,
            allow_hf=allow_hf,
            rcsb_list=rcsb_list,
            extra_ids=extra_ids,
            only_ids=only_ids,
            max_expand=max_expand,
            full_seeds=full_seeds,
            kabsch_set=kabsch_set if i == 0 else "none",
            kabsch_max=kabsch_max,
            decoy_mode=mode,
            dry_run=False,
            seed=int(seed) + i * 1009,
            stamp=f"{mode}",
        )
        mode_reports[mode] = rep

    compare = build_decoy_mode_compare(mode_reports)
    write_json(root / "DECOY_MODE_COMPARE.json", compare)
    write_decoy_mode_compare_md(compare, root / "DECOY_MODE_COMPARE.md")

    # Partner annex: soft primary stats + comparison table
    soft_rep = mode_reports.get("soft") or next(iter(mode_reports.values()))
    annex_base = dict(soft_rep)
    annex_base["stamp"] = stamp
    annex_base["decoy_mode_compare"] = compare
    annex_base["config"] = {
        **(soft_rep.get("config") or {}),
        "compare_modes": modes_clean,
        "n_seeds": n_seeds,
        "n_decoys": n_decoys,
    }
    write_partner_annex(annex_base, root)
    # Patch annex JSON with compare block explicitly
    annex_path = root / "PARTNER_SCIENCE_ANNEX.json"
    if annex_path.is_file():
        try:
            annex = json.loads(annex_path.read_text(encoding="utf-8"))
            annex["decoy_mode_compare"] = {
                "by_mode": {
                    m: {
                        "all_ok": (compare["by_mode"][m].get("all_ok")),
                        "curated_holdout": (compare["by_mode"][m].get("curated_holdout")),
                        "curated_probe": (compare["by_mode"][m].get("curated_probe")),
                        "rcsb_expand": (compare["by_mode"][m].get("rcsb_expand")),
                    }
                    for m in compare.get("by_mode") or {}
                },
                "deltas_vs_soft": compare.get("deltas_vs_soft"),
            }
            annex["disclaimers"] = list(annex.get("disclaimers") or []) + [
                "decoy_mode_compare is a science stress table; not an acceptance metric.",
            ]
            write_json(annex_path, annex)
        except Exception as exc:  # noqa: BLE001
            logger.warning("annex compare patch failed: %s", exc)

    # Append compare table to partner MD
    md_path = root / "PARTNER_SCIENCE_ANNEX.md"
    if md_path.is_file():
        extra = write_decoy_mode_compare_md(compare, root / "_compare_snippet.md")
        try:
            body = md_path.read_text(encoding="utf-8")
            snip = extra.read_text(encoding="utf-8")
            md_path.write_text(body.rstrip() + "\n\n" + snip, encoding="utf-8")
            extra.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("partner md compare append: %s", exc)

    # Internal rollup
    rollup = {
        "ontology": "known_solutions_compare_not_lambda_eq_gamma",
        "stamp": stamp,
        "pin": pin,
        "modes": modes_clean,
        "compare": compare,
        "mode_out_dirs": {m: r.get("out_dir") for m, r in mode_reports.items()},
        "status": "OK" if pin.get("ok") and mode_reports else "FAIL",
        "out_dir": str(root),
        "note": "Multi-mode decoy comparison; report-only; never λ=γ.",
    }
    write_json(root / "KNOWN_SOLUTIONS_COMPARE.json", rollup)
    write_internal_md(
        {
            **soft_rep,
            "stamp": stamp,
            "aggregates": soft_rep.get("aggregates") or {},
            "kabsch_aggregates": soft_rep.get("kabsch_aggregates") or {},
            "pin": pin,
        },
        root / "KNOWN_SOLUTIONS.md",
    )
    # extend internal md with compare path
    try:
        p = root / "KNOWN_SOLUTIONS.md"
        p.write_text(
            p.read_text(encoding="utf-8")
            + "\n## Decoy mode comparison\n\n"
            + f"See `DECOY_MODE_COMPARE.md` (modes={modes_clean}).\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass

    _write_latest_pointer(out_dir, root)

    try:
        update_known_solutions_index(out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("known_solutions INDEX: %s", exc)

    try:
        from realm.validate.known_solutions_pdf import write_partner_science_pdf

        write_partner_science_pdf(root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("partner science PDF skipped: %s", exc)

    return rollup
