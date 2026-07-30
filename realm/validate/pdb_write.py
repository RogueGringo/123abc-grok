"""Write geometric CA / backbone molds as standard PDB (handoff bridge).

Complement to pdb_io (read). Never λ=γ. Coordinates are the structural shadow
of Crit/Coutsias molds for downstream decorate/physics tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

# Ideal peptide geometry (Å / degrees) — approximate; CA is source of truth
_BL_N_CA = 1.458
_BL_CA_C = 1.525
_BL_C_O = 1.231
_BL_C_N = 1.329
_ANG_N_CA_C = np.deg2rad(111.2)
_ANG_CA_C_O = np.deg2rad(120.8)


def build_remarks(
    *,
    source: str,
    N: int,
    rank_score: float | None = None,
    method: str | None = None,
    twist: float | None = None,
    maxop_gap: float | None = None,
    extra: Sequence[str] | None = None,
) -> list[str]:
    """Fixed REMARK contract for handoff files."""
    lines = [
        "REMARK   1 ENGINE 123abc-grok geometric handoff",
        "REMARK   2 ONTOLOGY substrate_crit_projection_not_lambda_eq_gamma",
        f"REMARK   3 SOURCE {source}",
        f"REMARK   4 N {int(N)}",
    ]
    if rank_score is not None:
        lines.append(f"REMARK   5 RANK_SCORE {float(rank_score):.8g}")
    if method is not None:
        lines.append(f"REMARK   6 METHOD {method}")
    if twist is not None:
        lines.append(f"REMARK   7 TWIST {float(twist):.8g}")
    if maxop_gap is not None:
        lines.append(f"REMARK   8 MAXOP_GAP {float(maxop_gap):.8g}")
    if extra:
        for i, e in enumerate(extra):
            lines.append(f"REMARK   9 {e}")
    return lines


def _atom_line(
    serial: int,
    name: str,
    resname: str,
    chain: str,
    resseq: int,
    xyz: np.ndarray,
    element: str,
) -> str:
    x, y, z = (float(xyz[0]), float(xyz[1]), float(xyz[2]))
    # PDB fixed-width ATOM (columns per wwPDB)
    return (
        f"ATOM  {serial:5d} {name:^4s} {resname:>3s} {chain:1s}{resseq:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2s}"
    )


def write_ca_pdb(
    path: Path | str,
    xyz: np.ndarray,
    *,
    chain: str = "A",
    resnames: Sequence[str] | None = None,
    remarks: Sequence[str] | None = None,
    conect: bool = True,
) -> Path:
    """Write CA-only PDB; optional cycle CONECT."""
    path = Path(path)
    pts = np.asarray(xyz, dtype=float)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError(f"xyz must be (N,3+), got {pts.shape}")
    n = int(pts.shape[0])
    if n < 3:
        raise ValueError("need ≥3 CA atoms")
    names = list(resnames) if resnames is not None else ["GLY"] * n
    if len(names) != n:
        raise ValueError(f"resnames length {len(names)} != N={n}")

    lines: list[str] = []
    if remarks:
        lines.extend(remarks)
    for i in range(n):
        lines.append(
            _atom_line(
                i + 1,
                " CA ",
                str(names[i])[:3].upper(),
                chain[:1] or "A",
                i + 1,
                pts[i, :3],
                "C",
            )
        )
    if conect:
        for i in range(n):
            j = (i + 1) % n
            lines.append(f"CONECT{i+1:5d}{j+1:5d}")
    lines.append("END")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v)) + 1e-15
    return v / n


def idealized_backbone_from_ca(xyz: np.ndarray) -> dict[str, np.ndarray]:
    """Build N, CA, C, O positions from CA trace (cyclic).

    CA is held fixed. Local frame from CA_{i-1}, CA_i, CA_{i+1}.
    """
    ca = np.asarray(xyz, dtype=float)[:, :3].copy()
    n = ca.shape[0]
    N_pos = np.zeros_like(ca)
    C_pos = np.zeros_like(ca)
    O_pos = np.zeros_like(ca)
    for i in range(n):
        prev = ca[(i - 1) % n]
        cur = ca[i]
        nxt = ca[(i + 1) % n]
        t_in = _unit(cur - prev)
        t_out = _unit(nxt - cur)
        # bisector in plane for backbone continuity
        bis = _unit(t_in + t_out)
        # normal to plane of three CAs
        normal = np.cross(t_in, t_out)
        nn = float(np.linalg.norm(normal))
        if nn < 1e-8:
            normal = np.array([0.0, 0.0, 1.0])
            if abs(float(np.dot(t_out, normal))) > 0.9:
                normal = np.array([0.0, 1.0, 0.0])
            normal = normal - t_out * float(np.dot(normal, t_out))
            normal = _unit(normal)
        else:
            normal = normal / nn
        # perpendicular in plane
        perp = _unit(np.cross(normal, t_out))
        # Place C along bisector toward next; N opposite
        # Use bond lengths projected roughly along chain
        C_pos[i] = cur + t_out * (_BL_CA_C * 0.55) + perp * (_BL_CA_C * 0.35)
        N_pos[i] = cur - t_in * (_BL_N_CA * 0.55) - perp * (_BL_N_CA * 0.25)
        # O off C in peptide plane (normal × chain)
        o_dir = _unit(np.cross(C_pos[i] - cur, normal))
        if float(np.dot(o_dir, perp)) < 0:
            o_dir = -o_dir
        O_pos[i] = C_pos[i] + o_dir * _BL_C_O
    return {"N": N_pos, "CA": ca, "C": C_pos, "O": O_pos}


def write_backbone_pdb(
    path: Path | str,
    xyz_ca: np.ndarray,
    *,
    chain: str = "A",
    resnames: Sequence[str] | None = None,
    remarks: Sequence[str] | None = None,
) -> Path:
    """Write idealized N–CA–C–O backbone PDB from CA coords."""
    path = Path(path)
    ca = np.asarray(xyz_ca, dtype=float)
    n = int(ca.shape[0])
    names = list(resnames) if resnames is not None else ["GLY"] * n
    if len(names) != n:
        raise ValueError(f"resnames length {len(names)} != N={n}")
    bb = idealized_backbone_from_ca(ca)
    lines: list[str] = []
    if remarks:
        lines.extend(remarks)
    serial = 1
    for i in range(n):
        res = str(names[i])[:3].upper()
        ch = chain[:1] or "A"
        rseq = i + 1
        for atom_name, element, key in (
            (" N  ", "N", "N"),
            (" CA ", "C", "CA"),
            (" C  ", "C", "C"),
            (" O  ", "O", "O"),
        ):
            lines.append(
                _atom_line(serial, atom_name, res, ch, rseq, bb[key][i], element)
            )
            serial += 1
    lines.append("END")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_mold_pair(
    out_dir: Path | str,
    stem: str,
    xyz: np.ndarray,
    *,
    source: str,
    rank_score: float | None = None,
    method: str | None = None,
    twist: float | None = None,
    maxop_gap: float | None = None,
    chain: str = "A",
    resnames: Sequence[str] | None = None,
    extra_remarks: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Write both CA and backbone PDB levels; return paths + meta."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = int(np.asarray(xyz).shape[0])
    remarks = build_remarks(
        source=source,
        N=n,
        rank_score=rank_score,
        method=method,
        twist=twist,
        maxop_gap=maxop_gap,
        extra=extra_remarks,
    )
    path_ca = out_dir / f"{stem}_ca.pdb"
    path_bb = out_dir / f"{stem}_bb.pdb"
    write_ca_pdb(path_ca, xyz, chain=chain, resnames=resnames, remarks=remarks)
    write_backbone_pdb(path_bb, xyz, chain=chain, resnames=resnames, remarks=remarks)
    return {
        "path_ca": str(path_ca),
        "path_bb": str(path_bb),
        "source": source,
        "N": n,
        "rank_score": rank_score,
        "method": method,
    }
