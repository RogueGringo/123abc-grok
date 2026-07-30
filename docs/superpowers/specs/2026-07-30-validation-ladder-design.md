# Validation Ladder Design — Null Battery → sec≈k → Cyclic PDB Deep Dive

**Date:** 2026-07-30  
**Status:** Approved for implementation planning  
**Branch / context:** `feat/zeta-kinematic-resonance` after EVOLVED_SEAL R≈0.00453  
**Related:** prior design `2026-07-29-zeta-kinematic-resonance-design.md` (stub ontology flip)

---

## 1. Intent

Convert the sealed geometric–kinematic engine from **internal consistency** into **externally testable science**, without breaking ontology.

### Goals

1. **Phase 1 — Null battery:** Prove the sealed residual / mold fitness prefers real Riemann ζ seeds over null frequency seeds (scramble, GOE, Poisson), under fixed champion knobs and equal compute budget.
2. **Phase 2 — Strategy B (sec≈k):** Re-search sector count so geometric gap sample size approaches seed gap sample size; push `density_return` without destroying pin/occ seal.
3. **Phase 3 — Cyclic PDB deep dive:** One real cyclic peptide from RCSB/PDB; native conformation vs decoys scored on the projected moduli mold (not λ=γ).

### Non-goals (v1)

- Replacing AlphaFold / large-scale free folding.
- Mass 100+ PDB campaigns (scale after single-structure deep dive works).
- λ ≈ γ grocery matching or RH claims.
- GPU/NPU port of sheaf eigens (CPU multi-process remains the compute path).
- Full all-atom MD force fields as primary ranker.

### Ontology (locked)

- ζ zeros = higher-D scaffolding / spectral action seeds.  
- Geometry = projection off Crit(S).  
- Affine ax+b = expected projection signature.  
- **Pass metrics** = Crit residual components, mold occupancy/distance, decoy ranking enrichment.  
- **Never** score identity of sheaf eigenvalues to γₙ.

---

## 2. Success criteria

### Phase 1 hard gate (must pass before Phase 3 claims)

With **identical** champion knobs, N, k, sectors, and evaluation budget:

```
F_ζ  <  0.8 × min(F_scramble, F_GOE, F_Poisson)
```

Also report (diagnostic, not soft-pass alone):

- `dens_return_ζ` should be ≤ dens of each null (preferred).
- pin/coverage may be low for nulls *or* for ζ; **joint** (F, dens_return, corr) must favor ζ.
- If gate fails: **stop** before PDB claims; re-open residual design or knobs — do not “prove proteins” on a soft residual.

### Phase 2 success

