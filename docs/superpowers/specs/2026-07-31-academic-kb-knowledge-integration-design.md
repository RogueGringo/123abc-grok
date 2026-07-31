# Design: Academic KB Knowledge Integration (A–D Stalks + E Horizon)

**Date:** 2026-07-31  
**Status:** Implemented P1–P6 + H1 parent-KB audit (VR H0 + λ1 adapters; no bulk import)  
**Human L0:** “all if possible” (A+B+C+D; E = parent-KB aperture later)  
**Source KB:** `C:\LM_STUDIO_MODELS\01.AI-ML-NN-MATH-PHYSICS-KNOWLEDGE-DEVELOPMENT PROJECTS-KB-00-1JUN26\ACADEMIC`  
**Repo:** `123abc-grok` — dual-gate / Crit / sheaf / Coherence OS v2 / Job OS  
**Related designs:** `2026-07-31-coherence-os-v2-design.md`, `2026-07-31-oilfield-job-coherence-os-design.md`, `ACTIVE_MAPPING.json`  

---

## 0. Problem and non-goals

### Problem
The ACADEMIC folder holds research-grade and tutorial knowledge (zigzag TDA, RLM long-context, learning theory, classical ML) that can **harden existing stalks** without inventing a third product. The risk is score-chase: RF accuracy, enrichment, or Gini impurity retuning pins. We need one **integration surface** so A–D attach under locked ontology.

### Human L0
- Primary ask: investigate ACADEMIC for implementable knowledge in-scope.  
- Choice: **all if possible** (A persistence, B science theory, C graph glue, D out-of-core inspect).  
- E (full parent KB) deferred as horizon unless needed for sheaf reuse.

### Goals
1. **Single package** `realm/kb_geometry/` (name flexible) or extend existing modules — **not** five CLIs.  
2. **A — Zigzag / multi-scale persistence** on Crit windows + Job OS regime windows.  
3. **B — Science theory harden:** holdout/PAC language, dual-gate science annex never ACCEPTANCE.  
4. **C — Graph geometry toolkit:** kNN / optional spectral helpers for multi-channel fibers (glue aid).  
5. **D — Out-of-core job inspect:** RLM-inspired chunked/recursive scan of huge LAS/SQL under Job OS.  
6. Pin invariants unchanged (protein LengthPolicy + Job QC pin).  
7. Provenance: every new descriptor cites ACADEMIC source ID + “info not accept.”

### Non-goals
- Train RF/DT as commercial accept for protein or MWD.  
- Retune `soft_T` / SOP bands from impurity or accuracy.  
- Full Petersen course reimplementation.  
- Embed LLM RLM product as required runtime.  
- Replace MaxOp sheaf L with arbitrary graph Laplacian without documenting dual.  
- Bulk-import entire parent KB (E) in v1.

### Ontology (locked)
| Role | Meaning |
|------|---------|
| **Substrate** | ACADEMIC PDFs + raw series / Crit fields |
| **Operational geometry** | Crit projection + dual-gate + job manifold |
| **Pin** | LengthPolicy + Job QC — never free |
| **Science** | Dual-gate / persistence / PAC reports — never SHIP alone |
| **Never** | λ=γ; ζ as eigenvalue target; enrichment-as-accept |

---

## 1. Architecture (one product, four stalks)

```text
┌──────────────────────────────────────────────────────────────┐
│  KB Geometry Integration Layer (v1)                          │
│  descriptors · reports · optional Job OS / science hooks     │
└───────────────┬──────────────────┬──────────────────┬────────┘
                │                  │                  │
        ┌───────▼──────┐   ┌───────▼──────┐   ┌──────▼───────┐
        │ A Zigzag PH  │   │ B Science    │   │ C Graph      │
        │ multi-scale  │   │ theory/annex │   │ kNN/spectral │
        └───────┬──────┘   └───────┬──────┘   └──────┬───────┘
                │                  │                  │
                └────────────┬─────┴──────────────────┘
                             │
                    ┌────────▼────────┐
                    │ D Out-of-core   │
                    │ chunk inspect   │──► Job OS execute path
                    └─────────────────┘
```

