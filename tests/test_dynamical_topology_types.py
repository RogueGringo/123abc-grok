from realm.dynamical_topology.types import Stage, empty_report, finalize_report
import numpy as np

def test_empty_report_guards():
    r = empty_report()
    assert r["kind"] == "dynamical_topology"
    assert r["not_acceptance"] is True
    assert r["pin_writable"] is False
    assert r["acceptance_writable"] is False
    assert "2410.11042" in r["kb_source"]

def test_finalize_forces_guards():
    bad = {"kind": "dynamical_topology", "not_acceptance": False, "pin_writable": True}
    r = finalize_report(bad)
    assert r["not_acceptance"] is True
    assert r["pin_writable"] is False

def test_stage_holds_points():
    s = Stage(index=0, label="s0", points=np.zeros((3, 2)))
    assert s.points.shape == (3, 2)
