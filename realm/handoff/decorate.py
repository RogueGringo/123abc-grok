"""Decorate pipeline — adapters optional at import time.

polyala: all ALA + CB stubs
sequence: native 3-letter resnames when available + CB stubs (no CB for GLY)
Never full sidechain packing; never lambda=gamma.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from realm.handoff.types import DecorateRequest, DecorateResult

# 1-letter → 3-letter (standard)
_AA1_TO_3 = {
    "A": "ALA",
    "R": "ARG",
    "N": "ASN",
    "D": "ASP",
    "C": "CYS",
    "Q": "GLN",
    "E": "GLU",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "L": "LEU",
    "K": "LYS",
    "M": "MET",
    "F": "PHE",
    "P": "PRO",
    "S": "SER",
    "T": "THR",
    "W": "TRP",
    "Y": "TYR",
    "V": "VAL",
}


def _decorate_out_dir(bb: Path) -> Path:
    out_dir = (
        bb.parent / "decorated"
        if bb.parent.name != "molds"
        else bb.parent.parent / "decorated"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _normalize_resnames(
    n_ca: int,
    *,
    resnames: list[str] | None,
    sequence: str | None,
    force_ala: bool,
) -> list[str]:
    if force_ala:
        return ["ALA"] * n_ca
    names: list[str] = []
    if resnames is not None and len(resnames) == n_ca:
        for r in resnames:
            rn = str(r).strip().upper()
            if len(rn) == 1:
                rn = _AA1_TO_3.get(rn, "ALA")
            elif len(rn) >= 3:
                rn = rn[:3]
            else:
                rn = "ALA"
            names.append(rn)
        return names
    if sequence is not None and len(sequence) == n_ca:
        for ch in sequence:
            names.append(_AA1_TO_3.get(ch.upper(), "ALA"))
        return names
    return ["ALA"] * n_ca


def _write_stub_pdb(
    bb: Path,
    *,
    resnames: list[str],
    out_name: str,
) -> Path:
    """Rewrite bb resnames and append CB stubs (skip GLY)."""
    from realm.validate.pdb_io import parse_ca_trace

    text = bb.read_text(encoding="utf-8")
    ca = parse_ca_trace(text)
    n_ca = int(ca.shape[0])
    if len(resnames) != n_ca:
        resnames = (list(resnames) + ["ALA"] * n_ca)[:n_ca]

    out_lines: list[str] = []
    res_i = 0
    has_ontology = "not_lambda_eq_gamma" in text
    for ln in text.splitlines():
        if ln.startswith("END"):
            continue
        if ln.startswith("ATOM") or ln.startswith("HETATM"):
            name = ln[12:16].strip() if len(ln) >= 16 else ""
            rn = resnames[min(res_i, n_ca - 1)] if n_ca else "ALA"
            if len(ln) >= 20:
                ln = ln[:17] + f"{rn:3s}" + ln[20:]
            else:
                ln = (ln + " " * 20)[:17] + f"{rn:3s}"
            # After writing a complete residue's atoms we track via CA
            if name == "CA":
                res_i += 1
        out_lines.append(ln)

    # Ensure ontology REMARK for partner verify (molds are source of truth)
    prefix: list[str] = []
    if not has_ontology:
        prefix.append(
            "REMARK   2 ONTOLOGY substrate_crit_projection_not_lambda_eq_gamma"
        )
    prefix.append("REMARK   9 DECORATE stub_sidechain_not_full_packing")
    out_lines = prefix + out_lines

    serial = sum(
        1 for ln in out_lines if ln.startswith("ATOM") or ln.startswith("HETATM")
    ) + 1
    for i, p in enumerate(ca):
        rn = resnames[i]
        if rn == "GLY":
            continue  # no CB
        x, y, z = float(p[0]), float(p[1]), float(p[2]) + 1.5
        resseq = i + 1
        out_lines.append(
            f"ATOM  {serial:5d}  CB  {rn:3s} A{resseq:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00           C"
        )
        serial += 1
    out_lines.append("END")
    out_path = _decorate_out_dir(bb) / out_name
    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return out_path


class DecorateAdapter(Protocol):
    name: str

    def available(self) -> bool: ...

    def decorate(self, req: DecorateRequest) -> DecorateResult: ...


class NullDecorateAdapter:
    name = "null"

    def available(self) -> bool:
        return True

    def decorate(self, req: DecorateRequest) -> DecorateResult:
        return DecorateResult(
            path_decorated=None,
            adapter=self.name,
            status="SKIP",
            note="external decorate — handoff exports backbone only",
        )


class PolyAlaStubAdapter:
    """Minimal CB stubs on CA for tools that want a sidechain atom present."""

    name = "polyala"

    def available(self) -> bool:
        return True

    def decorate(self, req: DecorateRequest) -> DecorateResult:
        bb = req.backbone.path_bb
        if not bb.is_file():
            return DecorateResult(
                None, self.name, "ERROR", note=f"missing backbone {bb}"
            )
        from realm.validate.pdb_io import parse_ca_trace

        ca = parse_ca_trace(bb.read_text(encoding="utf-8"))
        n_ca = int(ca.shape[0])
        names = _normalize_resnames(n_ca, resnames=None, sequence=None, force_ala=True)
        out_path = _write_stub_pdb(
            bb,
            resnames=names,
            out_name=bb.stem.replace("_bb", "") + "_polyala.pdb",
        )
        return DecorateResult(
            path_decorated=out_path,
            adapter=self.name,
            status="OK",
            note="poly-ALA resnames + CB stubs only (not full sidechain packing)",
        )


class SequenceStubAdapter:
    """Native resnames when provided; CB stubs for non-GLY (not full packing)."""

    name = "sequence"

    def available(self) -> bool:
        return True

    def decorate(self, req: DecorateRequest) -> DecorateResult:
        bb = req.backbone.path_bb
        if not bb.is_file():
            return DecorateResult(
                None, self.name, "ERROR", note=f"missing backbone {bb}"
            )
        from realm.validate.pdb_io import parse_ca_trace

        ca = parse_ca_trace(bb.read_text(encoding="utf-8"))
        n_ca = int(ca.shape[0])
        # Prefer explicit resnames, then request sequence, then meta.resnames
        meta_rn = None
        if req.backbone.meta:
            meta_rn = req.backbone.meta.get("resnames")
        resnames = req.resnames if req.resnames is not None else meta_rn
        has_seq = (
            (resnames is not None and len(resnames) == n_ca)
            or (req.sequence is not None and len(req.sequence) == n_ca)
        )
        if not has_seq:
            # graceful fallback to polyala
            names = _normalize_resnames(
                n_ca, resnames=None, sequence=None, force_ala=True
            )
            out_path = _write_stub_pdb(
                bb,
                resnames=names,
                out_name=bb.stem.replace("_bb", "") + "_polyala.pdb",
            )
            return DecorateResult(
                path_decorated=out_path,
                adapter=self.name,
                status="OK",
                note=(
                    "sequence unavailable (length mismatch or missing); "
                    "fell back to poly-ALA CB stubs"
                ),
            )
        names = _normalize_resnames(
            n_ca,
            resnames=list(resnames) if resnames is not None else None,
            sequence=req.sequence,
            force_ala=False,
        )
        out_path = _write_stub_pdb(
            bb,
            resnames=names,
            out_name=bb.stem.replace("_bb", "") + "_seq.pdb",
        )
        n_cb = sum(1 for r in names if r != "GLY")
        return DecorateResult(
            path_decorated=out_path,
            adapter=self.name,
            status="OK",
            note=(
                f"native resnames + CB stubs on {n_cb}/{n_ca} non-GLY "
                "(not full sidechain packing)"
            ),
        )


class PyRosettaAdapter:
    """Optional PyRosetta decorate: pose load/dump only; never required in CI."""

    name = "pyrosetta"

    def available(self) -> bool:
        try:
            import pyrosetta  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def decorate(self, req: DecorateRequest) -> DecorateResult:
        if not self.available():
            return DecorateResult(
                None, self.name, "SKIP", note="pyrosetta not installed"
            )
        try:
            import pyrosetta

            pyrosetta.init("-mute all")
            pose = pyrosetta.pose_from_pdb(str(req.backbone.path_bb))
            bb = req.backbone.path_bb
            out_dir = (
                bb.parent / "decorated"
                if bb.parent.name != "molds"
                else bb.parent.parent / "decorated"
            )
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / (bb.stem + "_pyrosetta.pdb")
            pose.dump_pdb(str(out_path))
            return DecorateResult(
                out_path, self.name, "OK", note="pose load/dump only"
            )
        except Exception as exc:  # noqa: BLE001
            return DecorateResult(None, self.name, "ERROR", note=str(exc))


def get_decorate_adapters() -> list[DecorateAdapter]:
    adapters: list[DecorateAdapter] = [
        NullDecorateAdapter(),
        PolyAlaStubAdapter(),
        SequenceStubAdapter(),
        PyRosettaAdapter(),
    ]
    # Optional BioPython — import-guarded
    try:
        import Bio  # noqa: F401

        adapters.append(_BioPythonValidateAdapter())
    except Exception:  # noqa: BLE001
        pass
    return adapters


class _BioPythonValidateAdapter:
    name = "biopython_validate"

    def available(self) -> bool:
        try:
            import Bio  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def decorate(self, req: DecorateRequest) -> DecorateResult:
        """Load backbone with BioPython to prove openability; no sequence design."""
        try:
            from Bio.PDB import PDBParser

            parser = PDBParser(QUIET=True)
            parser.get_structure("bb", str(req.backbone.path_bb))
            return DecorateResult(
                path_decorated=req.backbone.path_bb,
                adapter=self.name,
                status="OK",
                note="BioPython openable validation only",
            )
        except Exception as exc:  # noqa: BLE001
            return DecorateResult(
                None, self.name, "ERROR", note=str(exc)
            )


def select_adapter(name: str) -> DecorateAdapter:
    name = (name or "null").lower().strip()
    if name in ("auto", "seq"):
        # Prefer sequence-aware; falls back to polyala behavior when no resnames
        for a in get_decorate_adapters():
            if a.name == "sequence":
                return a
        for a in get_decorate_adapters():
            if a.name == "polyala":
                return a
        return NullDecorateAdapter()
    for a in get_decorate_adapters():
        if a.name == name:
            return a
    return NullDecorateAdapter()
