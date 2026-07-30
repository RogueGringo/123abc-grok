# Handoff Protocol Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close remaining gaps in the approved handoff protocol so Crit∪Coutsias molds export as multi-level openable PDBs, with decorate/physics stubs, structure mode, and full test coverage — without touching dual-gate ranking policy.

**Architecture:** The geometric engine already forges Crit templates and Coutsias closures in R³. Handoff is a **write-side bridge**: `MoldRecord` ensemble → rank → `write_mold_pair` (CA + idealized N–CA–C–O) → optional `DecorateAdapter` / `PhysicsFilterAdapter`. Ranking production path (`LengthPolicy`, `pdb_batch.rank_one`) must not be modified for score chase. Success metric is **downstream-openable files**, not enrichment %.

**Tech Stack:** Python 3.11+, NumPy, existing `realm.validate.pdb_io` / `pdb_write`, `realm.handoff.*`, `handoff_export.py`, pytest. Optional: BioPython / PyRosetta (import-guarded only).

## Global Constraints

- Ontology REMARK on every structure: `substrate_crit_projection_not_lambda_eq_gamma` (never λ=γ)
- Do **not** change `realm/validate/length_policy.py` production numbers or dual-gate defaults
- Do **not** require PyRosetta or OpenMM in CI
- CA is source of truth; backbone is idealized rebuild for packing tools
- Spec: `docs/superpowers/specs/2026-07-30-handoff-protocol-design.md`
- Primary metric: files open in BioPython / standard PDB parsers without error

## Repo status (do not re-implement from scratch)

| Phase | Spec deliverable | Status on disk |
|-------|------------------|----------------|
| P1 | `pdb_write` CA+bb+REMARK+tests | **DONE** — `realm/validate/pdb_write.py`, `tests/test_pdb_write.py` (3 tests pass) |
| P2 | Crit+Coutsias generate, rank, CLI, index | **DONE** — `realm/handoff/generate.py`, `handoff_export.py` |
| P3 | Decorate Protocol + Null + PolyAla | **DONE** — `realm/handoff/decorate.py` |
| P4 | GeometrySelfCheck + JSON | **DONE** — `realm/handoff/physics.py` |
| P5 | Optional Rosetta/BioPython | **PARTIAL** — BioPython validate only; no PyRosetta |

**Remaining work (this plan):** verification suite for P2–P4, structure mode, CLI flags from spec, PyRosetta optional stub, plan/doc status sync. **Do not replace P1 with alternate Gemini API** (`write_ca_pdb(xyz, path)` vs current `write_ca_pdb(path, xyz)`).

## File map

| File | Responsibility |
|------|----------------|
| `realm/validate/pdb_write.py` | CA/backbone PDB writers, REMARKs, mold pair (P1 — touch only if tests force API fix) |
| `realm/validate/pdb_io.py` | CA parse (round-trip consumer) — read only unless parse bug |
| `realm/handoff/types.py` | `MoldRecord`, `BackboneArtifact`, decorate/physics types |
| `realm/handoff/generate.py` | Crit + Coutsias ensemble + `merge_and_rank` |
| `realm/handoff/decorate.py` | Decorate adapters |
| `realm/handoff/physics.py` | Geometry self-check |
| `handoff_export.py` | CLI orchestration |
| `tests/test_pdb_write.py` | P1 tests (exist) |
| `tests/test_handoff.py` | **Create** — P2–P4 smoke + adapters |
| `tests/test_handoff_structure.py` | **Create** — structure mode |
| `docs/superpowers/plans/2026-07-30-handoff-protocol-plan.md` | Mark phases done / remaining |

---

### Task 1: Lock P1 verification (no rewrite)

**Files:**
- Test: `tests/test_pdb_write.py` (modify only if missing assertions)
- Read: `realm/validate/pdb_write.py`

**Interfaces:**
- Consumes: existing `write_ca_pdb(path, xyz, *, chain, resnames, remarks, conect) -> Path`
- Consumes: `write_backbone_pdb(path, xyz_ca, *, ...) -> Path`
- Consumes: `build_remarks(*, source, N, rank_score=None, method=None, twist=None, maxop_gap=None, extra=None) -> list[str]`
- Produces: green pytest for P1 contract

