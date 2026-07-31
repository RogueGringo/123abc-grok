"""Partner science PDF one-pager tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.validate.known_solutions_pdf import (
    resolve_science_stamp,
    write_partner_science_pdf,
)


def _stamp(tmp_path: Path) -> Path:
    s = tmp_path / "stamp"
    s.mkdir()
    (s / "pin.json").write_text(
        json.dumps(
            {
                "ok": True,
                "soft_T": 0.036,
                "seq_mix": 0.0,
                "face_weight": 0.08,
                "expected_soft_T": 0.036,
            }
        ),
        encoding="utf-8",
    )
    (s / "PARTNER_SCIENCE_ANNEX.json").write_text(
        json.dumps(
            {
                "kind": "partner_science_annex",
                "stamp": "test",
                "pin": {"ok": True, "soft_T": 0.036, "seq_mix": 0.0, "face_weight": 0.08},
                "counts": {
                    "n_attempted": 3,
                    "n_ranked_ok": 3,
                    "n_fail": 0,
                    "n_universe": 3,
                },
                "mean_enrichment_by_tag": {
                    "curated_probe": {"n": 1, "mean_enrichment": 0.9},
                    "curated_holdout": {"n": 1, "mean_enrichment": 0.8},
                    "all_ok": {"n": 3, "mean_enrichment": 0.85},
                },
                "kabsch_subset": {"n_ok": 1, "mean_best_rank_score": 0.2},
                "disclaimers": [
                    "NOT ACCEPTANCE",
                    "Never lambda=gamma.",
                ],
            }
        ),
        encoding="utf-8",
    )
    (s / "DECOY_MODE_COMPARE.json").write_text(
        json.dumps(
            {
                "by_mode": {
                    "soft": {
                        "curated_probe": {"mean_enrichment": 0.9},
                        "curated_holdout": {"mean_enrichment": 0.8},
                        "rcsb_expand": {"mean_enrichment": 0.7},
                        "all_ok": {"mean_enrichment": 0.85},
                    },
                    "hard": {
                        "curated_probe": {"mean_enrichment": 0.6},
                        "curated_holdout": {"mean_enrichment": 0.5},
                        "rcsb_expand": {"mean_enrichment": 0.4},
                        "all_ok": {"mean_enrichment": 0.5},
                    },
                },
                "deltas_vs_soft": {
                    "hard": {
                        "delta_all_vs_soft": -0.35,
                        "delta_holdout_vs_soft": -0.3,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return s


def test_resolve_science_stamp_latest(tmp_path: Path):
    s = _stamp(tmp_path)
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "LATEST").write_text(str(s.resolve()), encoding="utf-8")
    assert resolve_science_stamp(parent) == s


def test_write_partner_science_pdf(tmp_path: Path):
    fpdf = pytest.importorskip("fpdf")
    assert fpdf
    s = _stamp(tmp_path)
    pdf = write_partner_science_pdf(s)
    assert pdf.is_file()
    assert pdf.stat().st_size > 500
    assert pdf.name == "PARTNER_SCIENCE_ONEPAGER.pdf"
    # header present in binary-ish form
    data = pdf.read_bytes()
    assert data[:4] == b"%PDF"
    # Branded content (compressed streams may still embed ASCII strings)
    # At least ensure multi-page-safe size after branding header/footer
    assert pdf.stat().st_size > 800


def test_pdf_from_cli(tmp_path: Path):
    pytest.importorskip("fpdf")
    from known_solutions import main

    s = _stamp(tmp_path)
    rc = main(["--pdf-from", str(s)])
    assert rc == 0
    assert (s / "PARTNER_SCIENCE_ONEPAGER.pdf").is_file()
