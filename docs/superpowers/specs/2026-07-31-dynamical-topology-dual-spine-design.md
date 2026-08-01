# Design: Dynamical Topology Dual Spine + Navigator Menu

**Date:** 2026-07-31  
**Status:** Implemented (D1–D5 on feature branch)  
**Approach:** Dual spine (measure + control) with guided menu for non-CLI users  
**Primary academic source:**  
`ACADEMIC/PERSISTENT TOPOLOGICAL FEATURES IN.pdf` (Gardinazzi et al., arXiv:2410.11042 — zigzag persistence across layers)  
**Repo ontology:** AXiomZ G1 — ζ substrate seed only; operational = Crit / dual-gate / Job manifold; **never λ=γ**  
**Related:**  
- `2026-07-31-academic-kb-knowledge-integration-design.md` (P1–P6 + H1 shipped)  
- `2026-07-31-coherence-os-v2-design.md`  
- `2026-07-31-oilfield-job-coherence-os-design.md`  
- `realm/ontology.py`, `realm/kb_geometry/*`, `realm/sheaf_backend.py`, `realm/aqft_local.py`  

---

## 0. Problem and non-goals

### Problem
The project already walks an algebraic-topology path (Crit filtration, sheaf MaxOp L, AQFT dual fingerprints, Job multi-scale / TREND_ROLLUP) and has partial transfers from the zigzag LLM paper (window H0, kNN, phases). Those pieces are **scattered**. Missing is a **maximal effective configuration**: one dynamical engine with two disciplined reads (science measure + fixed-point control), plus a **menu** so non-CLI users get the same effects without memorizing flags.

### Human L0
1. Intuition predated academic zigzag/AQFT reading; consolidate the *dynamic*.  
2. Dual spine **C**: measure the dynamic **and** topology-informed OS stop.  
3. Approach **2**: true stage-axis zigzag engine + dual consumers (not thin-only, not full H1/prune product).  
4. Add **navigator menu** for non-CLI users, same effect as CLI.

### Goals
1. One **DynamicalTopology** engine: ordered stages → complexes → zigzag-faithful birth/death along the stage axis.  
2. **Measure interface:** reports for science annex / TREND / ledger (`not_acceptance: true`).  
3. **Control interface:** `topology_stable(K)` participates in fixed-point **only** with `is_solved ∧ empty free-param board`; pin never written.  
4. **Sheaf/AQFT dual:** MaxOp L / frustration / aqft_local remain spatial co-fingerprint; not replaced by graph Laplacian.  
5. **Navigator menu:** keyboard-driven wizard that shells into existing CLIs/library entrypoints.  
6. Domain stage builders: Job OS cycles, handoff rounds, Crit windows.  
7. Provenance: arXiv:2410.11042 + AXiomZ axioms on every report.

### Non-goals
- Probe real LLM transformer layers.  
- Retune dual-gate LengthPolicy or Job QC pin from topology scores.  
- Replace MaxOp as operational sheaf L.  
- Full paper H1 + layer-pruning product as v1 ship gate.  
- Full GUI/web app (menu is terminal-first).  
- Edit pin numbers inside the wizard.

### Ontology (locked)

| Role | Meaning |
|------|---------|
| **Substrate** | ζ seeds / raw series / stage point clouds |
| **Time dual** | Zigzag (or faithful stage-axis barcode) across stages |
| **Space dual** | Cellular sheaf MaxOp L on Crit cycle |
| **Pin** | LengthPolicy + Job QC — read-only every cycle |
| **Free control** | stability-K / topo-stability / window budget only |
| **Never** | λ=γ; enrichment/topology as ACCEPTANCE alone |

---

## 1. Architecture

```text
 stage_0 → stage_1 → … → stage_T
      │         │              │
   complex   complex        complex
      └──── DynamicalTopology engine ────┘
                     │
       ┌─────────────┴─────────────┐
       ▼                           ▼
  MEASURE                      CONTROL
  DynamicalTopologyReport      topology_stable(K)
  TREND / science annex        ∧ is_solved ∧ empty board
       │                           │
       └────── pin read-only ──────┘
                     │
              Navigator menu
              (wizard → same CLIs)
```

