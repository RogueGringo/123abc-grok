"""Sharp modality backends: MaxOp CellularSheaf if available, else pure numpy.

MaxOp lives at PRIMEdEV-1/primed-topology. We try to import it; on failure we
build an equivalent cycle connection Laplacian matching realm.cohesive.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import eigh

logger = logging.getLogger(__name__)

_MAXOP_PATHS = [
    Path(__file__).resolve().parents[2] / "primed-topology" / "src",
    Path(r"C:\PRIMEdEV-1\primed-topology\src"),
]


def _try_import_maxop():
    for p in _MAXOP_PATHS:
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        from maxop.sheaf import CellularSheaf  # type: ignore

        return CellularSheaf
    except Exception as exc:  # noqa: BLE001
        logger.info("MaxOp CellularSheaf unavailable (%s); using numpy sharp backend", exc)
        return None


CellularSheaf = _try_import_maxop()


def numpy_connection_laplacian(N: int, d: int, monodromy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    A = np.asarray(monodromy, dtype=float)
    dim = N * d
    L = np.zeros((dim, dim), dtype=float)
    I = np.eye(d, dtype=float)
    for i in range(N):
        j = (i + 1) % N
        bi, bj = i * d, j * d
        L[bi : bi + d, bi : bi + d] += I
        L[bj : bj + d, bj : bj + d] += I
        if i == N - 1:
            L[bi : bi + d, bj : bj + d] -= A
            L[bj : bj + d, bi : bi + d] -= A.T
        else:
            L[bi : bi + d, bj : bj + d] -= I
            L[bj : bj + d, bi : bi + d] -= I
    L = 0.5 * (L + L.T)
    eigs = np.sort(np.real(eigh(L, eigvals_only=True)))
    return L, eigs


def maxop_connection_laplacian(N: int, d: int, monodromy: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Encode cycle monodromy as a cellular sheaf L_F = δ*δ.

    Restriction maps:
      ordinary edge (i → i+1): F(i≤e)=I, F(i+1≤e)=I  (constant sheaf)
      cut edge (N-1 → 0): F(N-1≤e)=I, F(0≤e)=A
    so the coboundary on the cut measures x_0 - A x_{N-1}.
    """
    if CellularSheaf is None:
        raise RuntimeError("MaxOp not available")

    A = np.asarray(monodromy, dtype=float)
    I = np.eye(d, dtype=float)
    vertex_stalks = {i: d for i in range(N)}
    edges: list[tuple[int, int]] = []
    edge_stalks: dict[tuple[int, int], int] = {}
    restriction_maps: dict[tuple[tuple[int, int], int], np.ndarray] = {}

    for i in range(N):
        j = (i + 1) % N
        e = (i, j)
        edges.append(e)
        edge_stalks[e] = d
        if i == N - 1:
            # coboundary: F(j)x_j - F(i)x_i = A x_0 - I x_{N-1} ? 
            # MaxOp: (delta x)(e) = F(v<=e) x_v - F(u<=e) x_u for e=(u,v)
            # Want twist on cut: x_0 - A x_{N-1}
            restriction_maps[(e, i)] = A.copy()  # u = N-1
            restriction_maps[(e, j)] = I.copy()  # v = 0
        else:
            restriction_maps[(e, i)] = I.copy()
            restriction_maps[(e, j)] = I.copy()

    sheaf = CellularSheaf(
        vertex_stalks=vertex_stalks,
        edges=edges,
        edge_stalks=edge_stalks,
        restriction_maps=restriction_maps,
    )
    L = sheaf.laplacian()
    L = 0.5 * (L + L.T)
    eigs = np.sort(np.real(np.linalg.eigvalsh(L)))
    meta = {
        "backend": "maxop.CellularSheaf",
        "spectral_gap_api": float(sheaf.spectral_gap()),
        "h0_dim": int(sheaf.global_sections_basis().shape[1]),
    }
    return L, eigs, meta


def sharp_laplacian(
    N: int,
    d: int,
    monodromy: np.ndarray,
    prefer_maxop: bool = True,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Dispatch sharp modality to MaxOp or numpy."""
    if prefer_maxop and CellularSheaf is not None:
        try:
            L, eigs, meta = maxop_connection_laplacian(N, d, monodromy)
            logger.info(
                "Sharp backend=MaxOp gap_api=%.6g H0_dim=%d",
                meta["spectral_gap_api"],
                meta["h0_dim"],
            )
            return L, eigs, meta
        except Exception as exc:  # noqa: BLE001
            logger.warning("MaxOp sharp failed (%s); falling back to numpy", exc)
    L, eigs = numpy_connection_laplacian(N, d, monodromy)
    meta = {"backend": "numpy.connection_laplacian", "spectral_gap_api": None, "h0_dim": None}
    logger.info("Sharp backend=numpy")
    return L, eigs, meta
