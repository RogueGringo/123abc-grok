from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np

KB_SOURCE = "arXiv:2410.11042 + AXiomZ dual spine"
TRANSFER_NOTE = "stages as discrete time (not LLM layers)"

@dataclass
class Stage:
    index: int
    label: str
    points: np.ndarray  # (n, d)

def empty_report() -> dict[str, Any]:
    return {
        "kind": "dynamical_topology",
        "not_acceptance": True,
        "ontology": "dynamical_topology_dual_spine_not_lambda_eq_gamma",
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "n_stages": 0,
        "bars": [],
        "n_long": 0,
        "n_short": 0,
        "phases": {"labels": [], "dominant": None},
        "sheaf_dual": None,
        "pin_writable": False,
        "acceptance_writable": False,
    }

def finalize_report(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    out["not_acceptance"] = True
    out["pin_writable"] = False
    out["acceptance_writable"] = False
    out.setdefault("kind", "dynamical_topology")
    out.setdefault("kb_source", KB_SOURCE)
    out.setdefault("transfer_note", TRANSFER_NOTE)
    out.setdefault("ontology", "dynamical_topology_dual_spine_not_lambda_eq_gamma")
    return out
