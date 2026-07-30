from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from realm.handoff.decorate import NullDecorateAdapter, PolyAlaStubAdapter, select_adapter
from realm.handoff.physics import GeometrySelfCheck, get_physics_adapter
from realm.handoff.types import BackboneArtifact, DecorateRequest
from realm.validate.pdb_write import write_mold_pair


def _ring(n: int = 8) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([3.8 * np.cos(t), 3.8 * np.sin(t), 0.05 * np.sin(2 * t)])


def test_decorate_null_skip(tmp_path: Path):
    paths = write_mold_pair(tmp_path, "m", _ring(8), source="crit", rank_score=0.1)
    art = BackboneArtifact(Path(paths["path_ca"]), Path(paths["path_bb"]))
    res = NullDecorateAdapter().decorate(DecorateRequest(backbone=art))
    assert res.status == "SKIP"
    assert res.path_decorated is None
    assert res.adapter == "null"


def test_decorate_polyala_writes_file(tmp_path: Path):
    paths = write_mold_pair(tmp_path / "molds", "m", _ring(8), source="crit", rank_score=0.1)
    art = BackboneArtifact(Path(paths["path_ca"]), Path(paths["path_bb"]))
    res = PolyAlaStubAdapter().decorate(DecorateRequest(backbone=art, poly_ala=True))
    assert res.status == "OK"
    assert res.path_decorated is not None
    assert res.path_decorated.is_file()
    text = res.path_decorated.read_text(encoding="utf-8")
    assert "CB" in text or " CB " in text


def test_physics_geometry_on_bb(tmp_path: Path):
    paths = write_mold_pair(tmp_path, "m", _ring(10), source="coutsias", rank_score=1.0)
    report = GeometrySelfCheck().filter(Path(paths["path_bb"]))
    assert report.adapter == "geometry_self_check"
    assert report.status in ("OK", "WARN", "FAIL")
    assert "ca_bond_mean" in report.metrics
    assert get_physics_adapter("none") is None
    assert get_physics_adapter("geometry") is not None


def test_select_adapter_null():
    a = select_adapter("null")
    assert a.name == "null"
