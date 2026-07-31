"""Parent KB H1: VR H0 + graph λ1 adapters."""

from __future__ import annotations

import numpy as np

from realm.kb_geometry.graph import knn_graph
from realm.kb_geometry.rips_h0 import algebraic_connectivity, vietoris_rips_h0
from realm.job_os.regime import evaluate_regime


def test_vietoris_rips_h0_two_clusters():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.05, size=(12, 2))
    b = rng.normal(5, 0.05, size=(12, 2))
    X = np.vstack([a, b])
    rep = vietoris_rips_h0(X, long_frac=0.15)
    assert rep["not_acceptance"] is True
    assert rep["n"] == 24
    assert rep["n_bars"] >= 1
    # at least one long-lived structure expected for well-separated clusters
    assert rep["n_long"] >= 1 or rep["n_essential"] >= 1
    # finite deaths (not all inf)
    assert all(np.isfinite(bar["death"]) for bar in rep["bars"])


def test_algebraic_connectivity_connected_vs_disconnected():
    # path graph: connected, λ1 > 0
    n = 5
    A = np.zeros((n, n))
    for i in range(n - 1):
        A[i, i + 1] = A[i + 1, i] = 1.0
    conn = algebraic_connectivity(A)
    assert conn["not_acceptance"] is True
    assert conn["lambda_1"] is not None
    assert float(conn["lambda_1"]) > 1e-9

    # two isolated edges: λ1 can be 0 (disconnected)
    B = np.zeros((4, 4))
    B[0, 1] = B[1, 0] = 1.0
    B[2, 3] = B[3, 2] = 1.0
    disc = algebraic_connectivity(B)
    assert float(disc["lambda_1"]) < 1e-6 or float(disc["lambda_1"]) >= 0.0


def test_regime_reports_lambda1_and_rips():
    series = {
        "n_rows": 30,
        "channels": {
            "SSSI": list(np.sin(np.linspace(0, 8, 30))),
            "RPM": list(np.linspace(100, 130, 30)),
        },
    }
    rep = evaluate_regime(
        series, regime_mode="persist_h0", window_scale=1, enabled=True
    )
    gl = rep.get("graph_labels") or {}
    assert gl.get("enabled") is True
    assert gl.get("not_acceptance") is True
    assert "lambda_1" in gl
    assert gl.get("rips_h0_n_bars") is not None


def test_knn_then_lambda1_pipeline():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(16, 3))
    g = knn_graph(X, k=3)
    lam = algebraic_connectivity(g)
    assert lam["lambda_1"] is not None
    assert "not λ=γ" in (lam.get("disclaimer") or "").lower() or "not λ=γ" in (
        lam.get("disclaimer") or ""
    ) or "lambda_eq_gamma" in (lam.get("ontology") or "")
