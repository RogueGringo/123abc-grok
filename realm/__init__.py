"""Zeta–Kinematic Realm — correct abstraction.

Geometry is built **off the zeta field** (γ_n as generative seed).
Sheaf spectra are properties of that induced geometry.
They are **not** the actual Riemann zeros.

    from realm import analyze_cycle, KinematicSpectralRealm, ZetaField

    result = analyze_cycle(N=11)
    print(result.summary()["ontology"])
    # → geometry_off_zeta_field_not_actual_zeros
"""

from realm.engine import KinematicSpectralRealm, analyze_cycle
from realm.derive import Deriver, DerivationResult, derive
from realm.lock_key import MasterLockProtocol, MeetResult, meet_lock
from realm.projection import (
    ModuliLandscape,
    ProjectionTestResult,
    build_moduli_landscape,
    run_projection_protocol,
    test_valley_occupancy,
)
from realm.types import AnalysisResult, ProbeReport, Sector, Spectrum, Waypoint
from realm.zeta_field import ZetaField, ZETA_ZEROS_IMAG
from realm.zeta_geometry import ZetaInducedGeometry, InducedSector

__all__ = [
    "KinematicSpectralRealm",
    "analyze_cycle",
    "derive",
    "Deriver",
    "DerivationResult",
    "meet_lock",
    "MasterLockProtocol",
    "MeetResult",
    "build_moduli_landscape",
    "test_valley_occupancy",
    "run_projection_protocol",
    "ModuliLandscape",
    "ProjectionTestResult",
    "ZetaField",
    "ZETA_ZEROS_IMAG",
    "ZetaInducedGeometry",
    "InducedSector",
    "AnalysisResult",
    "Sector",
    "Spectrum",
    "Waypoint",
    "ProbeReport",
]
