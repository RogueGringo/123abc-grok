"""Physics rollup + geometry self-check tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from realm.handoff.physics import (
    GeometrySelfCheck,
    rollup_physics_reports,
    scan_physics_tree,
    write_physics_rollup,
)
from realm.validate.pdb_write import write_mold_pair


def test_geometry_self_check_ok(tmp_path: Path):
    # regular cyclic CA hexagon-ish ring ~3.8 A edges
    n = 8
    r = 3.8 / (2 * np.sin(np.pi / n))
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    xyz = np.column_stack([r * np.cos(th), r * np.sin(th), np.zeros(n)])
    molds = tmp_path / "molds"
    molds.mkdir()
    paths = write_mold_pair(
        molds, "000_crit", xyz, source="crit", rank_score=0.1, method="test"
    )
    rep = GeometrySelfCheck().filter(Path(paths["path_bb"]))
    assert rep.status in ("OK", "WARN")
    assert rep.metrics.get("n_ca") == n
    assert abs(float(rep.metrics["ca_bond_mean"]) - 3.8) < 0.5


def test_rollup_and_scan(tmp_path: Path):
    n = 6
    r = 3.8 / (2 * np.sin(np.pi / n))
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    xyz = np.column_stack([r * np.cos(th), r * np.sin(th), np.zeros(n)])
    molds = tmp_path / "molds"
    molds.mkdir()
    write_mold_pair(molds, "000_crit", xyz, source="crit", rank_score=0.1, method="t")
    write_mold_pair(molds, "001_crit", xyz * 1.01, source="crit", rank_score=0.2, method="t")

    rollup = scan_physics_tree(tmp_path)
    assert rollup.get("ok") is True
    assert int(rollup.get("n_reports") or 0) == 2
    assert (tmp_path / "PHYSICS_ROLLUP.json").is_file()
    assert (tmp_path / "PHYSICS_ROLLUP.md").is_file()
    text = (tmp_path / "PHYSICS_ROLLUP.md").read_text(encoding="utf-8")
    assert "not" in text.lower() and "ACCEPTANCE" in text


def test_rollup_counts():
    reports = [
        {"status": "OK", "metrics": {"ca_bond_mean": 3.8, "ca_bond_std": 0.1}, "stem": "a"},
        {
            "status": "WARN",
            "metrics": {"ca_bond_mean": 4.5, "ca_bond_std": 0.7},
            "stem": "b",
            "notes": ["far"],
        },
        {"status": "FAIL", "metrics": {}, "stem": "c", "notes": ["missing"]},
    ]
    r = rollup_physics_reports(reports, scope="test")
    assert r["n_ok"] == 1 and r["n_warn"] == 1 and r["n_fail"] == 1
    assert r["mean_ca_bond"] is not None


def test_handoff_physics_cli(tmp_path: Path):
    from handoff_physics import main

    n = 6
    r = 3.8 / (2 * np.sin(np.pi / n))
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    xyz = np.column_stack([r * np.cos(th), r * np.sin(th), np.zeros(n)])
    molds = tmp_path / "molds"
    molds.mkdir()
    write_mold_pair(molds, "000_crit", xyz, source="crit", rank_score=0.1, method="t")
    rc = main([str(tmp_path)])
    assert rc == 0
    data = json.loads((tmp_path / "PHYSICS_ROLLUP.json").read_text(encoding="utf-8"))
    assert data["n_reports"] >= 1
