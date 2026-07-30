# Design: End-to-End Handoff Protocol (Geometric Engine → Chemistry Bridge)

**Date:** 2026-07-30  
**Status:** L3-ready draft (topological brainstorm)  
**Branch context:** `feat/zeta-kinematic-resonance`  
**Primary metric:** Downstream-openable files (BioPython / Rosetta / MD load without error)

---

## 0. Problem and non-goals

### Problem
The geometric engine produces coordinate-free Crit monodromies and Coutsias closed CA rings, then embeds them in R³. Commercial value as an **upstream sieve** requires a **handoff contract** into chemistry tools that decorate sidechains and run brief physics filters.

### Non-goals (v1)
- Beating dual-gate enrichment beyond the locked baseline via export
- λ=γ claims or HF protein-LM decoration
- Hard dependency on PyRosetta/OpenMM in CI
- Mass 100+ PDB campaigns
- Scaling N≥20 as a prerequisite (optional later phase)

### Ontology (locked)
- ζ is **substrate seed** for Crit molds only
- Operational geometry = Crit / Coutsias projection in R³
- MaxOp L = dual / spectral action on **geometry’s** spectrum
- **Never λ=γ**

---

## 1. Pipeline architecture

```text
┌─────────────┐   ┌──────────────┐   ┌────────────────────┐
│  Generate   │ → │ Score/Rank   │ → │ Multi-level Export │
│ Crit+Couts. │   │ ensemble     │   │ CA + backbone PDB  │
└─────────────┘   └──────────────┘   └─────────┬──────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
            ┌───────────────┐        ┌─────────────────┐        ┌────────────────┐
            │ DecorateAdapter│        │ PhysicsFilter   │        │ index.json     │
            │ (optional)     │        │ Adapter (opt.)  │        │ (scores, meta) │
            └───────────────┘        └─────────────────┘        └────────────────┘
```

Stages are **sheaf sections** over the base “mold identity”; restriction maps are file formats and typed dicts.

| Stage | Input | Output | v1 implementation |
|-------|--------|--------|-------------------|
| Generate | N, knobs, seed spectra | Mold records (CA coords + meta) | Required |
| Score/Rank | Mold records | Ordered top-K | Required |
| Export | Ordered molds | `*_ca.pdb`, `*_bb.pdb`, REMARKs | Required |
| Decorate | `*_bb.pdb` (+ sequence or poly-ALA) | decorated PDB or skip | Stub + optional adapter |
| Physics | decorated or backbone PDB | JSON report | Geometry self-check required; external min optional |

---

## 2. Generation: Crit ∪ Coutsias ensemble

### 2.1 Crit molds
- Source: `forge_crit_geometry` / mold bank selection (`self_fit_dense` when a reference structure exists; **proposal mode** without native CA uses planar/multimode Crit bank with production knobs)
- Fields per mold:
  - `source: "crit"`
  - `N`, `xyz` `(N,3)`, `thetas`, `multimode`, `omega_scale_mult?`
  - `operator` fingerprint summary (mean_gap, …) optional diagnostic

### 2.2 Coutsias molds
- Source: `forge_coutsias_mold_bank` / `PrimeFoldingEngine.generate_closures`
- Fields:
  - `source: "coutsias"`
  - `N`, `xyz`, `twist_so2`, `residual`, `S_L` / total score

### 2.3 Proposal mode vs structure-conditioned mode
| Mode | When | Mold pick |
|------|------|-----------|
| **proposal** | No native PDB | Crit bank (fixed multimode/omega grid) + Coutsias multi-start; rank by internal scores only |
| **structure** | Native CA available | Existing self_fit / dual_score path; export top templates + best Coutsias blend candidates |

v1 CLI supports both (`--mode proposal|structure`).

---

## 3. Scoring / ranking for export

### 3.1 Score vector (lower better unless noted)
- Crit: Kabsch softmin to reference if structure mode; else self-consistency residual / mean pairwise mold distance diagnostic
- Coutsias: existing `score_conformation` / spectral action total
- Optional dual: sheaf defect softmin (policy-driven) — **off by default for export purity**

### 3.2 Ensemble merge
- Tag each mold with `rank_score`
- Sort ascending; take `--top-k` (default 8)
- Multi-MODEL PDB: one MODEL per mold; separate files for ca/bb levels

### 3.3 Dual-gate safety
- Export path **must not** change `policy_for` production numbers
- No new magic `n_ca` ladders in export code

---

## 4. Multi-level PDB export

### 4.1 Module
`realm/validate/pdb_write.py` (write-side complement to `pdb_io.py`)

### 4.2 CA-only file (`*_ca.pdb`)
- One ATOM per residue: name `CA`, element C
- Residue names: `GLY` default or user sequence if provided
- Chain ID configurable (default `A`)
- `CONECT` edges `i→i+1` and close `N→1`
- REMARK block (see §4.4)

### 4.3 Backbone file (`*_bb.pdb`)
Idealized peptide frame from CA positions:
- Place N, CA, C, O with standard bond lengths/angles and peptide plane continuity around the cycle
- Algorithm (v1):
  1. CA positions as given (centered optional)
  2. For each i: build local frame from `CA[i-1], CA[i], CA[i+1]`
  3. Offset N, C, O in that frame (published ideal geometry constants)
  4. Soft-adjust closure if needed without moving CA (document residual)
- Residue names: poly-GLY or provided sequence

### 4.4 REMARK contract
```text
REMARK   1 ENGINE 123abc-grok geometric handoff
REMARK   2 ONTOLOGY substrate_crit_projection_not_lambda_eq_gamma
REMARK   3 SOURCE crit|coutsias
REMARK   4 N <int>
REMARK   5 RANK_SCORE <float>
REMARK   6 METHOD <tag>
REMARK   7 TWIST <float optional>
REMARK   8 MAXOP_GAP <float optional>
```

