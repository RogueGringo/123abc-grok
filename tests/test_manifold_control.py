"""Manifold control tuples + sheaf holonomy feedback."""

from __future__ import annotations

import numpy as np

from realm.manifold_control import (
    fold_control_snapshot,
    holonomy_feedback_step,
    multi_step_holonomy_control,
    sheaf_energy_at_twist,
)


def test_fold_control_architecture_card():
    card = fold_control_snapshot()
    assert "connes_proxy" in card
    assert "control_affine_Sigma" in card
    assert "sheaf_S" in card
    assert "never_lambda_eq_gamma" in card["allen_connes_discipline"]
    assert "lambda_eq_gamma" in card["connes_proxy"]["never"]


def test_holonomy_feedback_moves_or_stays():
    t = np.linspace(0, 2 * np.pi, 11, endpoint=False)
    xyz = np.column_stack([np.cos(t), np.sin(t), 0.05 * np.sin(2 * t)])
    e0 = sheaf_energy_at_twist(xyz, 0.5, prefer_maxop=False)
    assert e0 >= 0.0
    step = holonomy_feedback_step(xyz, 0.5, step=0.08, prefer_maxop=False)
    assert "u" in step
    assert step["E_out"] >= 0.0
    traj = multi_step_holonomy_control(
        xyz, 0.5, n_steps=4, step=0.08, prefer_maxop=False
    )
    assert traj["n_steps"] >= 1
    assert traj["E_final"] is not None
