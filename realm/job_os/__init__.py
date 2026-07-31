"""Oilfield Job Coherence OS (P3: survey stalk QC + holonomy).

Ontology:
  - Substrate: raw multi-channel time/depth series (LAS/SQL/MicroPulse/survey)
  - Operational geometry: job manifold (depth/time skeleton + channel fibers)
  - Pin: QC/SOP invariants — read-only every cycle; never retuned for score
  - Free params: align/window/pack/null/survey_gate
  - Solved: is_solved ∧ empty free-param board × K
  - Glue: structural depth/time proximity (not score-chase)
  - Survey: QC total G/MagF + optional discrete holonomy; never invent Inc/Azi
  - NEVER claim ζ/Crit predicts ROP; NEVER retune pin mid-run

Mirror of realm.handoff.coherence OS v2 patterns without protein adapters.
"""

from __future__ import annotations

from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds, Observations, SectionProposal

__all__ = [
    "FreeParams",
    "JobThresholds",
    "Observations",
    "SectionProposal",
    "run_job_coherence_loop",
]
