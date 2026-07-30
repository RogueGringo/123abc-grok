"""Sheaf defect tracking (local obstruction cocycles)."""

from __future__ import annotations

import numpy as np

from realm.sheaf_defects import (
    adaptive_chord_weight,
    blend_projection_defect,
    ca_to_stalk_section,
    chord_coboundary_residuals,
    defect_report_for_twist,
    edge_coboundary_residuals,
    multi_scale_obstruction,
    softmin_defect_vs_crit,
)


def test_ca_to_stalk_unit_scale():
    t = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.1 * np.sin(3 * t)])
    sec = ca_to_stalk_section(xyz, d=2)
    assert sec.shape == (12, 2)
    rms = float(np.sqrt(np.mean(np.sum(sec**2, axis=1))))
    assert abs(rms - 1.0) < 1e-6


def test_edge_residuals_flat_zero_twist():
    t = np.linspace(0, 2 * np.pi, 10, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), np.zeros(10)])
    sec = ca_to_stalk_section(xyz, d=2)
    A = np.eye(2)
    r = edge_coboundary_residuals(sec, A)
    assert r.shape == (10,)
    # unit-circle PCA section has O(1) chord residuals under identity maps
    assert float(np.mean(r)) < 1.0
    assert float(np.std(r)) < 1e-6  # uniform on regular polygon


def test_defect_report_and_softmin():
    t = np.linspace(0, 2 * np.pi, 11, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.05 * t / (2 * np.pi)])
    rep = defect_report_for_twist(xyz, 0.3, prefer_maxop=False)
    assert rep["dirichlet_energy"] >= 0.0
    assert rep["augmented_energy"] >= rep["dirichlet_energy"] - 1e-12
    assert len(rep["edge_residuals"]) == 11
    assert "multi_scale" in rep
    # n=11 → pure edge Dirichlet (adaptive chord_weight=0)
    assert rep["chord_weight"] == 0.0
    sm = softmin_defect_vs_crit(
        xyz, [0.2, 0.5, 1.0, 2.0], soft_T=0.05, prefer_maxop=False
    )
    assert sm["mean_dist"] >= sm["min_dist"] - 1e-12
    assert sm["method"] == "SHEAF_DEFECT_SOFTMIN"


def test_chord_and_multi_scale():
    t = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.05 * np.sin(2 * t)])
    sec = ca_to_stalk_section(xyz, d=2)
    A = np.eye(2)
    r2 = chord_coboundary_residuals(sec, A, hop=2)
    assert r2.shape == (12,)
    assert float(np.mean(r2)) > 0.0
    ms = multi_scale_obstruction(sec, A, hops=(1, 2, 3))
    assert ms["combined_strain"] > 0.0
    assert "hop2_mean" in ms["means"]
    assert adaptive_chord_weight(10) == 0.0
    assert adaptive_chord_weight(12) == 0.18
    assert adaptive_chord_weight(13) == 0.25
    # n=13 activates multi-scale method tag
    t13 = np.linspace(0, 2 * np.pi, 13, endpoint=False)
    xyz13 = np.column_stack([np.cos(t13), np.sin(t13), 0.05 * np.sin(2 * t13)])
    sm13 = softmin_defect_vs_crit(
        xyz13, [0.2, 0.8, 1.5], soft_T=0.05, prefer_maxop=False
    )
    assert sm13["method"] == "SHEAF_DEFECT_MULTISCALE"
    assert sm13["chord_weight"] == 0.25


def test_blend_projection_primary():
    assert abs(blend_projection_defect(0.5, 2.0, beta=0.0) - 0.5) < 1e-12
    b = blend_projection_defect(0.5, 2.0, beta=0.1)
    assert 0.4 < b < 0.6
    b2 = blend_projection_defect(0.5, 2.0, beta=0.1, scale=0.18)
    assert b2 != b
