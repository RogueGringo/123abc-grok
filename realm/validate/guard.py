"""Degeneracy guard — Axiom 6.2, the Continuity Guard Principle.

Axiom 6.2 requires that operations destroying a system's topological signature be
rejected, flagged, or rolled back. The published validation ladder contained such
a destruction and ran to completion without detecting it:

* `derive.py` fills the sector pool from the critical *minima* of the spectral
  action, and `build_key`/`build_lock` then read the sector twists and those same
  minima. When the action yields at least `n_sectors` minima the two are the same
  array, so `pin_align`, `theta_ladder_l1`, `crit_coverage` and `stationarity` —
  0.70 of the residual weight — are identically zero for *any* seed spectrum.
* `occupancy` saturated at 1.0 in every run, so the `alpha*(1-occ)` term in F was
  also always zero.

Consequence: `F = R = 0.25*corr_penalty + 0.05*density_return` exactly, measured
across 24 runs with zero violations. Eight knobs were fitting two live scalars,
and a constant-gap ladder beat ζ.

This module makes that condition **detectable and rejectable**. It measures the
signature rather than assuming independence: a disjoint-block baseline (Axiom 6.1)
is supposed to break the coincidence, but it can itself collapse, so the guard
counts the coincidence that actually occurred.

It deliberately computes nothing about ζ and imposes no ontology — it only asks
whether a configuration's residual could have been non-zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

STAMP = "DEGENERATE_OBJECTIVE"

# A term this small is numerically indistinguishable from a structural zero.
VACUOUS = 1e-6
# Exact-coincidence tolerance. Machine-precision, not a fuzzy match: the failure
# mode being caught is literal set identity, measured at <1e-12 in the champion.
COINCIDENT_ATOL = 1e-12


class GuardRejection(RuntimeError):
    """Raised when a degenerate configuration is used for selection."""


@dataclass(frozen=True)
class DegeneracySignature:
    """Measured degeneracy of one scored configuration."""

    n_keys: int
    n_lock_minima: int
    n_exact_coincident: int
    coincident_fraction: float
    stationarity: float
    crit_coverage: float
    occupancy: float
    stationarity_vacuous: bool
    coverage_vacuous: bool
    occupancy_saturated: bool
    empty: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_degenerate(self) -> bool:
        return bool(self.reasons)

    @property
    def stamp(self) -> str:
        return STAMP if self.is_degenerate else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stamp": self.stamp,
            "is_degenerate": self.is_degenerate,
            "reasons": list(self.reasons),
            "n_keys": int(self.n_keys),
            "n_lock_minima": int(self.n_lock_minima),
            "n_exact_coincident": int(self.n_exact_coincident),
            "coincident_fraction": float(self.coincident_fraction),
            "stationarity": float(self.stationarity),
            "crit_coverage": float(self.crit_coverage),
            "occupancy": float(self.occupancy),
            "flags": {
                "stationarity_vacuous": bool(self.stationarity_vacuous),
                "coverage_vacuous": bool(self.coverage_vacuous),
                "occupancy_saturated": bool(self.occupancy_saturated),
                "empty": bool(self.empty),
            },
            "axiom": "6.2 continuity_guard_principle",
        }


def count_exact_coincident(
    key_thetas: np.ndarray, lock_minima: np.ndarray, *, atol: float = COINCIDENT_ATOL
) -> int:
    """How many key angles land on a lock minimum to machine precision."""
    k = np.asarray(key_thetas, dtype=float).ravel()
    m = np.asarray(lock_minima, dtype=float).ravel()
    if k.size == 0 or m.size == 0:
        return 0
    return int(sum(1 for t in k if np.min(np.abs(m - t)) <= atol))


def measure_degeneracy(
    *,
    key_thetas: np.ndarray,
    lock_minima: np.ndarray,
    stationarity: float,
    crit_coverage: float,
    occupancy: float,
    vacuous: float = VACUOUS,
) -> DegeneracySignature:
    """Measure whether a configuration's residual could have been non-zero.

    Any one condition is sufficient — they are OR'd. A configuration that trips
    none of them still is not *good*; it merely is not provably vacuous.
    """
    k = np.asarray(key_thetas, dtype=float).ravel()
    m = np.asarray(lock_minima, dtype=float).ravel()
    n_coin = count_exact_coincident(k, m)
    frac = (n_coin / k.size) if k.size else 0.0

    stat_vac = float(stationarity) < vacuous
    cov_vac = abs(float(crit_coverage)) < vacuous
    occ_sat = float(occupancy) >= 1.0
    empty = k.size == 0 or m.size == 0

    reasons: list[str] = []
    if empty:
        reasons.append("no keys or no lock minima — nothing was verified")
    if n_coin > 0:
        reasons.append(
            f"{n_coin}/{k.size} key angles coincide with lock minima to "
            f"{COINCIDENT_ATOL:g} — lock and key are the same object"
        )
    if stat_vac:
        reasons.append(
            f"stationarity={stationarity:.3g} < {vacuous:g} — keys sit at critical "
            "points where dS vanishes by construction"
        )
    if cov_vac:
        reasons.append(
            f"crit_coverage={crit_coverage:.3g} — every lock minimum is already a key"
        )
    if occ_sat:
        reasons.append(
            f"occupancy={occupancy:.3g} saturated — the (1-occ) penalty cannot vary"
        )

    return DegeneracySignature(
        n_keys=int(k.size),
        n_lock_minima=int(m.size),
        n_exact_coincident=n_coin,
        coincident_fraction=float(frac),
        stationarity=float(stationarity),
        crit_coverage=float(crit_coverage),
        occupancy=float(occupancy),
        stationarity_vacuous=stat_vac,
        coverage_vacuous=cov_vac,
        occupancy_saturated=occ_sat,
        empty=empty,
        reasons=tuple(reasons),
    )


def require_non_degenerate(sig: DegeneracySignature) -> DegeneracySignature:
    """Reject rather than flag. Returns the signature so it can be chained.

    Axiom 6.2 permits reject | flag | rollback. Selection uses **reject**: the
    ladder already demonstrated that a flag nobody reads is indistinguishable
    from no guard at all.
    """
    if sig.is_degenerate:
        raise GuardRejection(f"{STAMP}: " + "; ".join(sig.reasons))
    return sig
