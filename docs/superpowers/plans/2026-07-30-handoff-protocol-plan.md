# Implementation Plan: Handoff Protocol P1–P5

**Spec:** [2026-07-30-handoff-protocol-design.md](../specs/2026-07-30-handoff-protocol-design.md)  
**Approved:** L3 human gate ON_SHELL

## PR / phase order

| Phase | Files | Done when | Status |
|-------|--------|-----------|--------|
| **P1** | `realm/validate/pdb_write.py`, `tests/test_pdb_write.py` | CA + bb write, REMARKs, round-trip tests | **DONE** |
| **P2** | `realm/handoff/generate.py`, `types.py`, `handoff_export.py` | Crit+Coutsias ensemble, rank, out-dir dump (+ structure mode) | **DONE** |
| **P3** | `realm/handoff/decorate.py` | Protocol + Null + PolyAlaStub | **DONE** |
| **P4** | `realm/handoff/physics.py` | GeometrySelfCheck JSON | **DONE** |
| **P5** | optional adapters | import-guarded only | **DONE** (import-guarded) |

## P1 tasks
1. `write_ca_pdb`, `write_backbone_pdb`, remark builder
2. Ideal N–CA–C–O from CA frame
3. Unit tests round-trip + atom names + ontology REMARK

## P2 tasks
1. MoldRecord dataclass
2. `generate_crit_ensemble`, `generate_coutsias_ensemble`
3. Rank merge + `write_ensemble`
4. CLI `handoff_export.py`

## Invariants
- Do not change `length_policy` production numbers
- Never λ=γ in REMARK/ontology strings
