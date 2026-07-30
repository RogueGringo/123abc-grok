"""Sequence chemistry → discrete stalk conditioning (not HF language models).

Maps residue names to fixed physicochemical features used to reweight local
sheaf obstruction. Geometry (Crit Kabsch) stays projection-primary; sequence
only modulates the sheaf dual. Never λ=γ.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

# Kyte–Doolittle hydrophobicity (classic scale)
_KD: dict[str, float] = {
    "ILE": 4.5,
    "VAL": 4.2,
    "LEU": 3.8,
    "PHE": 2.8,
    "CYS": 2.5,
    "MET": 1.9,
    "ALA": 1.8,
    "GLY": -0.4,
    "THR": -0.7,
    "SER": -0.8,
    "TRP": -0.9,
    "TYR": -1.3,
    "PRO": -1.6,
    "HIS": -3.2,
    "GLU": -3.5,
    "GLN": -3.5,
    "ASP": -3.5,
    "ASN": -3.5,
    "LYS": -3.9,
    "ARG": -4.5,
}

# Residue volume proxy (Å³, approximate side-chain bulk)
_VOL: dict[str, float] = {
    "GLY": 60.0,
    "ALA": 88.0,
    "SER": 89.0,
    "CYS": 108.0,
    "ASP": 111.0,
    "THR": 116.0,
    "ASN": 114.0,
    "PRO": 112.0,
    "VAL": 140.0,
    "GLU": 138.0,
    "GLN": 143.0,
    "HIS": 153.0,
    "MET": 162.0,
    "ILE": 166.0,
    "LEU": 166.0,
    "LYS": 168.0,
    "ARG": 173.0,
    "PHE": 189.0,
    "TYR": 193.0,
    "TRP": 227.0,
}

# Formal charge at neutral pH
_CHARGE: dict[str, float] = {
    "ASP": -1.0,
    "GLU": -1.0,
    "LYS": 1.0,
    "ARG": 1.0,
    "HIS": 0.1,
}

# Non-standard / common cyclic-peptide residues (mild defaults)
_KD_EXTRA: dict[str, float] = {
    "MSE": 1.9,
    "SEC": 2.5,
    "PYL": -3.9,
    "MLE": 3.8,  # N-methyl leucine
    "NLE": 3.8,
    "MVA": 4.2,  # N-methyl valine ~ Val
    "BMT": 3.5,  # butenyl-methyl-threonine (CsA) — hydrophobic
    "ABA": 1.5,  # alpha-aminobutyric ~ mild Ala
    "AIB": 1.0,
    "SAR": -0.4,
    "ORN": -3.5,
    "DAB": -3.5,
    "HYP": -1.6,
    "DAL": 1.8,
    "DSN": -0.8,
}
_VOL_EXTRA: dict[str, float] = {
    "MLE": 175.0,
    "NLE": 166.0,
    "MVA": 150.0,
    "BMT": 180.0,
    "ABA": 105.0,
    "AIB": 100.0,
    "SAR": 70.0,
    "MSE": 162.0,
}


def normalize_resname(name: str) -> str:
    s = str(name or "").strip().upper()
    if not s:
        return "UNK"
    if s.startswith("D") and len(s) == 4 and s[1:] in _KD:
        return s[1:]
    return s


def aa_feature_vector(resname: str) -> np.ndarray:
    """3-vector: hydrophobicity, volume, charge (raw scales)."""
    r = normalize_resname(resname)
    h = float(_KD.get(r, _KD_EXTRA.get(r, 0.0)))
    if r in _VOL:
        v = float(_VOL[r])
    elif r in _VOL_EXTRA:
        v = float(_VOL_EXTRA[r])
    elif r in _KD_EXTRA:
        v = 140.0
    else:
        v = 120.0
    c = float(_CHARGE.get(r, 0.0))
    return np.array([h, v, c], dtype=float)


def aa_feature_matrix(resnames: Sequence[str]) -> np.ndarray:
    """Stack per-residue features → (n, 3)."""
    if not resnames:
        return np.zeros((0, 3), dtype=float)
    return np.vstack([aa_feature_vector(r) for r in resnames])


def sequence_residue_weights(
    resnames: Sequence[str] | None,
    *,
    mix: float = 0.0,
) -> np.ndarray | None:
    """Positive unit-mean weights from hydrophobicity (+ mild volume).

    w_i = 1 + mix * z(h_i + 0.25 z(vol_i)), renormalized to mean 1.
    mix=0 or missing sequence → None (uniform sheaf defects).
    """
    m = float(max(0.0, min(1.0, mix)))
    if m <= 1e-12 or not resnames:
        return None
    feats = aa_feature_matrix(resnames)
    h = feats[:, 0]
    v = feats[:, 1]
    h_z = (h - float(np.mean(h))) / (float(np.std(h)) + 1e-9)
    v_z = (v - float(np.mean(v))) / (float(np.std(v)) + 1e-9)
    raw = h_z + 0.25 * v_z
    w = 1.0 + m * raw
    w = np.clip(w, 0.25, 4.0)
    w = w / (float(np.mean(w)) + 1e-15)
    return w.astype(float)


def apply_residue_weights_to_edge_residuals(
    residuals: np.ndarray,
    weights: np.ndarray | None,
) -> np.ndarray:
    """Weight edge i→i+1 residual by mean endpoint weight."""
    r = np.asarray(residuals, dtype=float).ravel()
    if weights is None:
        return r
    w = np.asarray(weights, dtype=float).ravel()
    if w.size != r.size:
        return r
    out = r.copy()
    n = r.size
    for i in range(n):
        out[i] = r[i] * 0.5 * (w[i] + w[(i + 1) % n])
    return out


def apply_residue_weights_to_vertex_residuals(
    residuals: np.ndarray,
    weights: np.ndarray | None,
) -> np.ndarray:
    """Weight per-vertex residual (faces/chords) by local residue weight."""
    r = np.asarray(residuals, dtype=float).ravel()
    if weights is None:
        return r
    w = np.asarray(weights, dtype=float).ravel()
    if w.size != r.size:
        return r
    return r * w
