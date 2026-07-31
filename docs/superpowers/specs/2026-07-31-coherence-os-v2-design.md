# Design: Autonomous Coherence OS v2 (Batch Orchestrator)

**Date:** 2026-07-31  
**Status:** Implemented (OS v2 batch: run_id, ledger, stability-K, PARTNER_RECIPE, resume)  
**Builds on:** `handoff_coherence` multi-section merge (`409c22e`, `db5cb4c`)  
**Related:** dual-gate pin lock; known-solutions science path; commercial ship  

---

## 0. Problem and non-goals

### Problem
The dual-gate **commercial routine** (export → decorate → physics → verify) and a **cyclic negotiate loop** exist, but v1 is a thin CLI: single-winner merge, weak fixed-point notion (one-shot `is_solved`), no resume, no OS-level run identity. “Next level” is a **batch autonomous coherence OS** that runs until commercial routine fixed-point under multi-section negotiation — still **pin-locked**.

### Human L0 answers (topological brainstorm)
1. Altitude: **Autonomous coherence OS**  
2. Free domain: **Routine only** (decorate / physics / top_k; science info channel)  
3. Solved: **Commercial routine fixed-point**  
4. Runtime: **Batch orchestrator CLI** (no daemon v1)

### Goals
1. First-class **run** with persistent ledger + resume.  
2. Multi-section **proposal boards** every cycle (export, verify, physics, decorate, science-info).  
3. **Fixed-point stop:** `is_solved` **and** empty proposal board for **K** consecutive cycles (K≥1).  
4. Pin invariant checked every cycle; any pin-violating move rejected.  
5. Optional genotype remains **sibling plug-in**, not OS free-domain core.  
6. Commercial ship metrics unchanged (openable PDBs + pin).

### Non-goals (v2)
- Retune `soft_T` / `seq_mix` / `face_weight` production pin.  
- Enrichment as ACCEPTANCE / SHIP success.  
- Long-running daemon / watch directory.  
- Full Rosetta packing / MD as required adapters.  
- λ=γ scoring.  
- Making genotype NS mandatory for “solved.”

### Ontology (locked)
- ζ = substrate seed for Crit molds only.  
- Operational geometry = Crit / dual-gate projection.  
- **Never λ=γ.**  
- Commercial success = openable PDBs + dual-gate pin seal.

---

## 1. Architecture

```text
┌──────────────────────────────────────────────────────────┐
│  Coherence OS (batch)                                    │
│  RUN.json · ledger.jsonl · cycle_NN/ · COHERENCE.*       │
└────────────────────────────┬─────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌───────────┐      ┌────────────┐      ┌─────────────┐
   │ EXECUTE   │      │ OBSERVE    │      │ PROPOSE     │
   │ export    │ ───► │ pin,export,│ ───► │ per section │
   │ decorate  │      │ verify,    │      │ free params │
   │ physics   │      │ physics,   │      └──────┬──────┘
   │ verify    │      │ decorate,  │             │
   └───────────┘      │ science*   │             ▼
                      └────────────┘      ┌─────────────┐
                                          │ MERGE       │
                                          │ priority +  │
                                          │ tried-set   │
                                          └──────┬──────┘
                             ┌───────────────────┘
                             ▼
                    FIXED_POINT? ──yes──► SOLVED
                         │ no
                         ▼
                    budget / stuck ──► STOP
```

\*science-info optional; never accept gate; may only propose free-param nudges (e.g. top_k).

---

## 2. Free parameter domain (sheaf stalks)

| Param | Domain | Sections allowed |
|-------|--------|------------------|
| `decorate` | `null` \| `sequence` \| `polyala` | decorate, verify |
| `physics` | `geometry` \| `none` | physics |
| `top_k` | integers in [1, 8] | export, physics, science-info |
| *(v2.1 optional)* `science_decoy_mode` | soft \| mixed \| hard | science-info only |

**Global invariant (non-stalk):** dual-gate pin  
`soft_T(n=12)=0.036`, `seq_mix=0`, `face_weight=0.08` — **read-only every cycle**.

Genotype knobs (Λ, ω, …) are **not** in OS free domain for v2 core; use `--with-genotype` plug-in after SOLVED or when unsolved+science_weak (existing draft).

---

## 3. Fixed-point definition (solved)

Let `thr = CoherenceThresholds` (existing).

**Solved (commercial routine fixed-point):**
1. `is_solved(obs, thr, params)` is true, **and**
2. `collect_section_proposals(obs, params, thr, tried) == []` for **K consecutive cycles**.

Defaults: `K=1` in v2.0 (compatible with current single-cycle solve); CLI `--stability-k 2` for stricter stability.

**Not solved by:** enrichment mean, hard decoy win rate, partner PDF presence.

---

## 4. Multi-section propose + merge

