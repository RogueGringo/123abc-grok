# Parent KB H1 Audit — Sheaf / PH libraries

**Date:** 2026-07-31  
**Status:** Audited + thin adapters shipped  
**Root:** `C:\LM_STUDIO_MODELS\01.AI-ML-NN-MATH-PHYSICS-KNOWLEDGE-DEVELOPMENT PROJECTS-KB-00-1JUN26`  
**Repo dual:** `realm/kb_geometry/` + existing `realm/sheaf_backend.py` (MaxOp)  

---

## Decision table

| Source | What it claims | Verdict | Action |
|--------|----------------|---------|--------|
| `PYTHON CODE LIBRARY-6/persistent_homology.py` | VR H0+H1 | **H0 broken** (components born 0, death ∞; no edge-scale merge deaths) | **Do not import.** Clean VR H0 in `realm/kb_geometry/rips_h0.py` |
| `LIBRARY-6/sheaf_laplacian_calibration_v0.3.py` | λ1 baseline on hypergraph | Useful **metric idea**; YAML wormhole schema not in-repo | **Reimplement λ1** on knn adjacency only |
| `LIBRARY-6/threshold_guidance_v0.1.md` | Provisional λ1 floors | Synthetic baseline; absolute floors fragile | Document: prefer **relative λ1 trends** across Job OS cycles |
| `LIBRARY-1/5 sheaf_engine.py` | Codebase-as-manifold “consciousness” sheaf | Different product; heavy/coupling | **Do not import.** Keep MaxOp `sheaf_backend` as operational L |
| `LIBRARY-1/5 sheaf.py` | Companion sheaf stack | Same | **Do not import** |
| `LIBRARY-3/higher_cohomology`, `persistent_fabric` | TUI / fabric experiments | Out of dual-gate scope | **Defer** |
| SupaTrupa drilling stack | Full MWD app | Separate product | Job OS already covers handoff; no bulk import |
| ACADEMIC PDFs | Already integrated P1–P6 | Done | — |

---

## Restriction maps (ontology)

| Parent concept | Repo stalk | Pin interaction |
|----------------|------------|-----------------|
| VR H0 barcode | `kb_geometry.rips_h0` / regime multi-scale | Info only |
| Graph λ1 | `algebraic_connectivity` on knn | Info only; **never** confusable with λ=γ |
| MaxOp cellular sheaf L | `realm/sheaf_backend` | Operational geometry for Crit molds |
| Wormhole λ1 floor ~23 | **Rejected** as absolute gate | Relative trends only |

---

## Shipped adapters (this H1)

1. `vietoris_rips_h0(points)` — correct elder-rule H0  
2. `algebraic_connectivity(adj)` — λ1 of D−A  
3. Optional wire into regime `graph_labels` path: λ1 reported alongside spectral labels  
4. This audit doc  

---

## Non-goals preserved

- No RF/maintenance accept gates  
- No retune soft_T / Job QC pin from λ1  
- No bulk copy of sheaf_engine into realm  
- No claim that parent λ1 = dual-gate success  

---

## Next (optional, not H1)

- H1 loop patterns from parent H1 code only after unit-tested rewrite  
- Path-config for optional external primed-topology already handled by `sheaf_backend`  
