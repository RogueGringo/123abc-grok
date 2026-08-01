# Design: Dual-Stalk Ops Bridge (IG-PRIMON ↔ Job Coherence OS)

**Date:** 2026-07-31  
**Status:** Mode B shipped (`0278f48`); Mode C rotation in same wave  
**Approach:** Shared Gate Kernel; dual execution; common ledger shape — no monorepo merge  
**Sister:** `Oilfield-Ops-Training/ig-primon-t1-main` (arithmetic geometry / PCF / sheaf-for-meaning)  
**This repo:** dual-gate protein + Job Coherence OS (MWD/EDR) @ main  
**Related:**  
- `2026-07-31-oilfield-job-coherence-os-design.md`  
- `2026-07-31-dynamical-topology-dual-spine-design.md`  
- `2026-07-31-parent-kb-h1-audit.md`  
- `docs/JOB_OS.md`  
- Sister: `GATE_KERNEL.md`, `ig_primon/firewall.py`, `sheaf_llm/SYNTHESIS.md`  

---

## 0. Problem and non-goals

### Problem
Two mature programs share a falsification discipline but speak different substrates. Without an explicit restriction map, partners confuse research receipts with field SOLVED, and operators cannot cite a single **explore vs certify** law across wells.

### Goals
1. Name the shared **Gate Kernel** and map each slot to both trees.  
2. Ship Job-side **QC Firewall** (explore/certify/near-miss) as the operational dual of PRIMON PCF.  
3. Define **rotation group** doctrine for multi-well merit (Mode C).  
4. Keep pin sealed; never λ=γ; never bulk-import sister code into realm.

### Non-goals
- Merge repos or install `ig_primon` as a Job OS dependency.  
- Import mpmath Gardner anchors into LAS paths.  
- Treat science/topo/λ1 as ACCEPTANCE.  
- Retune soft_T / depth mono ε for score.  
- Absolute λ1 floors from parent KB.

---

## 1. Architecture (restriction maps)

```text
                 GATE KERNEL (0-dim)
        CLAIM · ANCHOR · CHAOS · ROTATE · LEDGER · RESIDUE
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
   ig-primon-t1                       123abc-grok
   Tier-E / Tier-C PCF                Job QC Firewall
   [V]/[E] receipts                  SOLVED / PARTNER_RECIPE
          │                                 │
          └──── shared law: agreement ≠ verification ────┘
```

| Kernel slot | Sister instance | Job OS instance |
|-------------|-----------------|-----------------|
| CLAIM | curvature / grounded sheaf / depth-N | sources glue + pin seal + EOW |
| ANCHOR | Gardner, Ising, R=−1 | depth mono, pack channels, known survey |
| CHAOS | GOE/GUE, UNK scramble | decoy science, null_policy |
| ROTATE | seeds, instruments, baselines | multi-well / multi-seed catalog |
| LEDGER | pre-reg + results_* | RUN / ledger / FIREWALL / INDEX |
| RESIDUE | meaning off chaos fixed point | science/topo residue — never ship alone |

### Persistent clusters (L1 long bars)

| ID | Law | Ship artifact |
|----|-----|---------------|
| P-FIREWALL | agreement ≠ verification | `FIREWALL.json` |
| P-PIN | never retune mid-run | pin hard_ok every cycle |
| P-ANCHOR-FIRST | known truth in same run | fixture + live QC |
| P-LEDGER | amend, no silent edit | ledger.jsonl |
| P-HELD-OUT | A derive / B measure | rotation wells |
| P-SHEAF-MEANING | glue multi-fiber, not compress | MultiPulse join + glue_score |

---

## 2. Mode B — Job QC Firewall (shipped)

**Module:** `realm/job_os/firewall.py`  
**Wire:** `run_job_coherence_loop` → `FIREWALL.json` + embed in `COHERENCE.json` / `RUN.json`  
**Commit:** `0278f48`

| Tier | Contents | `pin_writable` | Ship? |
|------|----------|----------------|-------|
| EXPLORE | science, dynamical topology measure, λ1/structure trends | false | Never alone |
| CERTIFY | pin hard + is_solved ∧ empty board × K (+ optional topo_stable) | false | Only seal |