### 4.1 Section contract
```text
Section.propose(obs, params, thr, tried) → list[SectionProposal]
SectionProposal = { section, params: FreeParams, reason, priority }
```

Priorities (lower wins): export=1, verify=2, physics=3, decorate=4, science=5.

### 4.2 Merge (v2.0)
- Sort by (priority, section, reason).  
- Winner = first proposal with FreeParams not in `tried`.  
- Record full **proposal board** every cycle (already partial).

### 4.3 Merge (v2.1 optional — field-wise sheaf)
- Per free field, take proposal from highest-priority section that sets that field.  
- Reject composite if in `tried` or pin-violating.  
- Only if H₁ review shows single-winner merge insufficient.

### 4.4 Pin veto
Any proposal that would change LengthPolicy production numbers → drop + log `veto_pin`.

---

## 5. Persistence and CLI

### Layout
```text
out/coherence_os/<run_id>/
  RUN.json              # free domain, thresholds, pin snapshot, K, budget
  ledger.jsonl          # append-only cycle records
  COHERENCE.json        # final rollup
  COHERENCE.md
  LATEST                # pointer to run or last cycle
  cycle_01/ ... cycle_N/
  GENOTYPE.json         # only if plug-in ran
```

### CLI surface (evolve existing `handoff_coherence.py`)
```bash
# New OS mode
python handoff_coherence.py --os \
  --pdb-ids probe \
  --require-decorate \
  --stability-k 1 \
  --max-rounds 12 \
  --out-dir out/coherence_os

# Resume incomplete run
python handoff_coherence.py --resume out/coherence_os/<run_id>

# Optional science info channel
python handoff_coherence.py --os --with-science ...

# Genotype sibling (not free-domain core)
python handoff_coherence.py --os --with-genotype --science-weak 0.55 ...
```

Exit codes: `0` solved, `1` stuck/budget (routine incomplete), `2` config, `4` pin fail.

---

## 6. Cycle record schema (ledger line)

```json
{
  "round": 1,
  "params": {"decorate": "null", "physics": "geometry", "top_k": 2},
  "observations": {},
  "coherence_score": 0.0,
  "is_solved_slice": false,
  "proposals": [{"section": "decorate", "reason": "...", "params": {}}],
  "merged": {"params": {}, "reason": "merge[decorate]:..."},
  "pin": {"ok": true, "soft_T": 0.036},
  "stability_streak": 0,
  "cycle_dir": "..."
}
```

---

## 7. Partner handoff interface

When SOLVED:
- Optional: write `PARTNER_RECIPE.json` = `{pin, free_params, run_id, ontology}` for partner re-run.  
- Optional: attach final cycle tree into matrix/releases via existing attach helpers.  
- **Never** set ACCEPTANCE from OS score alone.

---

## 8. Testing

| Test | Assert |
|------|--------|
| Unit merge priority | export beats decorate when both fire |
| Unit fixed-point K=2 | solved requires empty board twice |
| Unit pin veto | no proposal mutates soft_T |
| Integration 1CSA | null + require_decorate → sequence → SOLVED |
| Integration resume | restart from ledger.jsonl continues round N+1 |
| Guard | grep: no LengthPolicy write in coherence path |

---

## 9. Implementation order (post human gate)

1. Run identity + `ledger.jsonl` + `RUN.json` + resume.  
2. Stability-K fixed-point stop.  
3. Harden proposal board + pin veto logging.  
4. PARTNER_RECIPE.json on SOLVED.  
5. CI: existing coherence smoke + resume unit.  
6. Docs: design status → Implemented.

**Genotype plug-in:** leave as optional flag; do not expand free domain.

---

## 10. Horizon (not v2 scope)

| ID | Possibility |
|----|-------------|
| H1 | Field-wise multi-section merge (true sheaf glue) |
| H2 | science_decoy_mode free param for stress-stable fixed-point |
| H3 | Chemistry section (pack energy) as new free stalk |
| H4 | Multi-partner recipe catalog under releases/INDEX |
| H5 | Formal sheaf consistency check (ON_SHELL) as stop mode |

---

## 11. Success criteria for design acceptance

- [ ] Human accepts Bar A (OS v2 batch) + A2 routine free domain + A3 fixed-point + A4 CLI  
- [ ] Pin non-negotiable  
- [ ] Clear stop: is_solved ∧ empty proposals × K  
- [ ] Resume + ledger specified  
- [ ] Genotype is plug-in only  
- [ ] No implementation until W(I) ∈ W_phys (human gate)

---

## Appendix A — L0 log

1. Next level altitude: **Autonomous coherence OS**  
2. Free domain: **Routine only**  
3. Stop: **Commercial routine fixed-point**  
4. Runtime: **Batch orchestrator CLI**  

## Appendix B — L1 filtration

- Longest bar: Coherence OS v2 batch  
- Short bars under this altitude: pure chemistry OS, pure science claim engine, multi-tenant platform  
