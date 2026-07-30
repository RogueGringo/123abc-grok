"""Physics filter stubs — geometry self-check always available."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from realm.handoff.types import PhysicsReport
from realm.validate.pdb_io import parse_ca_trace


class PhysicsFilterAdapter(Protocol):
    name: str

    def available(self) -> bool: ...

    def filter(self, pdb_path: Path) -> PhysicsReport: ...


class GeometrySelfCheck:
    name = "geometry_self_check"
    ideal_ca = 3.8

    def available(self) -> bool:
        return True

    def filter(self, pdb_path: Path) -> PhysicsReport:
        path = Path(pdb_path)
        if not path.is_file():
            return PhysicsReport(
                status="FAIL",
                adapter=self.name,
                notes=[f"missing file {path}"],
            )
        text = path.read_text(encoding="utf-8")
        try:
            ca = parse_ca_trace(text)
        except Exception as exc:  # noqa: BLE001
            return PhysicsReport(
                status="FAIL",
                adapter=self.name,
                notes=[f"parse failed: {exc}"],
            )
        n = ca.shape[0]
        bonds = []
        for i in range(n):
            j = (i + 1) % n
            bonds.append(float(np.linalg.norm(ca[j] - ca[i])))
        b = np.asarray(bonds, dtype=float)
        mean_b = float(np.mean(b))
        std_b = float(np.std(b))
        closure = float(np.linalg.norm(ca[0] - ca[-1]))  # same as last bond for cycle
        notes: list[str] = []
        status = "OK"
        if abs(mean_b - self.ideal_ca) > 0.8:
            status = "WARN"
            notes.append(f"mean CA-CA bond {mean_b:.3f} far from {self.ideal_ca}")
        if std_b > 0.6:
            status = "WARN"
            notes.append(f"high CA-CA bond std {std_b:.3f}")
        return PhysicsReport(
            status=status,
            adapter=self.name,
            metrics={
                "n_ca": n,
                "ca_bond_mean": mean_b,
                "ca_bond_std": std_b,
                "closure_bond": float(b[-1]),
                "ideal_ca": self.ideal_ca,
            },
            notes=notes,
        )


def get_physics_adapter(name: str = "geometry") -> PhysicsFilterAdapter | None:
    name = (name or "geometry").lower().strip()
    if name in ("none", "off", "skip"):
        return None
    return GeometrySelfCheck()