- [ ] **Step 1: Run existing P1 tests**

Run: `pytest tests/test_pdb_write.py -v`

Expected: PASS (3 tests). If FAIL, fix `pdb_write.py` only — do **not** replace with path-last Gemini signatures.

- [ ] **Step 2: Add explicit ontology REMARK unit test if missing**

Append to `tests/test_pdb_write.py`:

```python
def test_remark_ontology_literal():
    from realm.validate.pdb_write import build_remarks
    lines = build_remarks(source="crit", N=11, rank_score=0.5, method="test")
    joined = "\n".join(lines)
    assert "not_lambda_eq_gamma" in joined
    assert any(line.startswith("REMARK") for line in lines)
    assert "SOURCE crit" in joined
```

- [ ] **Step 3: Run test**

Run: `pytest tests/test_pdb_write.py::test_remark_ontology_literal -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_pdb_write.py
git commit -m "test: lock handoff REMARK ontology contract for P1"
```

---

### Task 2: Handoff unit tests for decorate + physics (P3–P4 coverage)

**Files:**
- Create: `tests/test_handoff.py`
- Read: `realm/handoff/decorate.py`, `realm/handoff/physics.py`, `realm/handoff/types.py`

**Interfaces:**
- Consumes: `NullDecorateAdapter`, `PolyAlaStubAdapter`, `select_adapter(name: str)`
- Consumes: `GeometrySelfCheck`, `get_physics_adapter(name: str) -> PhysicsFilterAdapter | None`
- Consumes: `BackboneArtifact(path_ca: Path, path_bb: Path, meta: dict)`
- Consumes: `DecorateRequest(backbone, sequence=None, poly_ala=True)`
- Produces: tests proving Null SKIP, polyala OK file, physics report dict

- [ ] **Step 1: Write failing tests**

Create `tests/test_handoff.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from realm.handoff.decorate import NullDecorateAdapter, PolyAlaStubAdapter, select_adapter
from realm.handoff.physics import GeometrySelfCheck, get_physics_adapter
from realm.handoff.types import BackboneArtifact, DecorateRequest
from realm.validate.pdb_write import write_mold_pair


def _ring(n: int = 8) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([3.8 * np.cos(t), 3.8 * np.sin(t), 0.05 * np.sin(2 * t)])


def test_decorate_null_skip(tmp_path: Path):
    paths = write_mold_pair(tmp_path, "m", _ring(8), source="crit", rank_score=0.1)
    art = BackboneArtifact(Path(paths["path_ca"]), Path(paths["path_bb"]))
    res = NullDecorateAdapter().decorate(DecorateRequest(backbone=art))
    assert res.status == "SKIP"
    assert res.path_decorated is None
    assert res.adapter == "null"


def test_decorate_polyala_writes_file(tmp_path: Path):
    paths = write_mold_pair(tmp_path / "molds", "m", _ring(8), source="crit", rank_score=0.1)
    art = BackboneArtifact(Path(paths["path_ca"]), Path(paths["path_bb"]))
    res = PolyAlaStubAdapter().decorate(DecorateRequest(backbone=art, poly_ala=True))
    assert res.status == "OK"
    assert res.path_decorated is not None
    assert res.path_decorated.is_file()
    text = res.path_decorated.read_text(encoding="utf-8")
    assert "CB" in text or " CB " in text


def test_physics_geometry_on_bb(tmp_path: Path):
    paths = write_mold_pair(tmp_path, "m", _ring(10), source="coutsias", rank_score=1.0)
    report = GeometrySelfCheck().filter(Path(paths["path_bb"]))
    assert report.adapter == "geometry_self_check"
    assert report.status in ("OK", "WARN", "FAIL")
    assert "ca_bond_mean" in report.metrics
    assert get_physics_adapter("none") is None
    assert get_physics_adapter("geometry") is not None


def test_select_adapter_null():
    a = select_adapter("null")
    assert a.name == "null"
```