**Consumers (already in repo):**  
- Protein: `crit_action_filtration`, known-solutions science, handoff science channel.  
- Oilfield: `realm/job_os/regime.py`, `science.py`, `glue.py`, `loop.py`.  
- Sheaf: `realm/sheaf_backend.py` remains operational L; C is **fiber geometry helper**.

---

## 2. Stalk A — Zigzag / multi-scale persistence

### Source
Gardinazzi et al., *Persistent Topological Features in Large Language Models* (zigzag across layers; kNN filtration; birth/death descriptors; phase structure).

### Transfer (not LLM layers)
| Paper concept | Repo dual |
|---------------|-----------|
| Layers as time | **Windows** along holonomy scale, MD, or time |
| kNN filtration | Optional; default keep existing Vietoris/Crit filtration if present |
| Long-lived holes | Persistent Crit basins / regime clusters (signal) |
| Short-lived | Noise / rearrangement (not pin retune) |
| Layer pruning | **Horizon:** skip redundant windows in overnight science — not v1 |

### API sketch
```text
zigzag_window_barcode(series_or_crit, *, window_ids, homology_dims=(0,1))
  -> { bars, phases?, n_long, n_short, ontology_note }

phase_summary(barcode) -> { rearrange | stable | refine | emit }  # soft labels
```

### Wire-in
1. Protein: extend `crit_action_filtration` report with optional multi-window zigzag summary (flag `--with-zigzag`).  
2. Job OS: upgrade `regime.py` H0 barcode toward multi-scale / birth-death (keep SOLVED independent of barcode).

### Success
Unit test on synthetic 1D series: known two-scale structure yields long bar at coarse scale, short at fine noise.

---

## 3. Stalk B — Science theory harden (PAC / holdout language)

### Source
Petersen *Mathematics of Machine Learning* (PAC, Rademacher, VC, model selection, CV); dual-gate already in-repo.

### Transfer
| Theory idea | Repo dual |
|-------------|-----------|
| Train/test split | probe vs holdout tags (`known_solutions_ids`) |
| Generalization | science annex states **holdout** metrics separately from probe |
| Model selection | free-param SRM only — **not** pin SRM |
| Overfitting language | document risk if science score drives negotiate |

### Deliverables
1. `SCIENCE_THEORY.md` (short) under `docs/` or design appendix — operational glossary.  
2. Extend known-solutions / Job science annex JSON:  
   `split: probe|holdout`, `claim_class: informational`, `not_acceptance: true`.  
3. Optional: fail CI golden path if ACCEPTANCE written from science score (grep guard).

### Success
Test: science annex always contains `not_acceptance: true`; holdout ids never rewrite LengthPolicy.

---

## 4. Stalk C — Graph geometry toolkit

### Source
MoML: kNN, spectral clustering, PCA/JL/diffusion maps (as geometry, not full course).

### Transfer
| Tool | Use |
|------|-----|
| kNN graph | Optional fiber adjacency for Job multi-channel points |
| Spectral clustering | **Science-only** regime labels; not SOLVED gate |
| Diffusion / PCA | Optional dim reduction for glue diagnostics |

### API sketch
```text
knn_graph(X, k) -> adjacency
spectral_labels(adj, n_clusters) -> labels  # info only
```

### Wire-in
- `glue.py` / regime: optional graph-assisted structural score when depth/time domains partial.  
- Never mutates pin thresholds.

### Success
Synthetic 2-blob point cloud → two spectral labels; Job SOLVED unchanged when labels flip.

---

## 5. Stalk D — Out-of-core job inspect (RLM pattern)

