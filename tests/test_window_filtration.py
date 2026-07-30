"""Sub-spec II Stage 6 — multi-window filtration tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from realm.validate.length_policy import policy_for
from realm.validate.window_filtration import (
    COMPONENT_SCALAR_KEYS,
    N_KNOBS,
    contiguous_windows,
    load_champion_knobs,
    score_window_filtration,
)


def test_dual_gate_length_policy_untouched_by_filtration_module():
    """Stage 6 must not alter production dual-gate pins."""
    p = policy_for(12, base_beta=0.20)
    assert abs(p.soft_T - 0.036) < 1e-12
    assert p.seq_mix == 0.0
    assert abs(p.face_weight - 0.08) < 1e-12


def test_contiguous_windows_disjoint_adjacent():
    g = np.arange(1.0, 200.0, 1.0)
    wins = contiguous_windows(g, n_zeros=14, n_windows=3)
    assert len(wins) == 3
    assert wins[0]["key_gammas"].size == 14
    assert wins[0]["lock_gammas"].size == 14
    # window 0 key ends before its lock starts
    assert float(wins[0]["key_gammas"][-1]) < float(wins[0]["lock_gammas"][0])
    assert wins[0]["disjoint"] is True


def test_stage6_dof_threshold_at_w7():
    """Design: W≥7 at 6 components → constraint_scalars ≥ 5×8 knobs."""
    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = load_champion_knobs(kn_path)
    out = score_window_filtration(kn, n_windows=7, n_zeros=14, N=13, n_sectors=6)
    assert out["W"] == 7
    assert out["constraint_scalars"] == len(COMPONENT_SCALAR_KEYS) * 7
    assert out["constraint_scalars"] >= 5 * N_KNOBS
    assert out["pass_dof"] is True
    assert out["dof_ratio"] >= 5.0
    assert len(out["windows"]) == 7
    assert out["ontology"].endswith("not_lambda_eq_gamma")
    # component matrix shape
    mat = np.asarray(out["component_matrix"], dtype=float)
    assert mat.shape == (7, len(COMPONENT_SCALAR_KEYS))
    # every window produced components
    for w in out["windows"]:
        assert "components" in w
        assert "degeneracy" in w
        assert "corr_penalty" in w["components"]


def test_stage6_small_w_fails_dof_only():
    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = load_champion_knobs(kn_path)
    out = score_window_filtration(kn, n_windows=2, n_zeros=14, N=13, n_sectors=6)
    assert out["pass_dof"] is False
    assert out["stage6_pass"] is False  # DOF fails regardless of guard


def test_g5_span_makes_omega_ratio_window_invariant():
    """Legacy path: omega ratio tracks window; G5 path: ratio ≈ omega_span everywhere."""
    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = load_champion_knobs(kn_path)

    legacy = score_window_filtration(kn, n_windows=5, n_zeros=14, use_g5_span=False)
    g5 = score_window_filtration(kn, n_windows=5, n_zeros=14, use_g5_span=True)

    # Legacy: spread across windows is large (Finding 1 confounder)
    assert legacy["g5"]["rel_spread"] > 0.05
    assert legacy["g5"]["pass_within_5pct"] is False

    # G5: ratios collapse to the anchor within 5%
    assert g5["omega_span"] is not None
    assert g5["g5"]["pass_within_5pct"] is True
    assert g5["g5"]["rel_spread"] <= 0.05
    # dual-gate still locked
    p = policy_for(12, base_beta=0.20)
    assert abs(p.soft_T - 0.036) < 1e-12