- [ ] **Step 2: Run tests (expect PASS if adapters already correct)**

Run: `pytest tests/test_handoff.py -v`

Expected: all PASS. If polyala fails path layout (`parent.parent / "decorated"`), fix `PolyAlaStubAdapter.decorate` to write beside `path_bb` when no `molds/` parent:

```python
# preferred fix in decorate.py if tests fail:
out_dir = bb.parent / "decorated" if bb.parent.name != "molds" else bb.parent.parent / "decorated"
```

- [ ] **Step 3: Re-run until green**

Run: `pytest tests/test_handoff.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_handoff.py realm/handoff/decorate.py
git commit -m "test: handoff decorate and physics adapter contracts"
```

---

### Task 3: Proposal smoke test for CLI ensemble (P2 gate)

**Files:**
- Create: extend `tests/test_handoff.py` with smoke using generate API (not full Coutsias if slow)
- Modify: `realm/handoff/generate.py` only if Crit-only path broken

**Interfaces:**
- Consumes: `generate_crit_ensemble(knobs, *, N, n_zeros=14, ...) -> list[MoldRecord]`
- Consumes: `merge_and_rank(molds, *, top_k=8) -> list[MoldRecord]`
- Consumes: `MoldRecord.source`, `.xyz`, `.rank_score`
- Produces: test that Crit ensemble non-empty and top-k ordered

- [ ] **Step 1: Write Crit-only unit smoke (no network, no long Coutsias)**

Append to `tests/test_handoff.py`:

```python
def test_generate_crit_merge_rank_ordered():
    pytest.importorskip("json")
    from pathlib import Path
    import json
    from realm.handoff.generate import generate_crit_ensemble, merge_and_rank

    p = Path("evolve_result.json")
    if not p.is_file():
        pytest.skip("need evolve_result.json")
    kn = json.loads(p.read_text(encoding="utf-8"))["best_knobs"]
    molds = generate_crit_ensemble(kn, N=8, n_zeros=14, prefer_maxop=False)
    assert len(molds) >= 1
    ranked = merge_and_rank(molds, top_k=3)
    assert len(ranked) <= 3
    scores = [m.rank_score for m in ranked]
    assert scores == sorted(scores)
    assert all(m.source == "crit" for m in ranked)
    assert all(m.xyz.shape[1] >= 3 for m in ranked)
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_handoff.py::test_generate_crit_merge_rank_ordered -v`

Expected: PASS (may take ~30s for Keymaker forges). If empty molds, check `forge_crit_geometry` templates for N=8.

- [ ] **Step 3: Manual CLI smoke (document in commit message)**

Run:

```bash
python handoff_export.py -N 8 --top-k 3 --sources crit --decorate null --physics geometry --out-dir out/handoff_plan_smoke
```

Expected: `out/handoff_plan_smoke/index.json` exists; `molds/*_ca.pdb` and `*_bb.pdb` present; index `ontology` contains `not_lambda_eq_gamma`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_handoff.py
git commit -m "test: Crit ensemble rank smoke for handoff generate"
```

---

### Task 4: Structure mode for export (spec §2.3)

**Files:**
- Modify: `realm/handoff/generate.py` — add `generate_structure_ensemble`
- Modify: `handoff_export.py` — `--mode proposal|structure`, `--pdb`
- Test: `tests/test_handoff_structure.py`

**Interfaces:**
- Consumes: `pdb_batch.rank_one` or `forge_mold_pack` + pack templates
- Consumes: `load_ca_cyclic_band(path, with_resnames=True)`, `fetch_pdb`
- Produces: `generate_structure_ensemble(pdb_id, knobs, *, top_k) -> list[MoldRecord]` with `source="crit"` from selected pack templates, optional Coutsias scored vs native

- [ ] **Step 1: Write failing test**

Create `tests/test_handoff_structure.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from realm.handoff.generate import generate_structure_ensemble


