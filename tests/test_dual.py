"""Dual instrument: operator fingerprint + projection score."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from realm.validate.dual import (
    adaptive_defect_beta,
    dual_score_geometry,
    forge_crit_geometry,
    mid_length_omega_bank,
    multimode_for_ca_length,
    operator_fingerprint,
    polish_crit_pack_holonomy,
    sectors_for_ca_length,
    select_mold_by_fit,
    select_multimode_by_fit,
)


def _knobs():
    p = Path("evolve_result.json")
    if not p.is_file():
        pytest.skip("need evolve_result.json")
    return json.loads(p.read_text(encoding="utf-8"))["best_knobs"]


def test_sectors_for_ca_length_adaptive():
    assert sectors_for_ca_length(6, "adaptive") == 4
    assert sectors_for_ca_length(8, "adaptive") == 4
    assert sectors_for_ca_length(10, "adaptive") == 6
    assert sectors_for_ca_length(12, "adaptive") == 4  # 1TET-class
    assert sectors_for_ca_length(14, "adaptive") == 6  # cap-6 (not 8)
    assert sectors_for_ca_length(26, "adaptive") == 6
    assert sectors_for_ca_length(11, "fixed", default=6) == 6


def test_multimode_for_ca_length_adaptive_short():
    assert multimode_for_ca_length(6, "adaptive_short") is True
    assert multimode_for_ca_length(8, "adaptive_short") is True
    assert multimode_for_ca_length(11, "adaptive_short") is False
    assert multimode_for_ca_length(12, "off") is False
    assert multimode_for_ca_length(6, "on") is True


def test_select_multimode_by_fit_returns_pack():
    kn = _knobs()
    t = np.linspace(0, 2 * np.pi, 11, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.05 * np.sin(3 * t)])
    use_m, pack, diag = select_multimode_by_fit(
        xyz, kn, N=11, n_zeros=14, n_sectors=6, soft_T=0.04, prefer_maxop=False
    )
    assert isinstance(use_m, bool)
    assert len(pack["templates"]) >= 1
    assert "dist_planar" in diag and "dist_multimode" in diag
    assert diag["chosen"] in ("planar", "multimode")


def test_select_mold_bank_by_fit():
    kn = _knobs()
    t = np.linspace(0, 2 * np.pi, 11, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.0 * t])
    use_m, pack, diag = select_mold_by_fit(
        xyz,
        kn,
        N=11,
        n_zeros=14,
        n_sectors=6,
        soft_T=0.04,
        prefer_maxop=False,
        multimodes=(False, True),
        omega_scales=(0.9, 1.0, 1.15),
    )
    assert isinstance(use_m, bool)
    assert len(pack["templates"]) >= 1
    assert len(diag["bank"]) == 6
    assert "omega_scale_mult" in diag


def test_adaptive_defect_beta():
    assert adaptive_defect_beta(8, 0.20) == 0.20
    assert abs(adaptive_defect_beta(12, 0.20) - 0.25) < 1e-12
    assert abs(adaptive_defect_beta(13, 0.20) - 0.28) < 1e-12
    assert adaptive_defect_beta(14, 0.0) == 0.0


def test_combine_sector_weights():
    from realm.validate.dual import combine_sector_weights

    bw = np.array([1.0, 1.2, 0.8])
    gaps = np.array([0.01, 0.05, 0.02])
    w = combine_sector_weights(bw, gaps)
    assert w is not None
    assert abs(float(w.mean()) - 1.0) < 1e-6
    assert float(w.min()) > 0.0


def test_mid_length_bank_and_defect_tie():
    assert mid_length_omega_bank(11) == (0.85, 0.95, 1.0, 1.1, 1.2)
    b12 = mid_length_omega_bank(12)
    b13 = mid_length_omega_bank(13)
    assert set((0.85, 0.95, 1.0, 1.1, 1.2)).issubset(set(b12))
    assert 0.80 in b12 and 1.3 in b12
    assert b12 == b13
    assert len(b13) == 10
    kn = _knobs()
    t = np.linspace(0, 2 * np.pi, 13, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.04 * np.sin(2 * t)])
    use_m, pack, diag = select_mold_by_fit(
        xyz,
        kn,
        N=13,
        n_zeros=14,
        n_sectors=6,
        soft_T=0.04,
        prefer_maxop=False,
        multimodes=(False, True),
        omega_scales=b13,
        defect_tie=True,
    )
    assert isinstance(use_m, bool)
    assert diag["defect_tie"] is True
    assert diag["selection"] == "min_proj_then_defect_then_maxop_gap"
    assert len(diag["bank"]) == 20  # 2 × 10
    assert len(pack["templates"]) >= 1


def test_polish_crit_pack_holonomy_proj_gate():
    kn = _knobs()
    t = np.linspace(0, 2 * np.pi, 13, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.04 * np.sin(2 * t)])
    pack = forge_crit_geometry(
        kn, N=13, n_zeros=14, n_sectors=4, multimode=False, prefer_maxop=False
    )
    polished, diag = polish_crit_pack_holonomy(
        xyz, pack, n_steps=2, step=0.05, soft_T=0.04, prefer_maxop=False
    )
    assert diag["applied"] is True
    assert "proj_before" in diag and "proj_after" in diag
    if diag["accepted"]:
        assert diag["proj_after"] <= diag["proj_before"] + 1e-5
        assert polished.get("holonomy_polished") is True
    else:
        # reverted to original pack
        assert polished is pack or not polished.get("holonomy_polished")


def test_operator_fingerprint_shapes():
    th = np.linspace(0.2, 2 * np.pi - 0.2, 4)
    fp = operator_fingerprint(th, N=9, prefer_maxop=False)
    assert fp.gaps.shape == (4,)
    assert fp.mean_gap >= 0.0
    assert fp.feature_matrix().shape == (4, 3)


def test_forge_and_dual_score():
    kn = _knobs()
    pack = forge_crit_geometry(
        kn, N=11, n_zeros=14, n_sectors=6, prefer_maxop=False, multimode=False
    )
    assert len(pack["templates"]) >= 1
    assert pack["multimode"] is False
    # synthetic ring
    t = np.linspace(0, 2 * np.pi, 11, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.1 * np.sin(2 * t)])
    pure = dual_score_geometry(xyz, pack, alpha_proj=1.0, prefer_maxop=False)
    dual = dual_score_geometry(xyz, pack, alpha_proj=0.85, prefer_maxop=False)
    assert pure["method"] in (
        "CRIT_KABSCH_SOFTMIN",
        "CRIT_KABSCH_SOFTMIN_PERSIST",
        "CRIT_KABSCH_TOPK",
    )
    assert dual["method"] == "DUAL_PROJ_OP"
    assert dual["proj_dist"] == pure["mean_dist"]
    assert dual["op_dist"] >= 0.0
    assert pack.get("basin_weights") is not None