- Find config with `n_sectors` in {8,10,12} (k=14) such that:
  - occupancy ≥ 0.80, n_keys ≥ max(3, sec//2), pin≈0, coverage≈0
  - `R` ≤ previous champion **or** dens_return strictly lower at equal seal quality
- Document trade-off table; may keep sec=6 champion if dens_return does not improve under seal constraints.

### Phase 3 success (single structure)

- Fetch + parse one cyclic PDB (default configurable, e.g. cyclosporin-related entry or user override).
- Produce ranking table: native vs ≥N_decoy decoys by mold score.
- **Win:** native ranks in top fraction (default: top 20% or better than median decoy by ≥ margin).
- **Honest fail:** native not enriched — report and keep pipeline; do not invent λ=γ salvage.

---

## 3. Architecture

### Layout

```
realm/validate/
  __init__.py
  seeds.py          # ζ, scramble, GOE, Poisson frequency factories
  harness.py        # forge + residual + mold score from knobs + seed
  report.py         # JSON/table writers
  pdb_io.py         # RCSB fetch + cyclic backbone extract
  hf_io.py          # Hugging Face Hub download/cache (data plane only)
  decoys.py         # torsion/coordinate decoys from native

null_battery.py     # CLI Phase 1
sec_scale.py        # CLI Phase 2
pdb_decoy.py        # CLI Phase 3
```

Top-level CLIs mirror existing `evolve.py` / `meet.py` style (argparse, JSON out, optional plot).

### Shared harness contract

```text
score(seed_spec, knobs, N, k, sectors) → {
  F, R, occupancy, n_keys, n_valleys,
  breakdown, diagnostics, thetas, spectral_gaps, verdict
}
```

- `seed_spec`: `{kind: "zeta"|"scramble"|"goe"|"poisson", rng_seed, n_zeros}`  
- For non-ζ kinds: replace `ZetaField.gammas` (or equivalent) with synthetic ordinates of length k **before** `SpectralAction.from_field`.  
- Implementation detail: inject via small adapter on `ZetaField` / `Deriver` so forge path is unchanged for ζ.

### Reuse (do not fork)

| Existing | Role |
|----------|------|
| `Keymaker` / `Deriver` | forge geometry + action + Crit |
| `residual` / lock–key | R and F components |
| `build_moduli_landscape` / `test_valley_occupancy` | mold scores |
| `realm.hw` / process pool | parallel null evals + decoy scoring |
| `evolve_result.json` knobs | default sealed champion |

### Data flow

```
evolve_result.json knobs
        │
        ├─► null_battery: for kind in {ζ,scramble,GOE,Poisson}:
        │       score(kind) → null_battery_result.json
        │       gate F_ζ < 0.8 min F_null
        │
        ├─► sec_scale: for sec in {6,8,10,12}:
        │       short evolve or grid polish → table dens_return, R, occ
        │       optional new champion if better under seal constraints
        │
        └─► pdb_decoy (only if gate pass OR --force):
                fetch PDB → native coords/torsions
                decoys → score each on mold from ζ landscape
                → pdb_decoy_result.json + ranking plot
```

---

## 4. Phase details

### Phase 1 — Null battery

**Null constructions** (all length k, positive increasing-ish ordinates comparable to γ scale):

| Kind | Construction |
|------|----------------|
| `zeta` | Existing `ZetaField.first(k)` |
| `scramble` | Random permutation of real γ gaps, rebuild cumulative heights from γ₁ |
| `goe` | Wigner-surmise spacings, unfold to unit mean, map to height scale matching γ span |
| `poisson` | Exponential spacings, same mean density calibration |

**Procedure:**

1. Load knobs from `evolve_result.json` (override flags allowed).  
2. For each kind × `n_reps` (default 5, fixed rng seeds 0..n_reps-1): call harness.  
3. Aggregate mean F, R, dens_return, occ per kind.  
4. Gate on **mean F** (or best-of-rep — design chooses **mean F** for stability).  
5. Write `null_battery_result.json` + optional bar plot.

**Parallelism:** evaluate independent (kind, rep) pairs with `recommend_workers()` process pool.

### Phase 2 — sec≈k

1. Fix knobs bulk + IR mults; vary `n_sectors ∈ {6,8,10,12}` (and optional light polish on IR mults only).  
2. Require enough Crit minima (if valleys < sec//2, mark FAIL_CAPACITY).  
3. Table: sec, R, dens_return, occ, n_valleys, n_keys.  
4. Optional: short DE on IR mults only per sec (workers-aware).  
5. Write `sec_scale_result.json`.

Does **not** rewrite residual weights to “win.”

### Phase 3 — Single cyclic PDB deep dive

1. **Fetch (priority order):**  
   a. Local cache `data/pdb/{PDB_ID}.pdb` if present.  
   b. **RCSB:** `https://files.rcsb.org/download/{PDB_ID}.pdb`.  
   c. **Hugging Face fallback (optional):** `hf_hub_download` for CPSea2 demo/metadata or a mirrored PDB file when `--source hf` or RCSB fails and `--allow-hf-fallback`.  
2. **Parse:** backbone N–CA–C (or CA-trace fallback) for a cyclic chain; detect cycle by SEQRES/link or user `--chain` + first–last bond assumption for known cyclic peptides.  
3. **Native score:** embed as sector geometry or map torsions → θ proxy → mold distance on ζ landscape built from champion knobs.  
   - Preferred: reduce native ring to holonomy-like twist + embed_multimode path consistent with `zeta_geometry`.  
   - Fallback: score CA RMSD-to-Crit-geometry only if holonomy map incomplete — must be labeled FALLBACK in report.  
4. **Decoys:** ≥32 default — random torsion noise / CA jitter preserving bond lengths approximately; reject non-closed if closure residual > tol.  
5. **Rank** by mold mean distance (lower better) and occupancy flag.  
6. Report native rank, percentile, enrichment vs random.

**Default PDB:** configurable CLI `--pdb`; recommend a well-known cyclic peptide with public PDB (document choice in plan). If fetch fails, exit nonzero with clear message (no silent synthetic swap unless `--allow-synthetic-fallback`).

### Hugging Face data plane (not critical path for residual)

Hub is **data + I/O only**. Engine remains ζ → Crit → mold → residual. No pLM fine-tune in the seal path; no λ=γ.

| Resource | Use | Constraint |
|----------|-----|------------|
| [`YZY010418/CPSea2`](https://huggingface.co/datasets/YZY010418/CPSea2) | Demo TSV + PDB-side metadata for cyclic peptide IDs / later mass ranking | Do **not** load full multi-GB dump on ARM; use `hf_hub_download` of **demo** or specific files. Prefer experimental PDB slice over AFDB-mined pseudo-cycles for first claim. |
| [`LiteFold/CycPepMPDB`](https://huggingface.co/datasets/LiteFold/CycPepMPDB) | Optional later property labels (permeability); not v1 gate | Sequence/property only |
| [`RosettaCommons/ProteinMPNN`](https://huggingface.co/datasets/RosettaCommons/ProteinMPNN) tensors | Optional later coords `xyz` for decoy basing | Heavy; post single-structure |
| `huggingface_hub` | Cache under `data/hf/` or default HF cache; version-pin repo revision when possible | Dependency optional: if not installed, Phase 3 RCSB-only still works |

**Out of critical path (optional baselines only):** Rostlab ProtT5 / ProstT5 / ProtBERT — may later score same decoys as a **comparison ranker** (“does mold beat pLM distance?”). Never replace Crit residual with embedding loss.

**v1 Phase 3b (after null gate + single deep dive):** thin CLI flag `--cpsea-demo` lists cyclic PDB ids from CPSea2 demo metadata for a multi-id ranking loop (still not full 2.7M).

---

## 5. Metrics glossary

| Symbol | Definition |
|--------|------------|
| R | Lock residual total (existing weights) |
| F | Evolve fitness R + occ/sector penalties (existing) |
| dens_return | `density_return_l1` diagnostic |
| occ | mold occupancy fraction |
| rank_native | 1-based rank among native+decoys (1=best) |
| enrichment | fraction of decoys worse than native |

Hard gate uses **F** only (Phase 1). Phase 3 uses rank/enrichment.

---

## 6. CLI sketch

```bash
# Phase 1
python null_battery.py --knobs evolve_result.json --reps 5 --workers -1

# Phase 2
python sec_scale.py --knobs evolve_result.json --sectors 6,8,10,12 --workers -1

# Phase 3 (after gate or --force)
python pdb_decoy.py --pdb 1CSA --knobs evolve_result.json --n-decoys 32 --workers -1
```

Exit codes: `0` pass/gate ok, `2` gate fail, `3` I/O/fetch/parse fail.

---

## 7. Error handling

- Forge failures → F=10 entry, count as null evaluation (not crash whole battery unless all fail).  
- PDB network errors → exit 3 + hint cache path.  
- Parse ambiguity (multi-model) → take model 1; log.  
- Too few Crit minima for high sec → FAIL_CAPACITY row, not exception.  
- Never substitute λ=γ residual if mold fails.

---

## 8. Testing (implementation plan will detail)

- Unit: seed factories produce length k, positive spacings; scramble preserves multiset of gaps.  
- Unit: harness ζ path matches Keymaker residual within float tol for champion knobs.  
- Integration: null_battery dry-run 1 rep serial.  
- Integration: pdb fetch mocked with fixture PDB snippet in `tests/fixtures/`.  
- Unit: `hf_io` resolves demo path with mocked hub (no network in CI).  
- Ontology guard: grep/tests ensure no `abs(lambda - gamma)` style scorer in validate path.

---

## 9. Hardware

- Default `workers=-1` via `realm.hw.recommend_workers` (ARM 8-core, ~5–8 GB free → ~4–6 workers).  
- BLAS single-thread inside workers.  
- DirectML/GPU not used for forge.

---

## 10. Deliverables

| Artifact | Phase |
|----------|--------|
| `realm/validate/*` including `hf_io.py` | all |
| `null_battery.py` + `null_battery_result.json` | 1 |
| `sec_scale.py` + `sec_scale_result.json` | 2 |
| `pdb_decoy.py` + `pdb_decoy_result.png/json` | 3 |
| Optional: `data/hf/` cache (gitignored) | 3 / 3b |
| This design doc | planning |
| Implementation plan under `docs/superpowers/plans/` | next skill |

---

## 11. Risks & honesty

| Risk | Mitigation |
|------|------------|
| Residual too soft → nulls also “seal” | Hard F margin 0.8×; report dens_return jointly |
| PDB cycle detection brittle | Single known target first; explicit chain flags |
| High sec cannot form enough valleys | FAIL_CAPACITY; keep sec=6 champion |
| Overclaim biology | Phase 3 language = ranking experiment, not fold proof |
| HF dump too large for 8 GB RAM | Demo/metadata only; never `load_dataset` full CPSea2 |
| pLM creep | ProtT5 only as optional baseline ranker, never residual |

---

## 12. Approval record

| Decision | Choice |
|----------|--------|
| Scope | Full validation ladder (phased) |
| Phase 1 gate | Hard ζ preference: F_ζ < 0.8 × min F_null |
| Phase 3 data | Live RCSB/PDB fetch + optional HF Hub fallback |
| Phase 3 scale v1 | Single structure deep dive |
| Architecture | Approach A — one CLI per phase + `realm/validate` harness |
| Hugging Face | Data plane (CPSea2 demo, hub download); not pLM critical path |

**Brainstorm approval:** user selected approach A and approved design sections §1–§4 (2026-07-30 session).  
**HF amendment:** approved (“hit it”) same session — data plane section added.
