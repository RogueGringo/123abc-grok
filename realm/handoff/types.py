"""Typed artifacts for the handoff protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class MoldRecord:
    source: str  # crit | coutsias
    N: int
    xyz: np.ndarray
    rank_score: float
    method: str = ""
    twist: float | None = None
    maxop_gap: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_index_entry(self, paths: dict[str, str]) -> dict[str, Any]:
        return {
            "source": self.source,
            "N": self.N,
            "rank_score": self.rank_score,
            "method": self.method,
            "twist": self.twist,
            "maxop_gap": self.maxop_gap,
            "paths": paths,
            "meta": self.meta,
        }


@dataclass
class BackboneArtifact:
    path_ca: Path
    path_bb: Path
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_ca": str(self.path_ca),
            "path_bb": str(self.path_bb),
            "meta": self.meta,
        }


@dataclass
class DecorateRequest:
    backbone: BackboneArtifact
    sequence: str | None = None  # optional 1-letter sequence
    resnames: list[str] | None = None  # optional 3-letter residue names (preferred)
    poly_ala: bool = True


@dataclass
class DecorateResult:
    path_decorated: Path | None
    adapter: str
    status: str  # OK | SKIP | ERROR
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_decorated": None
            if self.path_decorated is None
            else str(self.path_decorated),
            "adapter": self.adapter,
            "status": self.status,
            "note": self.note,
        }


@dataclass
class PhysicsReport:
    status: str  # OK | WARN | FAIL
    adapter: str
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
