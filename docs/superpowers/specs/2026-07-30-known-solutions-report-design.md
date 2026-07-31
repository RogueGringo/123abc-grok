# Design: Known-Solutions Report (Public Natives → Science Ledger + Partner Annex)

**Date:** 2026-07-30  
**Status:** Landed (commercial + science closed loop) — 2026-07-30/31  
**Branch context:** commercial dual-gate handoff closed; science external test next  
**Related:** `2026-07-30-handoff-protocol-design.md`, `2026-07-30-validation-ladder-design.md`, dual-gate pin lock  

---

## 0. Problem and non-goals

### Problem
Commercial transfer (export → package → verify → accept → matrix → delivery → ship → partner receipt) is closed. Science claims still need a **single, reproducible report** that tests dual-gate ranking against **public experimental structures** (known solutions), without turning enrichment into a ship gate or retuning pins.

### Goals
1. Expand beyond the curated 12 where possible (RCSB expand list ∪ CPSea2 demo), with explicit source tags.
2. Run dual-gate **native-vs-decoy** ranking (`rank_one`) on all resolvable IDs.
3. Run **structure-mode Kabsch** fidelity on a **capped subset** (default curated 12).
4. Emit **split artifacts**: full internal ledger + thin partner science annex.
5. Stamp locked dual-gate pin on every run; report-only exit policy for weak enrichment.

### Non-goals
- Changing `LengthPolicy` / `PRODUCTION_RANK` / soft_T pin.
- λ=γ scoring or residual null-battery revival as primary claim.
- Making enrichment a release/ACCEPTANCE/SHIP success metric.
- Full mold PDB export for every expanded ID.
- Treating AFDB-mined pseudo-cycles as experimental ground truth without tagging.
- Partner receipt zip redesign (already closed).

### Ontology (locked)
- ζ = substrate seed for Crit molds only.
- Operational geometry = Crit / dual-gate projection path.
- Pass metrics for **this report** = enrichment / native_rank / Kabsch fit (informational).
- Pass metrics for **commercial product** remain openable PDBs + dual-gate pin.
- **Never λ=γ.**

---

## 1. End-consumers (split artifacts)

| Consumer | Artifact | Purpose |
|----------|----------|---------|
| Internal | `KNOWN_SOLUTIONS.json` + `.md` | Full rows, tags, skips, multi-seed stats, Kabsch subset |
| Partner | `PARTNER_SCIENCE_ANNEX.json` + `.md` | Pin + aggregate summary + provenance; **not** ACCEPTANCE |
| CI (optional later) | same JSON | Diff/regression of aggregates; v1 has no hard enrichment floor |

**Human answers locked (topological brainstorm L0):**
- End-consumer: **both** (split).
- Fail mode: **report-only** (no science hard gate on enrichment).
- Corpus: **RCSB expand + CPSea2 demo** union with curated 12.
- Product: **rank_one full set + Kabsch on subset**.

---

## 2. Architecture

```text
┌─────────────────────┐
│  ID universe resolve │  curated probe/holdout ∪ rcsb_expand ∪ cpsea2_demo
└──────────┬──────────┘
           │ id_universe.json
           ▼
┌─────────────────────┐     ┌──────────────────────┐
│  pin preflight      │     │  knobs load          │
│  verify_dual_gate   │     │  evolve_result.json  │
└──────────┬──────────┘     └──────────┬───────────┘
           │                           │
           ▼                           ▼
┌──────────────────────────────────────────────────┐
│  P_rank: rank_one / enrichment_stamp path        │
│  (all resolvable IDs, PRODUCTION_RANK levers)    │
└──────────────────────┬───────────────────────────┘
                       │
           ┌───────────┴───────────┐
           ▼                       ▼
┌─────────────────────┐  ┌─────────────────────────┐
│  P_kabsch (subset)  │  │  report writers         │
│  structure ensemble │  │  internal + partner     │
│  Kabsch vs native   │  │  annex                  │
└─────────────────────┘  └─────────────────────────┘
```

Modules (proposed; implement only after human gate):

