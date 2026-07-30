"""Length-scoped ranking policy — single table of truth for n_ca levers.

All length special-cases (sectors, ω bank, defect β, mold ties, height refine,
Coutsias scope, MaxOp×CTS gap mix, hard-min pull, sheaf chord/scale) live here.
Callers read a LengthPolicy; they do not re-branch on PDB folklore.

Math is dual-gate locked (production 40×3 baseline). New topological levers
extend this table — they do not re-scatter ifs into rank_one / dual_score.

Ontology: ζ substrate only; projection-primary; never λ=γ.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DENSE_OMEGA: tuple[float, ...] = (0.85, 0.95, 1.0, 1.1, 1.2)
# 4M6E mild bridges (n=8 expansion dual-gate regressed holdout)
MILD_OMEGA: tuple[float, ...] = (0.85, 0.90, 0.95, 1.0, 1.1, 1.15, 1.2)
# 1TET/4K8Y-class full wings
FULL_OMEGA: tuple[float, ...] = (
    0.80,
    0.85,
    0.90,
    0.95,
    1.0,
    1.05,
    1.1,
    1.15,
    1.2,
    1.3,
)

# Shared production kwargs for all CLIs that call rank_one.
PRODUCTION_RANK: dict[str, Any] = {
    "sectors_mode": "adaptive",
    "multimode_mode": "self_fit_dense",
    "defect_beta": 0.20,
    "soft_T": 0.04,
    "alpha_proj": 1.0,
    "aggregate": "softmin",
    "holonomy_polish": False,
    "coutsias_alpha": 0.0,
}


@dataclass(frozen=True)
class LengthPolicy:
    """Structure-conditioned ranking levers for a CA ring length."""

    n_ca: int
    n_sectors: int
    defect_beta: float
    omega_scales: tuple[float, ...]
    defect_tie: bool
    height_refine: bool
    coutsias_scope: bool
    gap_mix: float
    hardmin_mix: float
    chord_weight: float
    defect_scale: float
    face_weight: float  # 2-simplex sheaf face strain (0 = baseline 1-skeleton only)
    seq_mix: float  # sequence → sheaf score residual weights (prod 0)
    seq_mold_mix: float  # sequence → mold defect_tie only (not score)
    soft_T: float  # Crit softmin temperature (length-adaptive)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["omega_scales"] = list(self.omega_scales)
        return d


def adaptive_defect_beta(n_ca: int, base: float = 0.20) -> float:
    """Length-adaptive sheaf-defect blend (mid-length floors). Dual-gate locked."""
    b = float(max(0.0, min(1.0, base)))
    if b <= 1e-12:
        return 0.0
    n = int(n_ca)
    if n >= 13:
        return float(min(0.34, b + 0.10))
    if n >= 12:
        return float(min(0.30, b + 0.08))
    if n == 10:
        return float(min(0.26, b + 0.04))  # 4M6E mild
    return b


def mid_length_omega_bank(n_ca: int) -> tuple[float, ...]:
    """Length-adaptive omega bank (superset of production dense)."""
    n = int(n_ca)
    if n >= 12:
        return FULL_OMEGA
    if n == 10:
        return MILD_OMEGA
    return DENSE_OMEGA


def sectors_for_ca_length(
    n_ca: int, mode: str = "fixed", default: int = 6
) -> int:
    """Crit sector count from ring length (projection mold capacity).

    adaptive: n≤8 → 4; n==12 → 4 (1TET-class); else → 6 (cap-6).
    fixed: always ``default``.
    """
    mode = str(mode or "fixed").lower().strip()
    if mode == "adaptive":
        n = int(n_ca)
        if n <= 8:
            return 4
        if n == 12:
            return 4
        return 6
    return max(2, int(default))


def adaptive_chord_weight(n_ca: int, override: float | None = None) -> float:
    """Length-adaptive multi-residue chord weight for sheaf defect."""
    if override is not None:
        return float(max(0.0, min(1.0, override)))
    n = int(n_ca)
    if n >= 13:
        return 0.25
    if n >= 12:
        return 0.18
    return 0.0


def adaptive_defect_scale(n_ca: int) -> float:
    """Map sheaf defect softmin into Kabsch units (length-adaptive)."""
    n = int(n_ca)
    if n >= 13:
        return 0.18
    if n >= 12:
        return 0.17
    if n == 10:
        return 0.16
    return 0.15


def adaptive_face_weight(n_ca: int, override: float | None = None) -> float:
    """2-simplex face strain weight on sheaf defect (mid/short floors)."""
    if override is not None:
        return float(max(0.0, min(1.0, override)))
    n = int(n_ca)
    if n >= 13:
        return 0.12  # 4K8Y / 5EOC steric floors
    if n >= 12:
        return 0.08  # 1TET-class
    return 0.0


def adaptive_seq_mix(n_ca: int, override: float | None = None) -> float:
    """Sequence mix into *score* sheaf residual weights.

    Production default 0 (dual-gate: mid score mixes regressed holdout/top20).
    """
    if override is not None:
        return float(max(0.0, min(1.0, override)))
    _ = int(n_ca)
    return 0.0


def adaptive_soft_T(n_ca: int, base: float = 0.04) -> float:
    """Length-adaptive Crit softmin temperature.

    Mildly sharper softmin on soft/short floors to tighten mold membership
    without abandoning ensemble projection. Mid/long keep near-base T.
    """
    b = float(max(1e-4, base))
    n = int(n_ca)
    if n == 8:
        return float(min(b, 0.032))
    if n in (10, 12):
        return float(min(b, 0.036))
    if n >= 13:
        return float(min(b, 0.038))
    return b


def adaptive_seq_mold_mix(n_ca: int, override: float | None = None) -> float:
    """Sequence mix into *mold defect_tie* only (native structure+chemistry).

    Soft/mid floors use sheaf defect_tie for mold pick; mild sequence
    reweight can break near-ties without changing decoy scoring path.
    """
    if override is not None:
        return float(max(0.0, min(1.0, override)))
    n = int(n_ca)
    if n in (10, 12):
        return 0.15
    if n >= 13:
        return 0.10
    if n == 8:
        return 0.10  # short-floor mold tie (3AVB/3AV9)
    return 0.0


def policy_for(
    n_ca: int,
    *,
    base_beta: float = 0.20,
    sectors_mode: str = "adaptive",
    sectors_default: int = 6,
) -> LengthPolicy:
    """Canonical length policy.

    Soft floors n∈{10,12}:
      defect_tie, height_refine, coutsias_scope, hardmin_mix=0.12
      seq_mold_mix for sequence-conditioned mold tie (score seq_mix stays 0)
    Short floor n==8:
      defect_tie, height_refine, hardmin_mix=0.08, seq_mold_mix=0.10
      (no coutsias; dense omega only — n=8 ω expand dual-gate hurt)
    Mid n≥12: gap_mix + faces; n≥13: defect_tie + seq_mold_mix
    n≥13: no height refine (dual-gate hurt)
    """
    n = int(n_ca)
    soft_floor = n in (10, 12)
    short_floor = n == 8
    mid_steric = n >= 13
    if soft_floor:
        hardmin = 0.12
    elif short_floor:
        hardmin = 0.08
    else:
        hardmin = 0.0
    return LengthPolicy(
        n_ca=n,
        n_sectors=sectors_for_ca_length(
            n, mode=sectors_mode, default=sectors_default
        ),
        defect_beta=adaptive_defect_beta(n, base_beta),
        omega_scales=mid_length_omega_bank(n),
        defect_tie=soft_floor or mid_steric or short_floor,
        height_refine=soft_floor or short_floor,
        coutsias_scope=soft_floor,
        gap_mix=0.20 if n >= 12 else 0.0,
        hardmin_mix=float(hardmin),
        chord_weight=adaptive_chord_weight(n),
        defect_scale=adaptive_defect_scale(n),
        face_weight=adaptive_face_weight(n),
        seq_mix=adaptive_seq_mix(n),
        seq_mold_mix=adaptive_seq_mold_mix(n),
        soft_T=adaptive_soft_T(n, base=0.04),
    )