### Source
Zhang et al., *Recursive Language Models* (prompt as env; REPL peek/decompose; recursive subcalls; compaction insufficient for dense access).

### Transfer (no required LLM)
| RLM idea | Job OS dual |
|----------|-------------|
| Prompt as env variable | Huge LAS/SQL path as external store |
| Peek / slice programmatically | Streaming row windows + index map |
| Recursive subcalls | Nested cycle inspect of chunk → merge obs |
| Cost-aware | Max chunks budget in RUN.json |

### Deliverables
1. `realm/job_os/chunk_inspect.py` (or under `kb_geometry`):  
   - stream LAS/SQL in depth/time chunks  
   - per-chunk observe → aggregate Observations  
2. CLI: `--chunk-rows N` / `--max-chunks M` on `job_coherence.py`  
3. Ledger records chunk plan (not full raw dump).

### Success
Fixture LAS oversized synthetic: full-load path OOM-risk avoided; aggregate pin+export still computable; SOLVED semantics preserved on small fixture.

---

## 6. Free params / pin interaction

| Change free domain? | v1 |
|---------------------|----|
| Protein LengthPolicy | **No** |
| Job free params | Optional: `window_scale` already; may add `chunk_rows` as free or CLI-only |
| Zigzag k / dims | CLI thresholds in config, not negotiate pin |
| Graph k | Config, science-only |

Any proposal that would write pin → `veto_pin`.

---

## 7. Phased implementation (all stalks, ordered)

| Phase | Stalks | Deliverable | Depends |
|-------|--------|-------------|---------|
| **P0** | — | This design accepted | — |
| **P1** | **A** | Zigzag/window barcode core + tests; wire optional flag to Crit filtration report | — |
| **P2** | **B** | Science annex schema + holdout language + guard tests | — |
| **P3** | **C** | knn/spectral helpers + optional Job regime info labels | P1 optional |
| **P4** | **A+C** | Job OS regime multi-scale barcode using A (+ optional C) | P1, P3 |
| **P5** | **D** | Chunk inspect for large LAS/SQL under Job OS | Job OS exists |
| **P6** | **B+D** | Science annex on chunked overnight job runs | P2, P5 |
| **H1 (E)** | Parent KB | Audit sheaf/PH libs in PYTHON CODE LIBRARY-* for import vs reimplement | After P1–P5 |

**Parallelism:** P1 and P2 independent; P3 after or with P1; P4 after P1+P3; P5 after Job OS (already on main); P6 last.

**Do not** ship RF predictive-maintenance notebook as a repo product.

---

## 8. Provenance & evidence

Every new report field:
```json
{
  "kb_source": "ACADEMIC/PERSISTENT TOPOLOGICAL FEATURES IN.pdf | arXiv:2410.11042",
  "transfer_note": "windows not LLM layers",
  "not_acceptance": true,
  "ontology": "kb_geometry_not_lambda_eq_gamma"
}
```

Ledger / PARTNER_RECIPE unchanged in role.

---

## 9. Testing matrix

| Test | Assert |
|------|--------|
| Zigzag synthetic | Long bar vs noise scale |
| Pin invariant | No LengthPolicy / job pin mutation in new code paths |
| Science annex | `not_acceptance` always true |
| Spectral labels | Do not flip `is_solved` |
| Chunk inspect | Large fixture aggregates without requiring full RAM load |
| Known-solutions | Holdout split labeled; probe ≠ accept |
| Guard | Grep: no soft_T write in kb_geometry / science annex |

---

## 10. H₁ consistency (sheaf sections)

| Loop | Restriction |
|------|-------------|
| A ↔ protein Crit | Same pin; zigzag observes Crit field only |
| A ↔ Job regime | Barcode in regime_report; SOLVED independent |
| B ↔ SHIP/ACCEPTANCE | Science never sets accept |
| C ↔ glue | Graph score optional; structural glue primary |
| D ↔ Job OS loop | Chunks feed same observe/negotiate; one ledger |
| C ↔ sheaf MaxOp | Document dual: MaxOp = operational geometry L; C = channel graph helper |
| E later ↔ A | Prefer existing PH/sheaf code if equivalent |

