"""KB geometry integration (Academic KB A–D stalks).

Stalks:
  A — multi-window zigzag / barcode (windows as time, not LLM layers)
  B — science annex holdout language (info only, never ACCEPTANCE)
  C/D — later phases

Ontology: never λ=γ; never retune dual-gate / Job QC pin for score.
Provenance cites ACADEMIC sources; transfer notes required.
"""

from __future__ import annotations

from realm.kb_geometry.science_annex import (
    SCIENCE_ANNEX_KIND,
    attach_science_theory,
    build_science_annex_base,
    is_informational_only,
)
from realm.kb_geometry.zigzag_windows import (
    phase_summary,
    zigzag_window_barcode,
)

__all__ = [
    "SCIENCE_ANNEX_KIND",
    "attach_science_theory",
    "build_science_annex_base",
    "is_informational_only",
    "phase_summary",
    "zigzag_window_barcode",
]
