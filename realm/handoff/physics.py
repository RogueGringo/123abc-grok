"""Physics filter stubs — geometry self-check always available."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from realm.handoff.types import PhysicsReport
from realm.validate.pdb_io import parse_ca_trace

logger = logging.getLogger(__name__)


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
                "closure_bond": float(b[-1]),  # last cyclic CA–CA bond
                "ideal_ca": self.ideal_ca,
            },
            notes=notes,
        )


def get_physics_adapter(name: str = "geometry") -> PhysicsFilterAdapter | None:
    name = (name or "geometry").lower().strip()
    if name in ("none", "off", "skip"):
        return None
    return GeometrySelfCheck()


def rollup_physics_reports(
    reports: list[dict[str, Any]],
    *,
    scope: str = "export",
) -> dict[str, Any]:
    """Aggregate geometry self-check reports for partner glance.

    Does not gate commercial ACCEPTANCE (openable PDBs + pin remain criteria).
    """
    n = len(reports)
    by_status: dict[str, int] = {}
    means: list[float] = []
    stds: list[float] = []
    fails: list[dict[str, Any]] = []
    warns: list[dict[str, Any]] = []
    for r in reports:
        st = str(r.get("status") or "UNKNOWN")
        by_status[st] = by_status.get(st, 0) + 1
        metrics = r.get("metrics") or {}
        if "ca_bond_mean" in metrics:
            try:
                means.append(float(metrics["ca_bond_mean"]))
            except (TypeError, ValueError):
                pass
        if "ca_bond_std" in metrics:
            try:
                stds.append(float(metrics["ca_bond_std"]))
            except (TypeError, ValueError):
                pass
        row = {
            "stem": r.get("stem"),
            "pdb": r.get("pdb"),
            "path": r.get("path"),
            "status": st,
            "notes": r.get("notes") or [],
            "ca_bond_mean": metrics.get("ca_bond_mean"),
        }
        if st == "FAIL":
            fails.append(row)
        elif st == "WARN":
            warns.append(row)

    return {
        "ontology": "physics_rollup_geometry_self_check_not_lambda_eq_gamma",
        "scope": scope,
        "adapter": "geometry_self_check",
        "n_reports": n,
        "by_status": by_status,
        "n_ok": int(by_status.get("OK", 0)),
        "n_warn": int(by_status.get("WARN", 0)),
        "n_fail": int(by_status.get("FAIL", 0)),
        "mean_ca_bond": float(np.mean(means)) if means else None,
        "mean_ca_bond_std": float(np.mean(stds)) if stds else None,
        "ideal_ca": 3.8,
        "fails": fails[:20],
        "warns": warns[:20],
        "note": (
            "Geometry self-check on CA rings (bond length vs ideal 3.8 A). "
            "Informational; commercial accept remains openable PDBs + dual-gate pin."
        ),
    }


def write_physics_rollup(
    reports: list[dict[str, Any]],
    path: Path | str,
    *,
    scope: str = "export",
) -> Path:
    """Write PHYSICS_ROLLUP.json (+ .md companion)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    rollup = rollup_physics_reports(reports, scope=scope)
    dest.write_text(json.dumps(rollup, indent=2) + "\n", encoding="utf-8")
    md = dest.with_suffix(".md")
    lines = [
        "# Physics rollup (geometry self-check)",
        "",
        f"- scope: `{scope}`",
        f"- n_reports: **{rollup['n_reports']}**",
        f"- OK / WARN / FAIL: **{rollup['n_ok']}** / **{rollup['n_warn']}** / **{rollup['n_fail']}**",
        f"- mean CA-CA bond: {rollup.get('mean_ca_bond')} (ideal 3.8)",
        f"- mean CA-CA std: {rollup.get('mean_ca_bond_std')}",
        "",
        "Informational only — **not** ACCEPTANCE / SHIP success.",
        "Commercial metric remains openable PDBs + dual-gate pin soft_T(n=12)=0.036.",
        "Never lambda=gamma.",
        "",
    ]
    if rollup["fails"]:
        lines.append("## Fails")
        lines.append("")
        for f in rollup["fails"][:10]:
            lines.append(f"- {f.get('stem') or f.get('path')}: {f.get('notes')}")
        lines.append("")
    if rollup["warns"]:
        lines.append("## Warns")
        lines.append("")
        for w in rollup["warns"][:10]:
            lines.append(f"- {w.get('stem') or w.get('path')}: {w.get('notes')}")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "physics rollup n=%s ok=%s warn=%s fail=%s → %s",
        rollup["n_reports"],
        rollup["n_ok"],
        rollup["n_warn"],
        rollup["n_fail"],
        dest,
    )
    return dest


def scan_physics_tree(
    root: Path | str,
    *,
    adapter: str = "geometry",
) -> dict[str, Any]:
    """Run geometry self-check on all *_bb.pdb under root; write rollup."""
    base = Path(root)
    ad = get_physics_adapter(adapter)
    if ad is None:
        return {"ok": False, "error": "physics adapter disabled", "n_reports": 0}
    reports: list[dict[str, Any]] = []
    for pdb in sorted(base.rglob("*_bb.pdb")):
        try:
            phys = ad.filter(pdb)
            d = phys.to_dict()
            d["path"] = str(pdb.relative_to(base)) if base in pdb.parents else str(pdb)
            d["stem"] = pdb.stem
            reports.append(d)
        except Exception as exc:  # noqa: BLE001
            reports.append(
                {
                    "status": "FAIL",
                    "adapter": getattr(ad, "name", adapter),
                    "path": str(pdb),
                    "stem": pdb.stem,
                    "notes": [str(exc)],
                    "metrics": {},
                }
            )
    out = base / "PHYSICS_ROLLUP.json"
    write_physics_rollup(reports, out, scope=str(base))
    rollup = json.loads(out.read_text(encoding="utf-8"))
    rollup["ok"] = True
    rollup["path"] = str(out.resolve())
    return rollup
