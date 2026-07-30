"""Dual instrument: operator fingerprint + projection score."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from realm.validate.dual import (
    dual_score_geometry,
    forge_crit_geometry,
    operator_fingerprint,
)


def _knobs():
    p = Path("evolve_result.json")
    if not p.is_file():
        pytest.skip("need evolve_result.json")
    return json.loads(p.read_text(encoding="utf-8"))["best_knobs"]


def test_operator_fingerprint_shapes():
    th = np.linspace(0.2, 2 * np.pi - 0.2, 4)
    fp = operator_fingerprint(th, N=9, prefer_maxop=False)
    assert fp.gaps.shape == (4,)
    assert fp.mean_gap >= 0.0
    assert fp.feature_matrix().shape == (4, 3)


def test_forge_and_dual_score():
    kn = _knobs()
    pack = forge_crit_geometry(kn, N=11, n_zeros=14, n_sectors=6, prefer_maxop=False)
    assert len(pack["templates"]) >= 1
    # synthetic ring
    t = np.linspace(0, 2 * np.pi, 11, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.1 * np.sin(2 * t)])
    pure = dual_score_geometry(xyz, pack, alpha_proj=1.0, prefer_maxop=False)
    dual = dual_score_geometry(xyz, pack, alpha_proj=0.85, prefer_maxop=False)
    assert pure["method"] in ("CRIT_KABSCH_SOFTMIN", "CRIT_KABSCH_TOPK")
    assert dual["method"] == "DUAL_PROJ_OP"
    assert dual["proj_dist"] == pure["mean_dist"]
    assert dual["op_dist"] >= 0.0