def test_structure_ensemble_from_local_pdb():
    kn_path = Path("evolve_result.json")
    pdb_path = Path("data/pdb/1CSA.pdb")
    if not kn_path.is_file() or not pdb_path.is_file():
        pytest.skip("need evolve_result.json and data/pdb/1CSA.pdb")
    kn = json.loads(kn_path.read_text(encoding="utf-8"))["best_knobs"]
    molds = generate_structure_ensemble(
        "1CSA",
        kn,
        n_zeros=14,
        top_k=4,
        include_coutsias=False,
    )
    assert len(molds) >= 1
    assert all(m.xyz.ndim == 2 and m.xyz.shape[1] >= 3 for m in molds)
    assert all(m.source in ("crit", "coutsias") for m in molds)
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_handoff_structure.py::test_structure_ensemble_from_local_pdb -v`

Expected: FAIL `ImportError` or `generate_structure_ensemble` not defined

- [ ] **Step 3: Implement `generate_structure_ensemble`**

Add to `realm/handoff/generate.py`:

```python
def generate_structure_ensemble(
    pdb_id: str,
    knobs: dict[str, Any],
    *,
    n_zeros: int = 14,
    top_k: int = 8,
    include_coutsias: bool = True,
    soft_T: float = 0.04,
    defect_beta: float = 0.20,
) -> list[MoldRecord]:
    """Structure mode: self_fit_dense mold pack vs native CA; export pack templates."""
    from realm.sequence_features import sequence_residue_weights
    from realm.validate.length_policy import policy_for
    from realm.validate.mold_bank import forge_mold_pack
    from realm.validate.pdb_io import fetch_pdb, load_ca_cyclic_band

    path = fetch_pdb(pdb_id)
    loaded = load_ca_cyclic_band(path, lo=6, hi=40, with_resnames=True)
    xyz, resnames, _chain = loaded  # type: ignore[misc]
    n_ca = int(xyz.shape[0])
    pol = policy_for(n_ca, base_beta=float(defect_beta), sectors_mode="adaptive")
    mold_rw = None
    if pol.defect_tie and float(pol.seq_mold_mix) > 1e-12:
        mold_rw = sequence_residue_weights(resnames, mix=float(pol.seq_mold_mix))
    _mm, pack, fit_diag, _h = forge_mold_pack(
        xyz,
        knobs,
        N=max(n_ca, 7),
        n_zeros=int(n_zeros),
        n_sectors=pol.n_sectors,
        soft_T=float(pol.soft_T),
        multimode_mode="self_fit_dense",
        multimode=None,
        omega_scales=pol.omega_scales,
        defect_tie=pol.defect_tie,
        height_refine=pol.height_refine,
        residue_weights=mold_rw,
    )
    molds: list[MoldRecord] = []
    thetas = pack.get("thetas")
    import numpy as np
    th = np.asarray(thetas, dtype=float).ravel() if thetas is not None else np.zeros(0)
    op = pack.get("operator")
    gap = float(op.mean_gap) if op is not None else None
    for si, pts in enumerate(pack.get("templates") or []):
        arr = np.asarray(pts, float)[:, :3]
        molds.append(
            MoldRecord(
                source="crit",
                N=int(arr.shape[0]),
                xyz=arr,
                rank_score=float(si),  # order; refined below if fit_diag
                method="structure_self_fit_dense",
                twist=float(th[si]) if si < th.size else None,
                maxop_gap=gap,
                meta={"fit": fit_diag, "pdb_id": pdb_id.upper(), "sector": si},
            )
        )
    if include_coutsias:
        molds.extend(generate_coutsias_ensemble(N=n_ca, n_starts=10, max_roots=4))
    return merge_and_rank(molds, top_k=top_k)
```

Note: Prefer scoring Crit templates by Kabsch softmin to native if easy — optional refinement:

```python
from realm.validate.decoys import score_geometry_vs_crit
# after building each mold, set rank_score = score_geometry_vs_crit(xyz, [arr], soft_T=soft_T)["mean_dist"]
```

Use that for Crit molds so lower score = better native fit.

- [ ] **Step 4: Wire CLI**

In `handoff_export.py` add:

```python
p.add_argument("--mode", choices=("proposal", "structure"), default="proposal")
p.add_argument("--pdb", type=str, default=None, help="PDB id for --mode structure")
```

Branch in `main`:

```python
if args.mode == "structure":
    if not args.pdb:
        logger.error("--mode structure requires --pdb")
        return 2
    from realm.handoff.generate import generate_structure_ensemble
    sources = {s.strip().lower() for s in args.sources.split(",") if s.strip()}
    molds = generate_structure_ensemble(
        args.pdb,
        knobs,
        n_zeros=int(args.k),
        top_k=int(args.top_k),
        include_coutsias=("coutsias" in sources),
    )
