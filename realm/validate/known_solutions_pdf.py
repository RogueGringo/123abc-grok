"""Partner science one-pager PDF from known-solutions annex/compare.

Optional fpdf dependency. Report-only; never ACCEPTANCE/SHIP.
Never lambda=gamma.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _pct(v: Any) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe(text: str) -> str:
    """Core Helvetica is latin-1 only."""
    return str(text).encode("latin-1", errors="replace").decode("latin-1")


def resolve_science_stamp(stamp_or_parent: Path | str) -> Path:
    """Resolve stamp dir from stamp path, parent with LATEST, or annex file parent."""
    p = Path(stamp_or_parent)
    if p.is_file() and p.name.endswith(".json"):
        return p.parent
    if (p / "PARTNER_SCIENCE_ANNEX.json").is_file() or (
        p / "DECOY_MODE_COMPARE.json"
    ).is_file():
        return p
    if (p / "LATEST").is_file():
        return Path((p / "LATEST").read_text(encoding="utf-8").strip())
    return p


def write_partner_science_pdf(
    stamp_dir: Path | str,
    dest: Path | str | None = None,
) -> Path:
    """Write PARTNER_SCIENCE_ONEPAGER.pdf under stamp (or dest).

    Requires fpdf. Raises RuntimeError if missing or stamp incomplete.
    """
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError(
            "fpdf not installed; pip install fpdf2 to emit partner science PDF"
        ) from exc

    root = resolve_science_stamp(stamp_dir)
    annex_p = root / "PARTNER_SCIENCE_ANNEX.json"
    pin_p = root / "pin.json"
    cmp_p = root / "DECOY_MODE_COMPARE.json"
    if not annex_p.is_file() and not pin_p.is_file():
        raise FileNotFoundError(f"no science annex/pin under {root}")

    annex: dict[str, Any] = {}
    if annex_p.is_file():
        annex = _load_json(annex_p)
    pin = dict(annex.get("pin") or {})
    if pin_p.is_file():
        try:
            pin = {**pin, **_load_json(pin_p)}
        except Exception:  # noqa: BLE001
            pass

    compare: dict[str, Any] = {}
    if cmp_p.is_file():
        compare = _load_json(cmp_p)
    elif annex.get("decoy_mode_compare"):
        compare = {
            "by_mode": (annex.get("decoy_mode_compare") or {}).get("by_mode") or {},
            "deltas_vs_soft": (annex.get("decoy_mode_compare") or {}).get(
                "deltas_vs_soft"
            ),
        }

    out = Path(dest) if dest else root / "PARTNER_SCIENCE_ONEPAGER.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_left_margin(16)
    pdf.set_right_margin(16)
    pdf.set_x(16)

    def h(text: str, size: int = 12) -> None:
        pdf.set_x(16)
        pdf.set_font("Helvetica", "B", size)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 7, _safe(text))

    def p(text: str, size: int = 10) -> None:
        pdf.set_x(16)
        pdf.set_font("Helvetica", "", size)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 5, _safe(text))

    def muted(text: str, size: int = 9) -> None:
        pdf.set_x(16)
        pdf.set_font("Helvetica", "I", size)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(0, 4.5, _safe(text))
        pdf.set_text_color(0, 0, 0)

    h("Dual-gate known-solutions science one-pager", 15)
    muted(
        "Public experimental natives vs decoys under locked dual-gate pins. "
        "Informational only -- not commercial ACCEPTANCE / SHIP success."
    )
    pdf.ln(2)

    h("Dual-gate pin (locked)")
    soft = pin.get("soft_T", pin.get("expected_soft_T", 0.036))
    p(f"pin ok: {pin.get('ok')}")
    p(f"soft_T(n=12): {soft}  (expect 0.036)")
    p(f"seq_mix: {pin.get('seq_mix', 0.0)}   face_weight: {pin.get('face_weight', 0.08)}")
    p(f"stamp: {annex.get('stamp') or root.name}")
    pdf.ln(1)

    tags = annex.get("mean_enrichment_by_tag") or {}
    counts = annex.get("counts") or {}
    h("Native-vs-decoy enrichment (soft / production decoys)")
    p(
        f"ranked OK: {counts.get('n_ranked_ok')} / attempted {counts.get('n_attempted')} "
        f"(universe n={counts.get('n_universe')})"
    )
    for key, label in (
        ("curated_probe", "probe"),
        ("curated_holdout", "holdout"),
        ("rcsb_expand", "RCSB expand"),
        ("all_ok", "all OK"),
    ):
        block = tags.get(key) or {}
        if not block.get("n"):
            continue
        p(
            f"  {label}: mean enrichment {_pct(block.get('mean_enrichment'))}  (n={block.get('n')})"
        )
    pdf.ln(1)

    by_mode = compare.get("by_mode") or {}
    if by_mode:
        h("Decoy-mode stress (soft / mixed / hard)")
        # Table
        col_w = [28, 34, 34, 34, 34]
        headers = ["mode", "probe", "holdout", "expand", "all"]
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_x(16)
        for w, lab in zip(col_w, headers):
            pdf.cell(w, 6, lab, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        order = sorted(
            by_mode.keys(),
            key=lambda m: {"soft": 0, "mixed": 1, "hard": 2}.get(m, 9),
        )
        for mode in order:
            b = by_mode[mode] or {}

            def _enr(tag: str, block: dict = b) -> str:
                t = block.get(tag) or {}
                return _pct(t.get("mean_enrichment"))

            row = [
                mode,
                _enr("curated_probe"),
                _enr("curated_holdout"),
                _enr("rcsb_expand"),
                _enr("all_ok"),
            ]
            pdf.set_x(16)
            for w, cell in zip(col_w, row):
                pdf.cell(w, 6, _safe(cell), border=1)
            pdf.ln()
        deltas = compare.get("deltas_vs_soft") or {}
        if deltas:
            pdf.ln(1)
            for mode, d in sorted(deltas.items()):
                da = d.get("delta_all_vs_soft")
                dh = d.get("delta_holdout_vs_soft")
                da_s = f"{float(da) * 100:+.1f} pts" if da is not None else "-"
                dh_s = f"{float(dh) * 100:+.1f} pts" if dh is not None else "-"
                p(f"  delta vs soft [{mode}]: all {da_s}, holdout {dh_s}", size=9)
        pdf.ln(1)

    kabsch = annex.get("kabsch_subset") or {}
    if kabsch.get("n_ok"):
        h("Structure Kabsch subset (capped)")
        p(
            f"n_ok: {kabsch.get('n_ok')}  mean best rank score (lower better): "
            f"{kabsch.get('mean_best_rank_score')}"
        )
        pdf.ln(1)

    pdf.set_text_color(120, 40, 40)
    h("Important -- not acceptance")
    pdf.set_text_color(0, 0, 0)
    disclaimers = annex.get("disclaimers") or [
        "This annex is science evidence under locked dual-gate pins.",
        "It is NOT ACCEPTANCE and does NOT gate commercial SHIP success.",
        "Commercial transfer success = openable PDBs + dual-gate pin seal.",
        "Enrichment is informational only.",
        "Never lambda=gamma.",
        "Partner receipt verify: python handoff_ship.py --verify-bundle partner_receipts_*.zip",
    ]
    for d in disclaimers:
        p(f"- {d}", size=9)

    pdf.ln(2)
    muted(
        "Generated by realm.validate.known_solutions_pdf. "
        "Ontology: Crit projection molds from zeta substrate only -- not lambda=gamma."
    )

    pdf.output(str(out))
    logger.info("partner science PDF -> %s", out)
    return out