**Near-miss:** explore promising ∧ certify fail → `near_miss_rejected`.  
**Invariants:** `assert_firewall_invariants` — explore always `not_acceptance`; near-miss never certified.

---

## 3. Mode C — Multi-well rotation (this wave)

### Claim (fail-able)
A Job OS configuration that **certifies** under the firewall on well A must be re-run under the **same pin thresholds** on well B…N (rotation group). Merit is **fraction certified under rotation**, not mean science score.

### Manifest schema

```json
{
  "kind": "job_rotation_manifest",
  "prereg_id": "rotation_v1",
  "ontology": "job_rotation_not_acceptance_for_residue",
  "stability_k": 1,
  "thresholds": {},
  "free_params": {"channel_pack": "surface_min", "align_mode": "depth_primary"},
  "wells": [
    {"well_id": "W1", "las": "path/to/a.las"},
    {"well_id": "W2", "las": "path/to/b.las", "micropulse": "...", "survey": "..."}
  ]
}
```

### Pre-registered verdicts

| Branch | Condition | Meaning |
|--------|-----------|---------|
| ROTATION_PASS | all wells `firewall_certified` | config survives rotation |
| ROTATION_PARTIAL | ≥1 certified, ≥1 not | residual / substrate dependence (bank) |
| ROTATION_FAIL | zero certified | config not operational under pin |
| NEAR_MISS_FLAG | any well near_miss | explore agreed, certify rejected — doctrine tooth |

### Non-goals for rotation
- Pin ε not in free_params; not adapted per well.  
- Aggregate science score never overrides ROTATION_* branch.  
- Single-well SOLVED is not multi-well merit.

### Artifacts

```
out/rotation/<batch_id>/
  MANIFEST.json          # frozen copy of input
  ROTATION_REPORT.json   # aggregate + per-well
  ROTATION_REPORT.md
  wells/<well_id>/<run_id>/   # normal Job OS tree + FIREWALL.json
```

---

## 4. Capability registry (ops merit ladder)

| ID | Capability | Status |
|----|------------|--------|
| C1 | Job QC Firewall language | **Shipped** Mode B |
| C2 | Partner receipt ladder | PARTNER_RECIPE + EOW (prior) |
| C3 | Regime residue ops | regime + science info (prior) |
| C4 | Topo-stable SOLVED | dual spine (prior) |
| C5 | Cross-well rotation doctrine | **Mode C this wave** |
| C6 | Inherited channel dictionary | channel_pack ontology (prior; deepen later) |

---

## 5. Global consistency (ON_SHELL)

| Check | Pass |
|-------|------|
| Pin sealed | rotation does not write mono ε / pack required set |
| Measure vs accept | FIREWALL explore `not_acceptance` |
| Substrate honesty | no claim PRIMON [V] math = well SOLVED |
| Ledger complete | each well has RUN + FIREWALL |
| Rotation affordable | ≥2 wells (or 2 fixture aliases for smoke) |
| Instrument audit | ROTATION_* from certify count, not science mean |

---

## 6. Implementation tasks

1. Design this doc (Mode A).  
2. Firewall already on main (Mode B).  
3. `realm/job_os/rotation.py` — load manifest, run wells, write report.  
4. CLI `--rotation MANIFEST.json` on `job_coherence.py`.  
5. Catalog: surface `firewall_certified` / near_miss.  
6. Tests: fixture dual-well smoke; near_miss doctrine unit already in firewall tests.  
7. Docs: JOB_OS.md rotation section.

---

## 7. Success criteria

- [x] FIREWALL on every OS run (`0278f48`)  
- [x] Rotation report with pre-registered branches (`realm/job_os/rotation.py`)  
- [x] Pin identical across wells in a batch (`pin_identical_across_wells`)  
- [x] CLI `--rotation` / `--rotation-dry-run`  
- [x] Catalog surfaces `firewall_certified` / near_miss  
- [x] Live multi-well JTOD1-class batch (`docs/examples/job_rotation_jtod1.manifest.json` → `ROTATION_PASS`, 3/3 firewall_certified, pin_identical)  
- [x] Tests green; no λ=γ; no pin retune  
