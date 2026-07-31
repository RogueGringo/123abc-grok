"""KB geometry P1 zigzag + P2 science annex (Academic KB integration)."""

from __future__ import annotations

import numpy as np
import pytest

from realm.kb_geometry.science_annex import (
    assert_science_not_acceptance,
    attach_science_theory,
    build_science_annex_base,
    is_informational_only,
)
from realm.kb_geometry.zigzag_windows import (
    phase_summary,
    zigzag_from_crit_filtration,
    zigzag_window_barcode,
)


def test_zigzag_two_scale_series_has_structure():
    """Coarse step + fine noise: full series and windows produce bars."""
    # Two plateaus with small noise → multi-scale structure
    rng = np.random.default_rng(0)
    a = np.ones(40) * 0.0 + rng.normal(0, 0.02, 40)
    b = np.ones(40) * 1.0 + rng.normal(0, 0.02, 40)
    series = np.concatenate([a, b])
    rep = zigzag_window_barcode(series, n_windows=4, long_frac=0.15)
    assert rep["not_acceptance"] is True
    assert rep["n_points"] == 80
    assert rep["n_bars"] >= 1
    assert rep["full_series"]["n_bars"] >= 1
    assert "arXiv:2410.11042" in rep["kb_source"]
    assert "windows" in rep["transfer_note"].lower() or "not LLM" in rep["transfer_note"]
    phases = rep["phases"]
    assert phases["not_acceptance"] is True
    assert phases["dominant"] in ("rearrange", "stable", "refine", "emit", "empty")


def test_zigzag_empty_and_flat():
    empty = zigzag_window_barcode([])
    assert empty["n_points"] == 0
    flat = zigzag_window_barcode(np.ones(20))
    assert flat["n_bars"] >= 1
    assert flat["not_acceptance"] is True


def test_phase_summary_labels_length():
    rep = zigzag_window_barcode(np.linspace(0, 1, 32), n_windows=4)
    ph = phase_summary(rep)
    assert len(ph["labels"]) == 4


def test_zigzag_from_crit_filtration_shape():
    filt = {
        "s_min": 0.0,
        "s_max": 1.0,
        "n_persistent": 2,
        "max_persistence": 0.5,
        "diagram_H0": [
            {"birth": 0.0, "death": 0.5, "persistence": 0.5},
            {"birth": 0.1, "death": 0.2, "persistence": 0.1},
            {"birth": 0.2, "death": 0.8, "persistence": 0.6},
            {"birth": 0.3, "death": 0.35, "persistence": 0.05},
        ],
    }
    z = zigzag_from_crit_filtration(filt, n_windows=2)
    assert z["source"] == "crit_action_filtration"
    assert z["not_acceptance"] is True
    assert z["n_windows"] == 2


def test_crit_action_filtration_with_zigzag_flag():
    from realm.axiomz import crit_action_filtration

    class _FakeAction:
        def S(self, theta):
            t = np.asarray(theta, dtype=float)
            return np.sin(t) + 0.15 * np.cos(2.0 * t)

    filt = crit_action_filtration(
        _FakeAction(), n_grid=256, with_zigzag=True, zigzag_windows=3
    )
    assert "diagram_H0" in filt
    assert "zigzag_windows" in filt
    assert filt["zigzag_windows"].get("not_acceptance") is True


def test_science_annex_base_forces_not_acceptance():
    base = build_science_annex_base(split="holdout")
    assert base["not_acceptance"] is True
    assert base["claim_class"] == "informational"
    assert base["pin_writable"] is False
    assert base["acceptance_writable"] is False
    assert base["split"] == "holdout"
    assert is_informational_only(base)
    assert_science_not_acceptance(base)


def test_attach_science_theory_probe_holdout_split():
    raw = {"kind": "partner_science_annex", "foo": 1}
    mean = {
        "curated_probe": {"n": 2, "mean_enrichment": 0.9},
        "curated_holdout": {"n": 3, "mean_enrichment": 0.4},
    }
    out = attach_science_theory(raw, split="mixed", mean_by_split=mean)
    assert out["foo"] == 1
    assert out["not_acceptance"] is True
    assert out["generalization"]["probe"]["n"] == 2
    assert out["generalization"]["holdout"]["n"] == 3
    assert out["generalization"]["not_acceptance"] is True
    assert is_informational_only(out)


def test_assert_science_rejects_accept_writable():
    bad = build_science_annex_base()
    bad["acceptance_writable"] = True
    with pytest.raises(ValueError, match="ACCEPTANCE|not_acceptance|informational"):
        assert_science_not_acceptance(bad)


def test_partner_annex_includes_theory_fields():
    from realm.validate.known_solutions import write_partner_annex

    report = {
        "stamp": "test",
        "pin": {"ok": True, "soft_T": 0.036, "seq_mix": 0.0, "face_weight": 0.08},
        "aggregates": {
            "n_attempted": 5,
            "n_ok": 4,
            "n_fail": 1,
            "curated_probe": {"n": 2, "mean_enrichment": 0.8},
            "curated_holdout": {"n": 2, "mean_enrichment": 0.5},
            "all_ok": {"n": 4, "mean_enrichment": 0.65},
        },
        "kabsch_aggregates": {"n_kabsch_ok": 0},
        "id_universe": {"n_total": 5, "sources": {}},
    }
    import tempfile
    from pathlib import Path
    import json

    with tempfile.TemporaryDirectory() as td:
        jp, _mp = write_partner_annex(report, Path(td))
        body = json.loads(jp.read_text(encoding="utf-8"))
    assert body["not_acceptance"] is True
    assert body["claim_class"] == "informational"
    assert "generalization" in body
    assert body["generalization"]["holdout"]["n"] == 2
    assert body["pin_writable"] is False


def test_job_science_annex_has_theory_fields():
    from realm.job_os.science import dual_gate_windows

    series = {
        "channels": {
            "SSSI": list(np.linspace(0, 1, 30)),
            "RPM": list(np.linspace(100, 120, 30)),
        }
    }
    rep = dual_gate_windows(series, window_scale=1, pin_ok=True)
    assert rep["not_acceptance"] is True
    assert rep["informational_only"] is True
    assert is_informational_only(rep)