| Module | Role |
|--------|------|
| `realm/validate/known_solutions_ids.py` (or `data/known_solutions/`) | Expand lists + tag merge |
| `realm/validate/known_solutions.py` | Orchestrate resolve → rank → kabsch → aggregates |
| `realm/handoff` reuse | `verify_dual_gate_pin`, optional structure generate for Kabsch |
| `known_solutions.py` CLI | Thin argparse entrypoint |
| `pdb_batch.rank_one` | Unchanged production ranking |

Does **not** own: ship, accept, delivery, partner receipt zip.

---

## 3. ID universe

### 3.1 Sources

| Tag | Source | Required for v1 run |
|-----|--------|---------------------|
| `curated_probe` | `PROBE_IDS` | Yes |
| `curated_holdout` | `HOLDOUT_IDS` | Yes |
| `rcsb_expand` | Versioned list of additional experimental PDB IDs (cyclic/short, band 6–40) | Yes (list may start modest; empty expand = still valid if documented) |
| `cpsea2_demo` | CPSea2 demo/metadata via existing `hf_io` | Optional (`--allow-hf`) |

### 3.2 Merge rules
1. Uppercase IDs; unique set.
2. Tag priority if collision: probe > holdout > rcsb_expand > cpsea2_demo (keep highest-priority tag; record `also_in` optional).
3. `--ids` CLI adds tags `cli_override` and still runs rank_one.
4. `--skip-expand` → curated only (debug / smoke).

### 3.3 Fetch order
1. `data/pdb/{ID}.pdb` if present  
2. RCSB via existing `fetch_pdb`  
3. Else row status `ERROR_FETCH` / skip — **no synthetic native**

### 3.4 CPSea2 constraint
- Demo/metadata only; do not `load_dataset` full multi-GB dump.
- Prefer experimental PDB IDs; if metadata marks AFDB/pseudo, tag `pseudo` and **exclude from primary aggregates** (optional secondary table).

---

## 4. Ranking products

### 4.1 P_rank (all resolvable)
- Call path equivalent to `enrichment_stamp` / `rank_one` with `PRODUCTION_RANK` (no local soft_T override for chasing).
- Defaults: `n_decoys=24`, `n_seeds=3` for curated tags; expand IDs default `n_seeds=1` unless `--full-seeds`.
- Slim row fields: pdb, status, n_ca, enrichment, enrichment_std, top20, native_rank, native_dist, method, soft_T, soft_T_effective, defect_beta*, sectors*, set tags.

### 4.2 P_kabsch (subset)
- Default set: curated probe ∪ holdout (`--kabsch-set curated`).
- Hard cap: `--kabsch-max` default **12**.
- Mechanism: existing structure-mode path (`generate_structure_ensemble` / Kabsch softmin vs native) — **read scores**; optional write of PDBs off by default (`--write-kabsch-pdbs` opt-in).
- Fields: best_rank_score, n_molds, n_ca, status.

### 4.3 Aggregates (internal)
Per tag and `all_ok`:
- n, mean_enrichment, mean_enrichment_std, top20_rate, mean_native_rank  
Kabsch: n_kabsch_ok, mean_best_rank_score  

**Never** collapse expand into holdout mean without separate fields (prevents dilution of holdout signal).

---

## 5. Artifacts

### Layout
```text
out/known_solutions/{UTC_stamp}/
  pin.json
  id_universe.json
  KNOWN_SOLUTIONS.json
  KNOWN_SOLUTIONS.md
  PARTNER_SCIENCE_ANNEX.json
  PARTNER_SCIENCE_ANNEX.md
```

Optional: `LATEST` pointer file or copy under `out/known_solutions/LATEST/` (match release pointer style if cheap).

### Partner annex content (thin)
- Dual-gate pin (soft_T n=12, seq_mix, face_weight) + ok boolean  
- Counts: attempted / ranked_ok / fetch_fail  
- Mean enrichment: probe / holdout / rcsb_expand / cpsea2_demo (each with n)  
- Kabsch subset: n + mean best score if any  
- Explicit disclaimers:
  - Not ACCEPTANCE / not SHIP success  
  - Enrichment informational; commercial metric remains openable PDBs + pin  
  - Never λ=γ  
