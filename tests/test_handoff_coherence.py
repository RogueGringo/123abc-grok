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
    nxt, reason, board = negotiate(obs, params, thr, tried=tried)
    assert nxt is not None
    assert nxt.decorate == "sequence"
    assert "sequence" in reason
    assert board and board[0]["section"] == "decorate"


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
    nxt, reason, board = negotiate(obs, params, thr, tried=set())
    assert nxt is None
    assert "pin" in reason
    assert board == []


def test_multi_section_merge_priority():
    from realm.handoff.coherence import collect_section_proposals, merge_proposals

    thr = CoherenceThresholds(require_decorate=True, max_physics_fail=0)
    params = FreeParams(decorate="null", physics="geometry", top_k=2)
    obs = Observations(
        pin_ok=True,
        soft_T=0.036,
        n_ids=2,
        n_export_ok=1,  # incomplete export
        n_pdb_ontology=2,
        verify_ok=True,
        decorate_n_ok=0,
        decorate_n_molds=0,
        decorate_n_paths=0,
        physics_n_ok=0,
        physics_n_warn=0,
        physics_n_fail=1,  # physics wants a move too
        out_dir="/tmp",
        notes=["export_incomplete", "physics_fail", "decorate_zero"],
    )
    tried: set[str] = set()
    props = collect_section_proposals(obs, params, thr, tried=tried)
    sections = {p.section for p in props}
    assert "export" in sections or "decorate" in sections or "physics" in sections
    nxt, reason, board = merge_proposals(props, params)
    assert nxt is not None
    assert reason.startswith("merge[")
    assert len(board) >= 1
    # export priority beats decorate/science when both present
    if any(p.section == "export" for p in props):
        assert "export" in reason


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