### Units

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| **Stage builder** | Domain → ordered list of point clouds / 1-D series | Job OS / Crit / handoff artifacts |
| **Complex builder** | Per-stage kNN (default) or Crit sublevel complex | `kb_geometry.graph`, Crit filtration |
| **Zigzag engine** | Birth/death along stage axis; intersection layers when feasible | numpy |
| **Descriptors** | Phases, long/short, barcode summary | engine output |
| **Control hook** | `topology_stable` for OS stop flags | descriptors + existing `is_solved` |
| **Sheaf dual reporter** | Optional gap/frustration from existing path | `sheaf_backend`, `aqft_local` |
| **Navigator menu** | Interactive shell over CLIs | job_coherence, handoff_coherence, engine report API |

---

## 2. Stage definitions

| Domain | Stage sequence | Point cloud / field |
|--------|----------------|---------------------|
| **Job OS** | `cycle_01 … cycle_N` after observe | Regime channel cloud and/or primary series windows |
| **Handoff coherence** | negotiate rounds | Free-param trajectory + optional science probe (info) |
| **Crit / protein** | Windows on S¹ action / multi-seed Crit packs | Persistence heights or Crit θ* embeddings |

Same engine API; only stage builders differ.

---

## 3. Engine API (contract)

```text
build_stages_job(run_dir | series_sequence) -> list[Stage]
build_stages_crit(action | filtration) -> list[Stage]
build_stages_handoff(ledger) -> list[Stage]

run_dynamical_topology(stages, *, knn_k=5, long_frac=0.25) -> DynamicalTopologyReport

topology_stable(report, *, prev_report=None, K=1, drop_tol=τ) -> bool
```

### DynamicalTopologyReport (required fields)

```json
{
  "kind": "dynamical_topology",
  "not_acceptance": true,
  "ontology": "dynamical_topology_dual_spine_not_lambda_eq_gamma",
  "kb_source": "arXiv:2410.11042 + AXiomZ dual spine",
  "transfer_note": "stages as discrete time (not LLM layers)",
  "n_stages": 0,
  "bars": [],
  "n_long": 0,
  "n_short": 0,
  "phases": {"labels": [], "dominant": null},
  "sheaf_dual": null,
  "pin_writable": false,
  "acceptance_writable": false
}
```

v1 may implement a **faithful stage-axis barcode** (kNN per stage + merge tracking / intersection approximation) if full fast-zigzag library is unavailable; contract and report shape stay fixed. Must improve on current “window H0 only” by treating **stages as time**, not only scale within one series.

---

## 4. Control rule (pin-safe)

**SOLVED when flag `--topo-stability` (or menu equivalent) is on:**

```text
is_solved(obs, thr, params)
  AND free-param proposal board empty
  AND topology_stable for K consecutive cycles
```

**Default without flag:** existing fixed-point only (backward compatible).

### `topology_stable` v1

All of:

1. Current report exists and `n_stages >= 1`.  
2. Dominant phase ∈ {`stable`, `emit`} **or** long-bar count does not drop more than relative `drop_tol` vs previous cycle.  
3. No hard pin fail (pin still from existing verify paths).

**Forbidden:** writing LengthPolicy, Job mono ε, pack required sets, or soft_T from topology.

---

## 5. Measure wiring

| Consumer | Action |
|----------|--------|
| Job OS | Write `DYNAMICAL_TOPOLOGY.json` per cycle when enabled; feed TREND_ROLLUP |
| Handoff coherence | Optional report on negotiate rounds |
| Crit path | Upgrade `with_zigzag` to stage-axis engine when available |
| Science annex | Attach report under `not_acceptance` theory fields |

---

## 6. Navigator menu

### Entry

```bash
python realm_menu.py
# or
python -m realm.menu
```

### Top-level items