**Gini:** positive if phases deepen measurement hierarchy. Negative if RF/DL product forks off pin.

---

## 11. Horizon E — parent KB aperture

After P1–P5, audit (read-only first):
- `PYTHON CODE LIBRARY-*/sheaf*.py`, `persistent_homology.py`  
- SupaTrupa drilling docs  
Decide: **import / calibrate** vs keep thin in-repo implementations.

Not required for A–D v1 success.

---

## 12. Success criteria for design acceptance

- [ ] Human accepts **all A–D as stalks of one integration layer**  
- [ ] Pin non-negotiable; RF/DT not accept  
- [ ] Phase order P1→P6 clear; P1∥P2 allowed  
- [ ] Provenance fields specified  
- [ ] E deferred explicitly  
- [ ] No implementation until W(I) ∈ W_phys  

---

## Appendix A — L0 log

1. Investigate ACADEMIC for in-scope knowledge.  
2. Mapped 8 files: zigzag paper, RLM, MoML, cheat sheet, DT/RF tutorials.  
3. Human: **all if possible** → A+B+C+D, E horizon.  

## Appendix B — L1 filtration

| Bar | Approach | Verdict |
|-----|----------|---------|
| Longest | Unified KB geometry integration (this design) | Ship |
| Medium | Zigzag-only protein patch | Incomplete vs “all” |
| Medium | Science docs only | Incomplete |
| Short | Five independent ML tools | Pin fork — kill |
| Kill | RF maintenance as Job SOLVED | Ontology violation |

## Appendix C — ACADEMIC source map

| Artifact | Stalks |
|----------|--------|
| Persistent Topological Features in LLMs | A (primary), C (kNN filtration idea) |
| RLM arXiv:2512.24601 | D |
| Mathematics of Machine Learning | B, C (spectral/kNN/PCA) |
| ML cheat sheet | Reference only |
| Decision Trees / RF notebooks | Explicit non-goal as product; optional science-info later only with labels + pin lock |

---

## PR Plan (for later `/execute-plan`)

### PR 1: Zigzag window barcode core
- **Description:** Implement multi-window zigzag/barcode helpers + synthetic tests; optional Crit filtration report flag. No pin writes.
- **Files:** `realm/kb_geometry/` or `realm/validate/zigzag_windows.py`, tests, optional axiomz/fold_protocol hook
- **Dependencies:** None

### PR 2: Science annex holdout language
- **Description:** Schema + docs + known-solutions/Job science annex fields; CI/guard not_acceptance.
- **Files:** docs snippet, known_solutions report paths, job science annex, tests
- **Dependencies:** None

### PR 3: Graph kNN/spectral toolkit
- **Description:** knn_graph + spectral_labels helpers; tests; optional regime info labels.
- **Files:** `realm/kb_geometry/graph.py`, tests, optional job_os/regime hook
- **Dependencies:** None (soft: PR1)

### PR 4: Job regime multi-scale barcode
- **Description:** Wire A (+ optional C) into job_os regime reports; SOLVED independent.
- **Files:** `realm/job_os/regime.py`, tests
- **Dependencies:** PR 1

### PR 5: Out-of-core chunk inspect
- **Description:** Stream/chunk LAS (and SQL if present) under job coherence loop; ledger chunk plan; CLI flags.
- **Files:** `realm/job_os/chunk_inspect.py`, loop.py, job_coherence.py, tests
- **Dependencies:** None (Job OS already on main)

### PR 6: Chunked science overnight annex
- **Description:** Combine B+D for large-job science annex with holdout language.
- **Files:** science annex + chunk path, tests
- **Dependencies:** PR 2, PR 5
