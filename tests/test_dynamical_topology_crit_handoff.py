"""Task 5: Crit + handoff stage builders + sheaf dual (measure-only)."""

from __future__ import annotations

import numpy as np

from realm.dynamical_topology.engine import run_dynamical_topology
from realm.dynamical_topology.stages_crit import build_stages_from_crit_filtration
from realm.dynamical_topology.stages_handoff import build_stages_from_handoff_ledger
from realm.dynamical_topology.sheaf_dual import sheaf_dual_fingerprint


def _assert_report_guards(rep: dict) -> None:
    assert rep["not_acceptance"] is True
    assert rep["pin_writable"] is False
    assert rep["acceptance_writable"] is False
    assert rep.get("kind") == "dynamical_topology"


def test_handoff_ledger_stages_run_dynamical_topology():
    ledger = [
        {
            "round": 1,
            "params": {"decorate": "null", "physics": "geometry", "top_k": 2},
            "coherence_score": 0.4,
        },
        {
            "round": 2,
            "params": {"decorate": "sequence", "physics": "geometry", "top_k": 3},
            "coherence_score": 0.7,
        },
        {
            "round": 3,
            "params": {"decorate": "sequence", "physics": "none", "top_k": 4},
            "coherence_score": 0.9,
        },
        # non-round entries must be ignored
        {"round": "genotype", "params": {"decorate": "sequence"}},
        {"action": "note", "msg": "skip"},
    ]
    stages = build_stages_from_handoff_ledger(ledger)
    assert len(stages) == 3
    for st in stages:
        assert st.points.ndim == 2
        assert st.points.shape[0] >= 1
        assert st.points.shape[1] >= 1
        assert np.all(np.isfinite(st.points))

    rep = run_dynamical_topology(stages)
    _assert_report_guards(rep)
    assert rep["n_stages"] == 3


def test_crit_filtration_stages_nonempty_and_guards():
    # Synthetic diagram_H0 persistence series (birth-ordered bars)
    diagram = [
        {"birth": 0.0, "death": 0.5, "persistence": 0.5},
        {"birth": 0.1, "death": 1.2, "persistence": 1.1},
        {"birth": 0.2, "death": 0.3, "persistence": 0.1},
        {"birth": 0.4, "death": 2.0, "persistence": 1.6},
        {"birth": 0.5, "death": 0.8, "persistence": 0.3},
        {"birth": 0.6, "death": 1.5, "persistence": 0.9},
        {"birth": 0.7, "death": 0.9, "persistence": 0.2},
        {"birth": 0.8, "death": 2.5, "persistence": 1.7},
    ]
    filt = {
        "diagram_H0": diagram,
        "s_min": 0.0,
        "s_max": 2.5,
        "n_persistent": 3,
        "max_persistence": 1.7,
    }
    stages = build_stages_from_crit_filtration(filt)
    assert len(stages) >= 1
    for st in stages:
        assert st.points.ndim == 2
        assert st.points.shape[0] >= 1
        assert np.all(np.isfinite(st.points))

    rep = run_dynamical_topology(stages)
    _assert_report_guards(rep)
    assert rep["n_stages"] >= 1


def test_crit_filtration_S_samples_fallback():
    # No diagram_H0; use S samples along grid as stages
    S = list(np.sin(np.linspace(0, 2 * np.pi, 24)))
    filt = {"S": S, "s_min": float(min(S)), "s_max": float(max(S))}
    stages = build_stages_from_crit_filtration(filt)
    assert len(stages) >= 1
    rep = run_dynamical_topology(stages)
    _assert_report_guards(rep)


def test_crit_empty_filtration_returns_empty_or_safe():
    stages = build_stages_from_crit_filtration({})
    assert isinstance(stages, list)
    rep = run_dynamical_topology(stages)
    _assert_report_guards(rep)


def test_sheaf_dual_no_crash_and_not_acceptance_or_none():
    # No monodromy → None or dict with not_acceptance
    out = sheaf_dual_fingerprint(N=None, monodromy=None)
    assert out is None or (
        isinstance(out, dict) and out.get("not_acceptance") is True
    )

    # With monodromy: dict fingerprint or None; never crash
    A = np.array([[0.0, -1.0], [1.0, 0.0]], dtype=float)  # 90° rotation SO(2)
    out2 = sheaf_dual_fingerprint(N=4, monodromy=A)
    assert out2 is None or (
        isinstance(out2, dict)
        and out2.get("not_acceptance") is True
        and "gap" in out2
    )


def test_handoff_empty_ledger():
    stages = build_stages_from_handoff_ledger([])
    assert stages == []
    rep = run_dynamical_topology(stages)
    _assert_report_guards(rep)
    assert rep["n_stages"] == 0
