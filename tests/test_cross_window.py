"""Sub-spec II Stages 7–8 tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from realm.validate.cross_window import (
    advantage_series,
    number_variance,
    persistence_barcode,
    rigidity_report_for_block,
    score_rigidity_filtration,
    compare_arms_filtration,
    unfold_ordinates,
)
from realm.validate.length_policy import policy_for
from realm.validate.window_filtration import load_champion_knobs
from realm.validate.zeros import real_zeros


def test_dual_gate_still_locked():
    p = policy_for(12, base_beta=0.20)
    assert abs(p.soft_T - 0.036) < 1e-12
    assert p.seq_mix == 0.0


def test_unfold_and_number_variance_finite():
    g = real_zeros(40)
    s = unfold_ordinates(g)
    assert s.size == 39
    assert abs(float(np.mean(s)) - 1.0) < 0.15  # roughly unit mean
    nv = number_variance(s, 5.0)
    assert np.isfinite(nv)
    assert nv >= 0.0


def test_rigidity_report_block():
    g = real_zeros(30)
    rep = rigidity_report_for_block(g[:14])
    assert "delta3" in rep and "number_variance" in rep
    assert "carrier" in rep


def test_persistence_barcode_lifespan():
    # True True True False True True → max lifespan 3; W=6 → ceil(W/2)=3 → pass
    bc = persistence_barcode([True, True, True, False, True, True])
    assert bc["max_lifespan"] == 3
    assert bc["threshold_ceil_W_over_2"] == 3
    assert bc["stage8_pass"] is True
    # single window blip
    bc2 = persistence_barcode([False, True, False, False, False, False, False])
    assert bc2["max_lifespan"] == 1
    assert bc2["stage8_pass"] is False  # ceil(7/2)=4


def test_advantage_series_lower_better():
    wins = advantage_series([1.0, 2.0, 0.5], [1.5, 1.0, 0.6], lower_is_better=True)
    assert wins.tolist() == [True, False, True]


def test_rigidity_filtration_zeta():
    out = score_rigidity_filtration(n_windows=4, n_zeros=14, arm="zeta")
    assert out["stage"] == 7
    assert out["W"] == 4
    assert len(out["carrier_series"]) == 4
    assert out["ontology"].endswith("not_lambda_eq_gamma")


def test_compare_arms_persistence_smoke():
    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = load_champion_knobs(kn_path)
    out = compare_arms_filtration(
        kn,
        arm_a="zeta",
        arm_b="gue",
        n_windows=4,
        n_zeros=14,
        N=13,
        n_sectors=6,
        component_key="density_return_l1",
        rng_seed=1,
    )
    assert out["W"] == 4
    assert "component_persistence" in out
    assert "rigidity_persistence" in out
    assert "max_lifespan" in out["component_persistence"]
    assert out["ontology"].endswith("not_lambda_eq_gamma")
    # stage8 result is boolean either way — structure only
    assert isinstance(out["component_persistence"]["stage8_pass"], bool)


def test_multi_carrier_or_and_fusion():
    from realm.validate.cross_window import multi_carrier_persistence

    # carrier A wins first 4 windows; B wins last 4 → OR lifespan 7, AND 0
    a = [True, True, True, True, False, False, False]
    b = [False, False, False, True, True, True, True]
    out = multi_carrier_persistence({"A": a, "B": b})
    assert out["or_fusion"]["max_lifespan"] == 7
    assert out["or_fusion"]["stage8_pass"] is True  # ceil(7/2)=4
    assert out["and_fusion"]["max_lifespan"] == 1
    assert out["best_lifespan"] == 4


def test_existence_arm_scan_smoke():
    from realm.validate.cross_window import existence_arm_scan

    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = load_champion_knobs(kn_path)
    out = existence_arm_scan(
        kn,
        arms=("zeta", "arith", "gue"),
        n_windows=3,
        n_zeros=14,
        N=13,
        n_sectors=6,
        rng_seed=2,
    )
    assert out["stage"] == "9-lite"
    assert "zeta" in out["arm_rows"] and "arith" in out["arm_rows"]
    assert "density_return_rank_lower_better" in out
    assert "arith_beats_zeta_existence" in out
    assert "multi_carrier_vs_zeta" in out
    assert "gue" in out["multi_carrier_vs_zeta"]
    mc = out["multi_carrier_vs_zeta"]["gue"]
    assert "or_fusion" in mc and "and_fusion" in mc
    assert out["ontology"].endswith("not_lambda_eq_gamma")
    # dual-gate still locked
    p = policy_for(12, base_beta=0.20)
    assert abs(p.soft_T - 0.036) < 1e-12