### 4.5 Round-trip validation
- `parse_ca_trace(write_ca_pdb(...))` max |Δ| < 1e-3 (PDB 0.001 Å fixed-width format; no silent reordering)
- Writer does **not** reorder residues

---

## 5. Decorate pipeline stub

### 5.1 Types (`realm/handoff/types.py`)
```text
BackboneArtifact { path_ca, path_bb, meta }
DecorateRequest { backbone: BackboneArtifact, sequence: str | None, poly_ala: bool }
DecorateResult { path_decorated: Path | None, adapter: str, status: OK|SKIP|ERROR, note }
```

### 5.2 Protocol
```text
class DecorateAdapter(Protocol):
    name: str
    def available(self) -> bool: ...
    def decorate(self, req: DecorateRequest) -> DecorateResult: ...
```

### 5.3 Implementations (v1)
| Adapter | When | Behavior |
|---------|------|----------|
| `NullDecorateAdapter` | always | `SKIP` — documents external decorate |
| `PolyAlaStubAdapter` | always | Writes poly-ALA sidechain CB stubs on bb (optional light decorate) |
| `PyRosettaAdapter` | `import pyrosetta` succeeds | Pack/design stub interface; not required in CI |
| `BioPythonAdapter` | biopython present | Load/save validation only or simple mutate |

### 5.4 Registry
`get_decorate_adapters() -> list[DecorateAdapter]` returns available adapters in priority order; CLI `--decorate null|polyala|auto`.

---

## 6. Physics filter stub

### 6.1 Protocol
```text
class PhysicsFilterAdapter(Protocol):
    def available(self) -> bool: ...
    def filter(self, pdb_path: Path) -> PhysicsReport: ...
```

### 6.2 GeometrySelfCheck (always on)
- CA–CA bond lengths mean/std vs ideal ~3.8 Å  
- Cycle closure distance  
- Optional backbone peptide bond lengths if bb file  

### 6.3 External (optional)
- OpenMM / sander hooks later; same report schema  

### 6.4 PhysicsReport JSON
```json
{
  "status": "OK|WARN|FAIL",
  "adapter": "geometry_self_check",
  "ca_bond_mean": 3.81,
  "ca_bond_std": 0.05,
  "closure": 0.12,
  "notes": []
}
```

---

## 7. CLI and output layout

### 7.1 Entry point
`handoff_export.py` (repo root) or `python -m realm.handoff.cli`

### 7.2 Key flags
```text
--mode proposal|structure
--N 11
--knobs evolve_result.json
--sources crit,coutsias
--top-k 8
--out-dir out/handoff_run
--sequence GLY... | --poly-ala
--decorate null|polyala|auto
--physics geometry|none
```

### 7.3 Output tree
```text
out/handoff_run/
  index.json
  molds/
    000_crit_ca.pdb
    000_crit_bb.pdb
    001_coutsias_ca.pdb
    001_coutsias_bb.pdb
    ...
  decorated/          # if decorate ≠ null and adapter OK
  physics/            # *.json reports
```

### 7.4 index.json
Lists each mold: paths, source, scores, physics status, decorate status.

---

## 8. Testing (success metric = openable files)

| Test | Assert |
|------|--------|
| `test_write_ca_roundtrip` | parse back CA, max abs error < 1e-6 |
| `test_write_backbone_atom_names` | residues contain N,CA,C,O |
| `test_remark_ontology` | REMARK contains `not_lambda_eq_gamma` |
| `test_handoff_proposal_smoke` | top-k files exist; index valid JSON |
| `test_decorate_null_skip` | Null adapter returns SKIP |
| `test_physics_geometry` | self-check runs on bb |

No dual-gate regression required beyond “export code does not touch ranking policy.”

---

## 9. Phased delivery (implementation plan input)

| Phase | Deliverable | Gate |
|-------|-------------|------|
| **P1** | `pdb_write` CA + backbone + REMARKs + unit tests | Round-trip openable |
| **P2** | Generate Crit+Coutsias ensemble + rank + CLI + index.json | Smoke dump for N=11 |
| **P3** | Decorate Protocol + Null + PolyAlaStub | Stub smoke |
| **P4** | Physics GeometrySelfCheck + JSON reports | Always-on self-check |
| **P5** | Optional PyRosetta/BioPython adapters | Import-guarded |

**W(I) ∈ W_phys when P1–P2 land and human accepts this spec.** P3–P5 complete the “full decorate pipeline stub” without blocking export value.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Idealized backbone geometry poor for Rosetta | Multi-level export; document CA as source of truth; iterate bb builder |
| Coutsias slow for large top-k | Cache banks; default top-k small; parallel later |
| Scope creep into full MD | Physics adapter hard-boundary; v1 = geometry self-check |
| Ontology leakage in REMARKs | Fixed REMARK template in tests |

---

## 11. Open questions (resolved in brainstorm)

| Q | A |
|---|---|
| First deliverable | End-to-end handoff protocol |
| Mold sources | Crit + Coutsias ranked ensemble |
| Atom levels | Multi-level CA + backbone |
| Success metric | Downstream-openable files |
| Decorate in v1 | Full pipeline stub (adapters optional) |

---

## 12. L3 sheaf consistency checklist

- [x] Generation outputs CA that Export consumes  
- [x] Export bb is what Decorate prefers; CA remains available  
- [x] Score tags appear in index.json and REMARKs (restriction maps agree)  
- [x] Decorate/Physics optional without breaking Generate→Export  
- [x] Ranking dual-gate path untouched  
- [x] Ontology REMARK on every written structure  

**Verdict (authoring pass):** ON_SHELL for v1 scope. Ready for human review before implementation.