1. Job OS — fixture quick smoke  
2. Job OS — custom paths (wizard)  
3. Catalog runs (`--catalog`)  
4. Dynamical topology report (on last run or path)  
5. Handoff coherence (protein)  
6. Open docs / show LATEST path  
0. Exit  

### Wizard behavior

- Prompt for LAS / MicroPulse / survey / EOW paths (Enter = skip).  
- Y/N: regime, science, topo-stability, chunk inspect.  
- Numeric: max_rows, stability_k, max_depth_mono_violations (with safe defaults).  
- **Confirm screen:** print equivalent CLI one-liner; require Enter to run.  
- **Execute:** subprocess or in-process call to existing modules — **no duplicated negotiate logic**.  
- **Summary:** solved/stop, paths to COHERENCE, TREND_ROLLUP, PARTNER_RECIPE, INDEX.

### Constraints

- Prefer **stdlib** (`input` loops); Windows-friendly.  
- Pin parameters displayed read-only if shown; not editable in basic mode.  
- Menu does not invent a second OS.

---

## 7. Phased delivery

| Phase | Deliverable | Success |
|-------|-------------|---------|
| **D0** | This spec approved + committed | Human gate |
| **D1** | `realm/dynamical_topology/` engine + synthetic tests | Two-phase synthetic → long bars in stable region |
| **D2** | Job OS + handoff MEASURE wire | Report files on runs |
| **D2b** | Navigator menu: smoke, catalog, docs, topology report | Non-CLI path equals CLI smoke |
| **D3** | CONTROL `--topo-stability` + menu toggle | Flag on ⇒ SOLVED needs topology_stable |
| **D4** | Crit stage builder + sheaf dual co-report | Crit path optional dual fingerprint |
| **D5** | Docs: time zigzag vs space sheaf diagram in JOB_OS / ontology note | User-facing clarity |

---

## 8. Testing

| Test | Assert |
|------|--------|
| Synthetic dual phase | Long bars dominate stable phase |
| Pin invariant | No soft_T / mono ε write in dynamical_topology package |
| Control off | Existing Job/handoff SOLVED unchanged |
| Control on | Unstable topology blocks SOLVED despite is_solved slice if board empty but topo fails |
| Menu dry-run | Builds correct argv / kwargs for fixture smoke |
| Report schema | `not_acceptance`, `pin_writable=false` always |
| Windows | Menu + Job smoke on Windows (dev target) |

---

## 9. Success criteria

1. One engine, two interfaces (measure + control), pin tests green.  
2. Menu achieves fixture Job OS smoke without manual flags.  
3. Provenance cites arXiv:2410.11042 + AXiomZ.  
4. Sheaf MaxOp remains operational spatial dual; zigzag is temporal dual.  
5. No ACCEPTANCE from topology score alone.

---

## 10. H₁ consistency

| Loop | Restriction |
|------|-------------|
| Zigzag ↔ pin | Topology never writes pin |
| Control ↔ free params | Only K / stop; not pack/soft_T |
| Menu ↔ CLIs | Menu is pure UI shell |
| Sheaf L ↔ graph λ1 | Graph λ1 info-only; MaxOp operational |
| Science ↔ SHIP | Measure always `not_acceptance` |

---

## Appendix A — L0 log

1. User: algebraic topology intuition pre-academia; AQFT/connections; consolidate maximal config around zigzag paper.  
2. Choice **C**: dual spine measure + control.  
3. Approach **2**: true stage-axis engine (not thin-only, not full prune product).  
4. Add navigator menu for non-CLI users.  
5. Design approved (human: “apprive”).  

## Appendix B — Paper ↔ repo dual

| Paper concept | Repo dual |
|---------------|-----------|
| Layers as time | Stages (cycles / Crit windows / rounds) |
| kNN filtration | Complex builder |
| Zigzag birth/death across layers | Engine along stage axis |
| Short / long features | rearrange vs stable phases |
| Four processing phases | phase_summary / dominant |
| Layer pruning showcase | Horizon (not v1 control) |
| Static PH limitation | Motivation for dual spine vs snapshot-only |