- Link language: partner mold packages and `handoff_ship --verify-bundle` are separate  

### Ontology stamps
Every JSON root includes:
```json
"ontology": "known_solutions_report_not_lambda_eq_gamma"
```

---

## 6. CLI

```bash
python known_solutions.py \
  --knobs evolve_result.json \
  --out-dir out/known_solutions \
  --n-decoys 24 \
  --n-seeds 3 \
  --allow-hf \
  --kabsch-set curated \
  --kabsch-max 12
```

| Flag | Role |
|------|------|
| `--dry-run` | Universe + pin only |
| `--skip-expand` | Curated 12 only |
| `--ids` | Extra IDs |
| `--rcsb-list` | Override expand list path |
| `--full-seeds` | Apply n_seeds to expand IDs too |
| `--write-kabsch-pdbs` | Opt-in structure export for subset |
| `-v` | Logging |

### Exit codes
| Code | Meaning |
|------|---------|
| 0 | Pin ok and (dry-run ok \| ≥1 rank row completed) |
| 2 | Pin failed or fatal config |
| 3 | Zero IDs resolved / total I/O collapse |
| — | Weak enrichment **does not** change exit code |

---

## 7. Tests

- Unit: universe merge / tag priority / dedup  
- Unit: aggregates separate probe vs holdout vs expand  
- Unit: pin failure → exit 2 path (mocked policy or monkeypatch)  
- Integration: `--skip-expand --dry-run` offline  
- Integration: `--skip-expand` rank on 1–2 fixture/cache IDs if cheap  
- Guard: no λ=γ scorer in known_solutions modules  
- Partner annex: must not contain accept/ship success fields that override commercial semantics  

---

## 8. Relationship to commercial stack

| Commercial | Known-solutions |
|------------|-----------------|
| `handoff_campaign` / matrix / ship | Unchanged |
| ACCEPTANCE / DELIVERY / SHIP | Unchanged |
| Partner receipt zip | Unchanged |
| Optional attach | `handoff_matrix` / `handoff_ship` / `handoff_science` attach annex + optional DECOY_MODE_COMPARE; never gates accept |
| Ops surface | `handoff_status --known-solutions` (science only; commercial ok independent) |
| Golden path | `python handoff_science.py --compare-modes soft,mixed,hard --attach-releases out/releases --status` |

Enrichment_stamp on campaigns remains informational; this report is the **canonical multi-source science ledger**.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Expand IDs fail cyclic band parse | SKIP rows; list starts with known-good; grow list empirically |
| HF missing in CI | `--allow-hf` off by default in CI; curated+RCSB list still run |
| Runtime explosion | Kabsch capped; expand seeds default 1 |
| Partner confuses annex with accept | Explicit disclaimers; separate filenames |
| Score-chase pressure | Report-only exits; pin frozen tests |

---

## 10. Implementation order (post human gate only)

1. ID universe module + RCSB expand list seed + tests  
2. Orchestrator: pin + rank_one loop + aggregates  
3. Kabsch subset path (scores only)  
4. Writers: internal + partner annex  
5. CLI `known_solutions.py`  
6. Smoke on curated; then expand offline/online as available  
7. Docs pointer from handoff README / PARTNER language if needed  

**Do not implement until human approves this design (W(I) ∈ W_phys).**

---

## 11. Success criteria (design acceptance)

- [ ] Human accepts split-artifact + report-only + expand sources + Kabsch subset  
- [ ] Pin and commercial success metrics remain non-negotiable  
- [ ] Clear CLI and exit codes  
- [ ] No λ=γ; no pin retune  
- [ ] Implementation plan can be written without further product ambiguity  

---

## Appendix A — L0 answer log (topological brainstorm)

1. End-consumer: **both** (internal ledger + partner annex)  
2. Science fail mode: **report-only**  
3. Corpus: **RCSB expand + CPSea2 demo** (with curated 12)  
4. Ranking product: **rank_one full + Kabsch subset**  

## Appendix B — L1 filtration

- Longest bar: standalone science ledger CLI  
- Rejected as primary: matrix-owned annex, campaign-only stamp scale-out  
