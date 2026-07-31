"""Coherence protocol unit tests (negotiate + observe; no full export)."""

from __future__ import annotations

from realm.handoff.coherence import (
    CoherenceThresholds,
    FreeParams,
    Observations,
    coherence_score,
    is_solved,
    negotiate,
    observe,
)


def test_free_params_clamp():
    p = FreeParams(decorate="weird", physics="nope", top_k=99).clamp()
    assert p.decorate == "sequence"
    assert p.physics == "geometry"
    assert p.top_k == 8


def test_is_solved_and_score():
    thr = CoherenceThresholds()
    params = FreeParams(decorate="sequence", physics="geometry", top_k=2)
    good = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=1,
        n_export_ok=1,
        n_pdb_ontology=4,
        verify_ok=True,
        decorate_n_ok=2,
        decorate_n_molds=2,
        decorate_n_paths=2,
        physics_n_ok=2,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
    )
    assert is_solved(good, thr, params) is True
    assert coherence_score(good, thr, params) > 0.9

    bad = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=1,
        n_export_ok=1,
        n_pdb_ontology=4,
        verify_ok=True,
        decorate_n_ok=0,
        decorate_n_molds=2,
        decorate_n_paths=0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
        notes=["decorate_zero"],
    )
    assert is_solved(bad, thr, params) is False


def test_negotiate_enable_sequence():
    thr = CoherenceThresholds(require_decorate=True)
    params = FreeParams(decorate="null", physics="geometry", top_k=2)
    obs = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=1,
        n_export_ok=1,
        n_pdb_ontology=2,
        verify_ok=True,
        decorate_n_ok=0,
        decorate_n_molds=0,
        decorate_n_paths=0,
        physics_n_ok=2,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
        notes=["decorate_zero"],
    )
    assert is_solved(obs, thr, params) is False
    tried: set[str] = set()
    nxt, reason = negotiate(obs, params, thr, tried=tried)
    assert nxt is not None
    assert nxt.decorate == "sequence"
    assert "sequence" in reason


def test_negotiate_never_suggests_pin_change_on_pin_fail():
    thr = CoherenceThresholds()
    params = FreeParams(decorate="null", physics="geometry", top_k=2)
    obs = Observations(
        pin_ok=False,
        soft_T=0.04,
        n_ids=1,
        n_export_ok=0,
        n_pdb_ontology=0,
        verify_ok=False,
        decorate_n_ok=0,
        decorate_n_molds=0,
        decorate_n_paths=0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=0,
        out_dir="/tmp",
        notes=["pin_fail"],
    )
    nxt, reason = negotiate(obs, params, thr, tried=set())
    assert nxt is None
    assert "pin" in reason


def test_observe_from_summary():
    pin = {"ok": True, "soft_T": 0.036}
    summary = {
        "n_ids": 2,
        "n_ok": 2,
        "decorate_rollup": {"n_ok": 4, "n_with_path": 4, "n_molds": 4},
        "physics_rollup": {"n_ok": 4, "n_warn": 0, "n_fail": 0},
    }
    v = {"ok": True, "ontology_remarks": {"n_pdb": 8}}
    obs = observe(pin=pin, export_summary=summary, verify_report=v, out_dir="/x")
    assert obs.pin_ok and obs.n_export_ok == 2
    assert obs.decorate_n_ok == 4
    assert obs.physics_n_fail == 0
