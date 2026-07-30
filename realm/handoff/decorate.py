"""Decorate pipeline stub — adapters optional at import time."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from realm.handoff.types import BackboneArtifact, DecorateRequest, DecorateResult


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
        from realm.validate.pdb_io import parse_ca_trace

        bb = req.backbone.path_bb
        if not bb.is_file():
            return DecorateResult(
                None, self.name, "ERROR", note=f"missing backbone {bb}"
            )
        text = bb.read_text(encoding="utf-8")
        # Rewrite existing residue names to ALA, then append CB stubs
        ca = parse_ca_trace(text)
        out_lines: list[str] = []
        for ln in text.splitlines():
            if ln.startswith("END"):
                continue
            if ln.startswith("ATOM") or ln.startswith("HETATM"):
                # PDB columns 18-20 are resname; force ALA for consistent poly-ALA
                if len(ln) >= 20:
                    ln = ln[:17] + "ALA" + ln[20:]
                else:
                    ln = (ln + " " * 20)[:17] + "ALA"
            out_lines.append(ln)
        serial = sum(1 for ln in out_lines if ln.startswith("ATOM") or ln.startswith("HETATM")) + 1
        for i, p in enumerate(ca):
            x, y, z = float(p[0]), float(p[1]), float(p[2]) + 1.5
            resseq = i + 1
            out_lines.append(
                f"ATOM  {serial:5d}  CB  ALA A{resseq:4d}    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00           C"
            )
            serial += 1
        out_lines.append("END")
        # Write beside path_bb when no molds/ parent; sibling decorated/ when under molds/
        out_dir = (
            bb.parent / "decorated"
            if bb.parent.name != "molds"
            else bb.parent.parent / "decorated"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / (bb.stem.replace("_bb", "") + "_polyala.pdb")
        out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        return DecorateResult(
            path_decorated=out_path,
            adapter=self.name,
            status="OK",
            note="poly-ALA resnames + CB stubs only (not full sidechain packing)",
        )


def get_decorate_adapters() -> list[DecorateAdapter]:
    adapters: list[DecorateAdapter] = [NullDecorateAdapter(), PolyAlaStubAdapter()]
    # Optional PyRosetta / BioPython later — import-guarded
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
    if name == "auto":
        for a in get_decorate_adapters():
            if a.name == "polyala":
                return a
        return NullDecorateAdapter()
    for a in get_decorate_adapters():
        if a.name == name or (name == "polyala" and a.name == "polyala"):
            return a
    return NullDecorateAdapter()
