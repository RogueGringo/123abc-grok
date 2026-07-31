"""KB geometry P3–P6: graph, multi-scale regime, chunk inspect."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from realm.kb_geometry.graph import knn_graph, series_point_cloud, spectral_labels
from realm.kb_geometry.science_annex import is_informational_only
from realm.job_os.chunk_inspect import (
    aggregate_chunk_inspect,
    iter_las_chunks,
    run_las_chunk_inspect,
)
from realm.job_os.ingest_las import parse_las
from realm.job_os.regime import evaluate_regime
from realm.job_os.types import FreeParams, JobThresholds


def test_knn_two_blobs_and_spectral():
    rng = np.random.default_rng(1)
    a = rng.normal(0, 0.1, size=(20, 2))
    b = rng.normal(3, 0.1, size=(20, 2))
    X = np.vstack([a, b])
    g = knn_graph(X, k=4)
    assert g["n"] == 40
    assert g["n_edges"] > 0
    assert g["not_acceptance"] is True
    lab = spectral_labels(g, n_clusters=2, seed=0)
    assert lab["not_acceptance"] is True
    labels = lab["labels"]
    assert len(labels) == 40
    # roughly two clusters: majority label of first 20 != majority of last 20
    from collections import Counter

    c0 = Counter(labels[:20]).most_common(1)[0][0]
    c1 = Counter(labels[20:]).most_common(1)[0][0]
    assert c0 != c1


def test_series_point_cloud():
    ch = {"SSSI": list(range(10)), "RPM": list(range(10, 20))}
    X = series_point_cloud(ch, max_points=8)
    assert X.shape[0] == 8
    assert X.shape[1] == 2


def test_regime_multi_scale_and_graph_info():
    series = {
        "n_rows": 40,
        "channels": {
            "SSSI": list(np.sin(np.linspace(0, 6, 40))),
            "RPM": list(np.linspace(100, 140, 40)),
            "TOR": list(np.cos(np.linspace(0, 6, 40))),
        },
    }
    rep = evaluate_regime(
        series, regime_mode="persist_h0", window_scale=2, enabled=True
    )
    assert rep["enabled"] is True
    assert rep["not_acceptance"] is True
    ms = rep.get("multi_scale") or {}
    assert ms.get("enabled") is True
    assert ms.get("not_acceptance") is True
    assert "n_long" in ms
    gl = rep.get("graph_labels") or {}
    assert gl.get("enabled") is True
    assert gl.get("not_acceptance") is True
    # flipping labels must not be in is_solved path — structure only present
    assert "structure_score" in rep


def test_chunk_inspect_on_fixture():
    las = Path("tests/fixtures/mini_edr.las")
    rep = run_las_chunk_inspect(
        las, chunk_rows=5, max_chunks=10, pack="surface_min"
    )
    assert rep["not_acceptance"] is True
    assert is_informational_only(rep)
    assert rep["n_chunks"] >= 1
    assert rep["rows_covered"] > 0
    assert "n_chunks_pin_ok" in rep


def test_parse_las_max_rows_cap():
    las = Path("tests/fixtures/mini_edr.las")
    full = parse_las(las)
    capped = parse_las(las, max_rows=5)
    assert capped["n_rows"] == 5
    assert capped["truncated"] is True
    assert full["n_rows"] >= capped["n_rows"]


def test_iter_chunks_aggregate():
    las = Path("tests/fixtures/mini_edr.las")
    series = parse_las(las)
    chunks = list(iter_las_chunks(series, chunk_rows=6, max_chunks=4))
    assert len(chunks) >= 1
    from realm.job_os.chunk_inspect import inspect_chunk

    reports = [inspect_chunk(c, pack="surface_min") for c in chunks]
    agg = aggregate_chunk_inspect(
        reports,
        parent_n_rows=int(series["n_rows"]),
        chunk_rows=6,
        max_chunks=4,
    )
    assert agg["n_chunks"] == len(reports)
    assert agg["not_acceptance"] is True


def test_job_loop_chunk_and_regime(tmp_path):
    from realm.job_os.loop import run_job_coherence_loop

    result = run_job_coherence_loop(
        las_path=Path("tests/fixtures/mini_edr.las"),
        out_root=tmp_path / "job",
        initial=FreeParams(
            align_mode="depth_primary",
            channel_pack="surface_min",
            null_policy="mark_only",
            regime_mode="persist_h0",
            window_scale=1,
        ),
        thresholds=JobThresholds(require_pin=True),
        max_rounds=2,
        os_mode=True,
        run_id="kb_p3p6",
        with_regime=True,
        with_science=True,
        chunk_rows=8,
        max_chunks=4,
        stability_k=1,
    )
    assert (Path(result["out_root"]) / "CHUNK_INSPECT.json").is_file()
    body = json.loads(
        (Path(result["out_root"]) / "CHUNK_INSPECT.json").read_text(encoding="utf-8")
    )
    assert body["not_acceptance"] is True
    assert result.get("chunk_inspect") is not None
    # science annex for chunks when with_science
    sci = Path(result["out_root"]) / "CHUNK_SCIENCE_ANNEX.json"
    assert sci.is_file()
    sci_body = json.loads(sci.read_text(encoding="utf-8"))
    assert sci_body["not_acceptance"] is True
    # regime multi-scale on a cycle
    cycles = list(Path(result["out_root"]).glob("cycle_*/regime_report.json"))
    assert cycles
    reg = json.loads(cycles[0].read_text(encoding="utf-8"))
    assert (reg.get("multi_scale") or {}).get("enabled") is True