else:
    # existing proposal path
    ...
```

- [ ] **Step 5: Run tests + structure smoke**

Run:

```bash
pytest tests/test_handoff_structure.py -v
python handoff_export.py --mode structure --pdb 1CSA --top-k 3 --sources crit --decorate null --physics geometry --out-dir out/handoff_struct_smoke
```

Expected: tests PASS; PDBs under `out/handoff_struct_smoke/molds/`.

- [ ] **Step 6: Commit**

```bash
git add realm/handoff/generate.py handoff_export.py tests/test_handoff_structure.py
git commit -m "feat: structure-mode handoff ensemble from native CA self_fit"
```

---

### Task 5: CLI flag parity with spec (§7.2)

**Files:**
- Modify: `handoff_export.py`

**Interfaces:**
- Produces CLI: `--mode`, `--pdb`, `--sequence`, `--poly-ala` (or keep polyala via decorate), existing flags

- [ ] **Step 1: Add sequence handling**

```python
p.add_argument("--sequence", type=str, default=None, help="1-letter or 3-letter seq for resnames")
```

Helper:

```python
def _resnames_from_sequence(seq: str | None, N: int) -> list[str] | None:
    if not seq:
        return None
    s = seq.strip()
    # if length == N and all alpha: treat as 1-letter
    aa1 = {
        "A": "ALA", "G": "GLY", "V": "VAL", "L": "LEU", "I": "ILE", "P": "PRO",
        "F": "PHE", "Y": "TYR", "W": "TRP", "S": "SER", "T": "THR", "C": "CYS",
        "M": "MET", "N": "ASN", "Q": "GLN", "D": "ASP", "E": "GLU", "K": "LYS",
        "R": "ARG", "H": "HIS",
    }
    if len(s) == N and s.isalpha():
        return [aa1.get(c.upper(), "GLY") for c in s]
    # space/comma separated 3-letter
    parts = [p.strip().upper() for p in s.replace(",", " ").split() if p.strip()]
    if len(parts) == N:
        return parts
    raise SystemExit(f"--sequence length must match N={N}")
```

Pass `resnames` into `write_mold_pair(..., resnames=resnames)`.

- [ ] **Step 2: Smoke**

```bash
python handoff_export.py -N 6 --sequence GGGGGG --sources crit --top-k 2 --out-dir out/handoff_seq
```

Expected: PDB residue names GLY; exit 0.

- [ ] **Step 3: Commit**

```bash
git add handoff_export.py
git commit -m "feat: handoff CLI --mode structure and --sequence resnames"
```

---

### Task 6: Optional PyRosetta adapter (P5)

**Files:**
- Modify: `realm/handoff/decorate.py`
- Test: `tests/test_handoff.py` (skip if no pyrosetta)

**Interfaces:**
- Produces: `PyRosettaAdapter` with `available()` False when import fails; `decorate` never raises into CLI uncaught

- [ ] **Step 1: Write skippable test**

```python
def test_pyrosetta_adapter_available_flag():
    from realm.handoff.decorate import PyRosettaAdapter
    a = PyRosettaAdapter()
    assert isinstance(a.available(), bool)
    if not a.available():
        pytest.skip("pyrosetta not installed")
