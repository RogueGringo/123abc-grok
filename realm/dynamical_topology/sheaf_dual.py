"""Optional sheaf dual fingerprint (read-only; never pin / never ACCEPTANCE).

Best-effort: uses realm.sheaf_backend.numpy_connection_laplacian when monodromy
is available; returns None when inputs are missing or the backend fails.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def sheaf_dual_fingerprint(
    N: int | None = None,
    monodromy: np.ndarray | None = None,
) -> dict[str, Any] | None:
    """Spectral-gap co-report from connection Laplacian (informational only).

    Returns ``{gap, note, not_acceptance: True, ...}`` or None if skipped.
    """
    if monodromy is None:
        return None
    try:
        A = np.asarray(monodromy, dtype=float)
    except (TypeError, ValueError):
        return None
    if A.ndim != 2 or A.shape[0] != A.shape[1] or A.size == 0:
        return {
            "gap": None,
            "note": "monodromy not square or empty; sheaf dual skipped",
            "not_acceptance": True,
        }

    d = int(A.shape[0])
    n = int(N) if N is not None else max(3, d + 1)
    if n < 2:
        n = 2

    try:
        from realm.sheaf_backend import numpy_connection_laplacian

        _L, eigs = numpy_connection_laplacian(n, d, A)
        eigs = np.asarray(eigs, dtype=float).ravel()
        # Spectral gap: first positive eigenvalue (H0 ~ kernel at 0 for flat)
        pos = eigs[eigs > 1e-10]
        gap = float(pos[0]) if pos.size else 0.0
        return {
            "gap": gap,
            "n_vertices": n,
            "stalk_dim": d,
            "eigs_head": [float(x) for x in eigs[: min(8, eigs.size)]],
            "note": (
                "Connection-Laplacian spectral gap (read-only dual stalk). "
                "Not ACCEPTANCE; not pin."
            ),
            "not_acceptance": True,
            "backend": "numpy_connection_laplacian",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "gap": None,
            "note": f"sheaf dual unavailable: {exc}",
            "not_acceptance": True,
        }
