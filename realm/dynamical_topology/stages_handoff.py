"""Build dynamical-topology Stage lists from handoff coherence ledgers.

Measure-only: free-param trajectory as discrete time (not pin / not ACCEPTANCE).
Each ledger round → small point cloud from one-hot decorate/physics + top_k.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from realm.dynamical_topology.types import Stage

# Mirror handoff free-param domains (closed sets; import-safe standalone)
DECORATE_ORDER = ("sequence", "polyala", "null")
PHYSICS_ORDER = ("geometry", "none")


def _one_hot(value: str, domain: Sequence[str]) -> list[float]:
    v = str(value or "").lower().strip()
    return [1.0 if v == d else 0.0 for d in domain]


def _params_vector(params: dict[str, Any] | None) -> np.ndarray:
    """Encode free params as a feature vector (decorate oh + physics oh + top_k)."""
    p = params if isinstance(params, dict) else {}
    dec = _one_hot(str(p.get("decorate") or "sequence"), DECORATE_ORDER)
    phys = _one_hot(str(p.get("physics") or "geometry"), PHYSICS_ORDER)
    try:
        top_k = float(p.get("top_k") if p.get("top_k") is not None else 2)
    except (TypeError, ValueError):
        top_k = 2.0
    # Normalize top_k into a mild scale so it does not dominate one-hots
    vec = np.asarray(dec + phys + [top_k / 8.0], dtype=float)
    return vec


def _points_from_params(
    params: dict[str, Any] | None,
    *,
    coherence_score: float | None = None,
) -> np.ndarray:
    """Small (3, d) cloud around free-param encoding so knn/VR can run."""
    base = _params_vector(params)
    d = int(base.shape[0])
    # Optional score as extra dim for trajectory richness
    if coherence_score is not None:
        try:
            sc = float(coherence_score)
        except (TypeError, ValueError):
            sc = 0.0
        if not np.isfinite(sc):
            sc = 0.0
        base = np.concatenate([base, np.asarray([sc], dtype=float)])
        d = int(base.shape[0])

    # Three nearby points (not inventing acceptance — measure embedding only)
    eps = 0.01
    jitter = np.zeros((3, d), dtype=float)
    jitter[0] = base
    jitter[1] = base + eps
    jitter[2] = base - eps
    # Keep one-hot-ish coords non-negative when possible
    jitter = np.where(np.isfinite(jitter), jitter, 0.0)
    return jitter


def build_stages_from_handoff_ledger(ledger: list[dict] | Sequence[dict]) -> list[Stage]:
    """Each ledger entry with integer ``round`` → Stage from free-param encoding.

    Skips genotype / non-int rounds and non-dict entries.
    """
    stages: list[Stage] = []
    for entry in ledger or []:
        if not isinstance(entry, dict):
            continue
        rnd = entry.get("round")
        if not isinstance(rnd, int):
            continue
        params = entry.get("params") or entry.get("next_params") or {}
        if not isinstance(params, dict):
            params = {}
        score = entry.get("coherence_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        pts = _points_from_params(params, coherence_score=score_f)
        stages.append(
            Stage(
                index=len(stages),
                label=f"round_{rnd}",
                points=pts,
            )
        )
    # Re-index for safety
    for i, st in enumerate(stages):
        st.index = i
    return stages