```

- [ ] **Step 2: Implement stub adapter**

```python
class PyRosettaAdapter:
    name = "pyrosetta"

    def available(self) -> bool:
        try:
            import pyrosetta  # noqa: F401
            return True
        except Exception:
            return False

    def decorate(self, req: DecorateRequest) -> DecorateResult:
        if not self.available():
            return DecorateResult(None, self.name, "SKIP", note="pyrosetta not installed")
        try:
            import pyrosetta
            # Minimal: init once, load pose from bb, dump as "decorated" without full design
            pyrosetta.init("-mute all")
            pose = pyrosetta.pose_from_pdb(str(req.backbone.path_bb))
            out = req.backbone.path_bb.parent.parent / "decorated"
            out.mkdir(parents=True, exist_ok=True)
            out_path = out / (req.backbone.path_bb.stem + "_pyrosetta.pdb")
            pose.dump_pdb(str(out_path))
            return DecorateResult(out_path, self.name, "OK", note="pose load/dump only")
        except Exception as exc:
            return DecorateResult(None, self.name, "ERROR", note=str(exc))
```

Register in `get_decorate_adapters()` after polyala.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_handoff.py -v`

Expected: PASS (pyrosetta test skipped without install)

- [ ] **Step 4: Commit**

```bash
git add realm/handoff/decorate.py tests/test_handoff.py
git commit -m "feat: optional PyRosetta decorate adapter (import-guarded)"
```

---

### Task 7: Dual-gate safety + plan doc sync

**Files:**
- Modify: `docs/superpowers/plans/2026-07-30-handoff-protocol-plan.md`
- Optional: one-line assert in test that `policy_for` still matches locked soft_T for n=12

**Interfaces:**
- Consumes: `policy_for(12).soft_T == 0.036` (production lock)

- [ ] **Step 1: Add regression guard**

In `tests/test_handoff.py`:

```python
def test_handoff_does_not_alter_length_policy():
    from realm.validate.length_policy import policy_for
    p = policy_for(12, base_beta=0.20)
    assert abs(p.soft_T - 0.036) < 1e-12
    assert p.seq_mix == 0.0
    assert abs(p.face_weight - 0.08) < 1e-12
```

- [ ] **Step 2: Run full handoff-related suite**

```bash
pytest tests/test_pdb_write.py tests/test_handoff.py tests/test_handoff_structure.py tests/test_dual.py::test_length_policy_table_baseline_locked -q
```

Expected: all PASS

- [ ] **Step 3: Update phase status in plan markdown**

Edit `docs/superpowers/plans/2026-07-30-handoff-protocol-plan.md` table:

```markdown
| P1 | DONE |
| P2 | DONE (+ structure mode from execution plan Task 4) |
| P3 | DONE |
| P4 | DONE |
| P5 | DONE (import-guarded) |
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_handoff.py docs/superpowers/plans/2026-07-30-handoff-protocol-plan.md docs/superpowers/plans/2026-07-30-handoff-protocol-execution.md
git commit -m "docs+test: handoff plan complete; dual-gate policy guard"
```

---

## Self-review (author checklist)

### Spec coverage
| Spec section | Task |
|--------------|------|
| §4 Multi-level PDB | Task 1 (verify P1) |
| §2–3 Generate/rank Crit+Coutsias | Task 3 |
| §2.3 structure mode | Task 4 |
| §5 Decorate stubs | Task 2, Task 6 |
| §6 Physics | Task 2 |
| §7 CLI flags | Task 4–5 |
| §8 Tests table | Tasks 1–3, 7 |
| Dual-gate safety | Task 7 |
| Ontology never λ=γ | Task 1 REMARK test |

### Placeholder scan
No TBD / “implement later” without code. Gemini re-implementation of P1 explicitly forbidden in Global Constraints and Task 1.

### Type consistency
- `write_ca_pdb(path, xyz, ...)` path-first (existing)
- `MoldRecord(source, N, xyz, rank_score, method, twist, maxop_gap, meta)`
- `DecorateResult.status in {OK, SKIP, ERROR}`
- `PhysicsReport.status in {OK, WARN, FAIL}`

---

## Out of scope (do not do in this plan)

- Changing dual-gate ranking knobs / LengthPolicy mid-floor tables for enrichment
- Scaling N≥20 dual-gate campaign
- Full Rosetta design / packing optimization
- OpenMM energy minimization as required CI step

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-30-handoff-protocol-execution.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

**Which approach?**
