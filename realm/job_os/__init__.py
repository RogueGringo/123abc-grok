"""Oilfield Job Coherence OS (P5: EOW package ship + recipe attach).

Ontology:
  - Substrate: raw multi-channel time/depth series (LAS/SQL/MicroPulse/survey)
  - Operational geometry: job manifold (depth/time skeleton + channel fibers)
  - Pin: QC/SOP invariants — read-only every cycle; never retuned for score
  - Free params: align/window/pack/null/survey_gate/regime_mode
  - Solved: is_solved ∧ empty free-param board × K
  - Glue: structural depth/time proximity (not score-chase)
  - Survey: QC total G/MagF + optional discrete holonomy; never invent Inc/Azi
  - Regime: windowed H0 barcode + dual-gate science info (not accept alone)
  - Firewall: explore (science/topo/λ1) vs certify (pin+fixed-point); near-miss rejected
  - Aliases (C6): inherited vendor→canonical mnemonics; never invent samples
  - EOW (D): package inventory + SHIP after SOLVED (or force UNSOLVED_SHIP)
  - NEVER claim ζ/Crit predicts ROP; NEVER retune pin mid-run

Mirror of realm.handoff.coherence OS v2 patterns without protein adapters.
"""

from __future__ import annotations

from realm.job_os.audit import audit_job_run, audit_rotation_batch
from realm.job_os.eow_ship import inventory_eow_package, ship_eow_package
from realm.job_os.firewall import assert_firewall_invariants, build_job_firewall
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.rotation import classify_rotation, run_job_rotation
from realm.job_os.types import FreeParams, JobThresholds, Observations, SectionProposal

__all__ = [
    "FreeParams",
    "JobThresholds",
    "Observations",
    "SectionProposal",
    "assert_firewall_invariants",
    "audit_job_run",
    "audit_rotation_batch",
    "build_job_firewall",
    "classify_rotation",
    "inventory_eow_package",
    "run_job_coherence_loop",
    "run_job_rotation",
    "ship_eow_package",
]
