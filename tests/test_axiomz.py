"""AXiomZ bridge + Crit filtration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.axiomz import (
    activation_signature,
    basin_persistence_weights,
    crit_action_filtration,
    load_mapping,
    run_term_series,
)
from realm.lock_key import Keymaker


def test_mapping_loads():
    m = load_mapping()
    assert m.get("activations")
    ids = {a["axiom_id"] for a in m["activations"]}
    assert "5.2" in ids
    assert "G1" in ids


def test_activation_signature():
    sig = activation_signature("unit", ["G1", "5.2"])
    assert "G1" in sig["axioms_invoked"]
    assert sig["ontology"] == "not_lambda_eq_gamma"


def test_crit_filtration_finds_structure():
    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(**kn)
    filt = crit_action_filtration(der.action, n_grid=800, n_levels=20)
    assert filt["n_features"] >= 1
    assert filt["max_persistence"] > 0


def test_basin_persistence_weights():
    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    der = Keymaker(N=13, n_zeros=14, n_sectors=6).forge(**kn)
    th = [float(s.twist) for s in der.sectors]
    w = basin_persistence_weights(der.action, th, n_grid=800)
    assert w.shape == (len(th),)
    assert abs(float(w.mean()) - 1.0) < 1e-6
    assert float(w.min()) > 0.0


def test_term_series_five_stages():
    kn_path = Path("evolve_result.json")
    if not kn_path.is_file():
        pytest.skip("need evolve_result.json")
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    out = run_term_series(kn, N=11, n_zeros=14, n_sectors=6, prefer_maxop=False)
    assert len(out["cts"]) == 5
    names = [s["stage"] for s in out["cts"]]
    assert names == ["substrate", "dynamics", "geometry", "topology", "quale"]
    # informative R should exceed legacy seating when dens-return is nonzero
    q = out["cts"][4]
    assert q["R_informative"] >= q["R_legacy_seating"] - 1e-9
