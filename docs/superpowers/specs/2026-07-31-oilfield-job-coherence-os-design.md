# Design: Oilfield Job Coherence OS (MWD Multi-Source)

**Date:** 2026-07-31  
**Status:** Implemented (P1–P5 merged to main; stack d0159f88 → 41ae148)  
**Primary altitude (L0):** **A — Job coherence** (multi-source glue under QC pin)  
**Also in scope (stalks, not separate products):** B survey holonomy · C drilling regime · D EOW handoff  
**Transfers from:** Coherence OS v2 (`2026-07-31-coherence-os-v2-design.md`, `a800cc8`)  
**Domain corpus:** `C:\JTOD1\OILFIELD_DRILLING_DATA_EXAMPLE_FILES` (+ existing `nue/` Forge DNA)  
**Related:** `nue/docs/TOPOLOGICAL_EDR_MANIFOLD.md`, `FORGE_PIPELINE.md`, dual-gate pin discipline  

---

## 0. Problem and non-goals

### Problem
MWD jobs produce **heterogeneous multi-source streams** (surface EDR LAS/SQL, MicroPulse memory, surveys, recorded `.dat`, EOW packages) that must *glue* before any deliverable or science claim is honest. Partial work exists in `nue/` (Forge SCAN→SHIP, coherence evidence demos) and a hardened **fixed-point OS** exists in protein-land (`handoff_coherence` OS v2). Missing: one **job-level coherence OS** with locked QC pins, free-param negotiation only, stability-K stop, ledger/resume, and attach points for survey / regime / EOW without forking four products.

### Human L0 answers
1. Primary work object: **A — Job coherence**  
2. Honest intent: **all of A+B+C+D**, with A as substrate  
3. Engine transfer: dual-gate / sheaf / OS machinery — **not** ζ→ROP claim  

### Goals
1. **Job run identity:** `run_id`, `RUN.json`, `ledger.jsonl`, resume, LATEST (OS v2 shape).  
2. **Multi-source observe:** EDR + MicroPulse (+ optional recorded / EOW assertions) → one observation vector.  
3. **Multi-section propose→merge** over free params only; pin veto every cycle.  
4. **Fixed-point:** `is_solved` ∧ empty free-param board × **K** consecutive cycles.  
5. **Sections as stalks** (same OS):  
   - **export** — ingest / parse completeness  
   - **align** — depth/time glue (decorate analogue)  
   - **survey** (B) — station QC + frame/holonomy defects  
   - **regime** (C) — stick-slip / slide-rotate / shock persistence (science + optional free nudge)  
   - **physics** — monotonic depth, unit sanity, channel bounds  
   - **verify** — pin + package inventory  
   - **eow** (D) — package/recipe/ship only after SOLVED (not free-param core)  
6. **PARTNER_RECIPE** = free params + pin stamp for re-run (tour handoff, not acceptance).  
7. **Science channel** optional: native-vs-decoy window ranking; **never** ACCEPTANCE alone.

### Non-goals (v1)
- ROP / bit-wear / production ML as SHIP success.  
- Retuning company SOP / QC pin to chase a score.  
- Claiming ζ or Crit molds “predict” formation or ROP.  
- Real-time daemon on the rig floor as v1 requirement (batch + folder-watch optional later).  
- Replacing WellSeeker / Pason / tool OEM software.  
- Making regime or enrichment mean the commercial accept gate.

### Ontology (locked for this domain)
| Role | Oilfield meaning |
|------|------------------|
| **Substrate** | Raw multi-channel time/depth series (SQL/LAS/CSV/dat) — not a spectral claim target |
| **Operational geometry** | Job manifold: depth/time 1-skeleton + channel fibers (EDR + MicroPulse + survey) |
| **Pin** | QC / SOP invariants (see §2) — **read-only every cycle** |
| **Free params** | Align/window/pack/filter knobs only (§2) |
| **Solved** | Commercial *job routine* fixed-point: sources glue + pin holds + no free moves ×K |
| **Science** | Informational persistence / dual-gate windows — not SHIP |

---

## 1. Architecture (A is the core; B/C/D are stalks)

```text
┌─────────────────────────────────────────────────────────────────┐
│  Oilfield Job Coherence OS (batch)                              │
│  RUN.json · ledger.jsonl · cycle_NN/ · COHERENCE.* · RECIPE     │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌───────────┐      ┌────────────┐      ┌─────────────┐
   │ EXECUTE   │      │ OBSERVE    │      │ PROPOSE     │
   │ ingest    │ ───► │ pin,export,│ ───► │ per section │
   │ align     │      │ align,     │      │ free params │
   │ survey*   │      │ survey,    │      └──────┬──────┘
   │ regime*   │      │ regime,    │             │
   │ verify    │      │ physics,   │             ▼
   └───────────┘      │ science*   │      ┌─────────────┐
                      └────────────┘      │ MERGE       │
                                          │ priority +  │
                                          │ tried-set   │
                                          └──────┬──────┘
                             ┌───────────────────┘
                             ▼
                    FIXED_POINT? ──yes──► SOLVED
                         │ no                 │
                         ▼                    ▼
                    budget / stuck      optional EOW SHIP (D)
```

\*survey / regime / science are **enabled by flags** but share one ledger and one pin.

### Why one OS not four products
- **A** = observation + free-param loop + stop.  
- **B** = survey section (proposals + obs fields).  
- **C** = regime section + science-info (persistence barcode, dual-gate windows).  
- **D** = post-SOLVED attach: package inventory, PARTNER_RECIPE, client drop — **Forge SHIP**.  

Restriction maps (interfaces) force global consistency: EOW cannot SHIP if job OS not SOLVED; regime cannot retune pin; survey defects block `is_solved` when survey required.

---

## 2. Free parameter domain and pin (sheaf stalks)

### 2.1 Pin (global invariant — non-negotiable)

Default pin candidates (concrete numbers company-tunable **once** as config, then locked for a run):

| Invariant | Intent |
|-----------|--------|
| Depth monotonic on depth-indexed sources (tolerance ε_d) | No time-warped zombie depths |
| Survey QC band (e.g. total G / MagF within tool band when present) | Bad stations flagged, not “fixed” by score |
| Required channel sets present for job profile (surface min-set / MWD min-set) | Incomplete export ≠ solved |
| No unit inversion without explicit convert (ft/m, klbs, psi) | Align free-param only via registered converters |
| Integrity: source path + content hash on ship | Provenance |

**Never free:** inventing surveys, silent depth reordering, changing SOP thresholds mid-run to pass gates.

### 2.2 Free params (v1)

| Param | Domain | Sections that may propose |
|-------|--------|---------------------------|
| `align_mode` | `none` \| `depth_primary` \| `time_primary` \| `survey_anchor` | align, export, survey |
| `window_scale` | enum / int steps (e.g. 1,2,4,8 stands or minutes) | regime, physics, science |
| `channel_pack` | `surface_min` \| `surface_full` \| `mwd_full` \| `job_union` | export, verify |
| `null_policy` | `drop` \| `hold_last` \| `mark_only` | align, decorate-analogue |
| `survey_gate` | `off` \| `qc_only` \| `holonomy` | survey (B) |
| `regime_mode` | `off` \| `persist_h0` \| `dual_gate_windows` | regime (C), science |
| *(optional v1.1)* `shock_pack` | `off` \| `on` | regime, physics |

**Merge priority (lower wins):** export=1, verify=2, align=3, survey=4, physics=5, regime=6, science=7.

### 2.3 Fixed-point (solved)

Solved when **all** hold for **K** consecutive cycles:

1. Pin OK.  
2. Export completeness for selected `channel_pack`.  
3. Align: cross-source depth/time glue score ≥ thr (or no multi-source required).  
4. If `survey_gate != off`: survey QC pass (and holonomy trivial / defect list empty if `holonomy`).  
5. Physics: no hard fails (monotonic / unit / bound).  
6. Free-param proposal board empty (no untried legal move).  

**Not solved by:** mean coherence scalar alone, stick-slip “looking better,” ROP proxy, enrichment-style score.

Default `K=1`; CLI `--stability-k 2` for stricter hold.

---

## 3. Data adapters (JTOD1)

| Source | Path pattern | Role |
|--------|--------------|------|
| EDR LAS time/depth | `EDR_DATA/LAS_*` | Surface fibers (WOB, TOR, RPM, SSSI, SPP, …) |
| EDR SQL dumps | `EDR_DATA/SQL_*` | Parallel Txxxx channels |
| MicroPulse | `MicroPulse_*/*.csv` | Downhole: GAMMA, SURVEY, SHOCK, VIBE, PULSE, TELEM… |
| Recorded runs | `MWD_ReCORDED_MODE_Runs/Run*` | Multi-run known-solutions corpus |
| EOW packages | `MWD_EOW_EXAMPLES/*` | Assertions + client deliverables (D) |
| Existing harness | `nue/src/o365_edr_sql_harness` | SCAN/SHAPE parsers + Forge evidence |

**v1 job profile:** pick one well/run folder set (e.g. SQL or LAS + matching MicroPulse if present) → single `job_id`.

Reuse `nue` parsers where possible; OS core should not re-implement Pason SQL streaming if harness already does.

---

## 4. Sections (B/C/D as first-class stalks)

### 4.1 A — Core job loop (required)
observe(export, align, pin, physics) → propose free params → merge → execute → ledger.

### 4.2 B — Survey stalk
- **Obs:** n_stations, qc_fail_count, max |G−1|, MagF band, optional discrete holonomy defect along MD.  
- **Propose:** `align_mode=survey_anchor`, `survey_gate=qc_only→holonomy`, `null_policy` on bad stations (mark, don’t invent).  
- **Solved contribution:** if survey required, defects empty + QC pin.

### 4.3 C — Regime stalk
- **Obs:** H₀-style persistence summary on SSSI / torque-norm / RPM windows; shock exceedance counts.  
- **Propose (free only):** `window_scale`, `regime_mode`, `shock_pack` — never SOP pin.  
- **Science-info:** dual-gate windows: “native” (known good run slice) vs decoy (time-scramble / channel-shuffle) under **locked** pin — report only.  
- **Solved contribution:** optional; v1 default **does not** require regime for SOLVED unless `--require-regime`.

### 4.4 D — EOW handoff (post-SOLVED)
- Only after SOLVED (or explicit `--force-ship` → status UNSOLVED_SHIP with banner).  
- Artifacts: package inventory (surveys, LAS, paperwork checklist), `PARTNER_RECIPE.json`, integrity hashes, `SHIP.md` / optional O365 studio link (existing nue pattern).  
- **Never** sets SOLVED from package completeness alone without pin + glue.

---

## 5. Persistence and CLI

### Layout
```text
out/job_os/<run_id>/
  RUN.json
  ledger.jsonl
  COHERENCE.json
  COHERENCE.md
  PARTNER_RECIPE.json      # on SOLVED
  cycle_01/ ... cycle_N/
    observations.json
    sources/                 # normalized extracts
    survey_report.json       # if B
    regime_report.json       # if C
  eow/                       # if D after SOLVED
    PACKAGE_INDEX.json
    SHIP.md
  LATEST → parent pointer
```

### CLI sketch (new entry or extend nue harness)
```bash
# Primary: job coherence
python job_coherence.py --os \
  --job-root "C:\JTOD1\...\EDR_DATA" \
  --micropulse "C:\JTOD1\...\MicroPulse_799_..." \
  --require-survey \
  --stability-k 1 \
  --out-dir out/job_os

# With regime science (info)
python job_coherence.py --os --with-regime --with-science ...

# After SOLVED: EOW attach
python job_coherence.py --resume out/job_os/<run_id> --eow-package "C:\JTOD1\...\MWD_EOW_EXAMPLES\..."
```

Exit: `0` SOLVED, `1` stuck/budget, `2` config, `4` pin fail (mirror OS v2).

---

## 6. Cycle record (ledger line)

```json
{
  "round": 1,
  "params": {
    "align_mode": "depth_primary",
    "window_scale": 2,
    "channel_pack": "job_union",
    "null_policy": "mark_only",
    "survey_gate": "qc_only",
    "regime_mode": "off"
  },
  "observations": {},
  "is_solved_slice": false,
  "proposals": [],
  "merged": null,
  "pin": {"ok": true},
  "stability_streak": 0,
  "cycle_dir": "..."
}
```

---

## 7. Phased implementation (single product, staged stalks)

| Phase | Deliverable | Success |
|-------|-------------|---------|
| **P0** | Design gate (this doc) | Human W(I) ∈ W_phys |
| **P1** | Job OS core: ingest LAS **or** SQL + pin + align free params + ledger + K-stop | Demo job reaches SOLVED or honest stuck |
| **P2** | MicroPulse fiber join + channel_pack | Surface+downhole glue obs |
| **P3** | Survey stalk (B) | QC + optional holonomy report; `--require-survey` |
| **P4** | Regime stalk (C) + science dual-gate windows | Barcode + info annex; not accept gate |
| **P5** | EOW SHIP (D) + PARTNER_RECIPE | Package index after SOLVED |
| **P6** | Optional O365/Power BI ship via existing nue | Evidence hash + principal |

**Do not** implement B/C/D as separate CLIs with separate pins.

---

## 8. Testing

| Test | Assert |
|------|--------|
| Pin veto | No proposal mutates depth-mono ε or SOP band |
| Align propose | Incomplete glue → align_mode / null_policy move |
| Fixed-point K=2 | Needs two empty-board solved slices |
| Survey required | Missing/bad stations → not solved; propose mark/anchor |
| Regime science | Dual-gate report exists; SOLVED independent of score |
| EOW gate | SHIP refuses without SOLVED (unless forced + banner) |
| Resume | ledger + RUN restore free params + streak |
| Fixture | Small LAS snippet + survey CSV from JTOD1 example set |

---

## 9. H₁ loops (cross-section consistency)

| Loop | Restriction map |
|------|-----------------|
| A ↔ B | Survey stations must share depth skeleton with EDR after align |
| A ↔ C | Regime windows use same aligned series; cannot invent depth |
| A ↔ D | EOW package paths hashed; recipe free params match SOLVED run |
| B ↔ C | Shock/vibe near survey stations may flag regime but not rewrite Inc/Azi |
| Pin ↔ all | Any free move that would hide pin fail is dropped + `veto_pin` |
| Science ↔ D | Science annex may attach to ship; never alone sets ACCEPTANCE |

**Gini check:** positive if phases deepen hierarchy (core → stalks → ship). Negative if parallel apps diverge.

---

## 10. Horizon (not v1)

| ID | Possibility |
|----|-------------|
| H1 | Live folder-watch / Power Automate trigger (nue `.ps1`) as daemon |
| H2 | Field-wise sheaf merge across free fields (true multi-section glue) |
| H3 | Formal ON_SHELL sheaf stop using real block Laplacian from welly/nue |
| H4 | Multi-job recipe catalog (fleet / basin INDEX) |
| H5 | Recorded-mode `.dat` binary adapters as first-class export |

---

## 11. Success criteria for design acceptance

- [ ] Human accepts **A as primary** with **B/C/D as stalks** (not four products)  
- [ ] Pin non-negotiable; free domain listed  
- [ ] Stop = is_solved ∧ empty board × K  
- [ ] Phase order P1→P5 clear  
- [ ] No ROP/ζ score-chase as SHIP  
- [ ] JTOD1 paths + nue reuse acknowledged  
- [ ] No implementation until W(I) ∈ W_phys (human gate)

---

## Appendix A — L0 log

1. Engine transfer question: other work driven by dual-gate / OS engine + MWD data.  
2. Data root: `C:\JTOD1\OILFIELD_DRILLING_DATA_EXAMPLE_FILES` (EDR, MicroPulse, recorded, EOW, nue).  
3. Primary: **A job coherence**; honest: **all A+B+C+D**.  

## Appendix B — L1 filtration

| Bar | Approach | Persistence |
|-----|----------|-------------|
| **Longest** | **Unified Job Coherence OS** with B/C/D as sections + post-SOLVED EOW | Survives scale change (single well → multi-run → EOW) |
| Medium | Standalone survey holonomy tool | Useful but orphans glue |
| Medium | Regime-only stick-slip classifier | Score-chase risk without pin |
| Short | Four independent apps | H₁ contradiction / pin fork |
| Kill | ζ/Crit claims on ROP | Ontology violation |

**Recommend:** longest bar — this design.

## Appendix C — Mapping to protein OS v2

| Protein OS v2 | Oilfield Job OS |
|---------------|-----------------|
| decorate | align_mode / null_policy |
| physics | physics + survey QC / mono depth |
| top_k | window_scale / channel_pack |
| PARTNER_RECIPE | same role |
| known-solutions science | dual-gate windows on good vs LIH/scramble |
| openable PDBs + pin | gluing sources + QC pin + package integrity |
| never λ=γ | never retune SOP pin for score |

---

## PR Plan

Derived from §7 phases for `/execute-plan`. Single product; linear stack P1→P5.
Reuse patterns from `realm/handoff/coherence.py` (OS v2) and optional `nue` parsers.
Do **not** retune protein LengthPolicy pins. Do **not** invent ROP/ζ score-chase.

### PR 1: Job OS core ingest pin ledger

- **Description:** Implement oilfield Job Coherence OS P1: LAS (and/or minimal SQL) ingest adapter, QC pin check (depth mono, required surface channels, unit sanity), free params (`align_mode`, `window_scale`, `channel_pack`, `null_policy`), multi-section propose/merge for export+align+physics+verify, fixed-point stop (`is_solved` ∧ empty board × K), `RUN.json` + `ledger.jsonl` + resume + `PARTNER_RECIPE` on SOLVED, CLI `job_coherence.py --os`. Mirror architecture of `realm/handoff/coherence.py` OS v2 without protein adapters. Unit tests with small LAS fixture (can synthesize minimal LAS under tests/fixtures if full JTOD1 path unavailable in CI). Pin never mutated by proposals.
- **Files/components affected:** realm/job_os/__init__.py, realm/job_os/types.py, realm/job_os/pin.py, realm/job_os/ingest_las.py, realm/job_os/observe.py, realm/job_os/propose.py, realm/job_os/loop.py, job_coherence.py, tests/test_job_coherence_core.py, tests/fixtures/mini_edr.las
- **Dependencies:** None

### PR 2: MicroPulse fiber join channel pack

- **Description:** P2 — join MicroPulse CSVs (GAMMA, SHOCK, VIBE, PULSE, TELEM, TEMP, FLOW as available) as downhole fibers onto job manifold; expand `channel_pack` (`surface_min` | `surface_full` | `mwd_full` | `job_union`); glue observations for surface+downhole depth/time alignment; propose align free params when glue incomplete. Tests with tiny MicroPulse-like CSV fixtures.
- **Files/components affected:** realm/job_os/ingest_micropulse.py, realm/job_os/glue.py, realm/job_os/observe.py, realm/job_os/propose.py, realm/job_os/loop.py, job_coherence.py, tests/test_job_coherence_micropulse.py, tests/fixtures/mini_micropulse_*.csv
- **Dependencies:** PR 1

### PR 3: Survey stalk QC holonomy

- **Description:** P3 — survey stalk (B): parse MicroPulse SURVEY or simple survey table; QC (total G / MagF band when present); optional discrete holonomy/defect report along MD; free param `survey_gate` (`off` | `qc_only` | `holonomy`); `--require-survey` gates `is_solved`. Do not invent Inc/Azi. Tests for missing stations → not solved + propose mark/anchor.
- **Files/components affected:** realm/job_os/survey.py, realm/job_os/observe.py, realm/job_os/propose.py, realm/job_os/loop.py, job_coherence.py, tests/test_job_coherence_survey.py, tests/fixtures/mini_survey.csv
- **Dependencies:** PR 2

### PR 4: Regime stalk dual-gate science

- **Description:** P4 — regime stalk (C): windowed persistence summary on SSSI / torque-norm / RPM (or available surface channels); shock exceedance counts; free params `regime_mode`, `window_scale`, optional `shock_pack`; science dual-gate windows (native vs time-scramble decoy) **informational only** — SOLVED independent of science score. `--with-regime` / `--with-science` flags. Tests: dual-gate report exists; solved without requiring regime unless `--require-regime`.
- **Files/components affected:** realm/job_os/regime.py, realm/job_os/science.py, realm/job_os/observe.py, realm/job_os/propose.py, realm/job_os/loop.py, job_coherence.py, tests/test_job_coherence_regime.py
- **Dependencies:** PR 3

### PR 5: EOW package ship recipe

- **Description:** P5 — post-SOLVED EOW handoff (D): package inventory from EOW-like directory (surveys, LAS, paperwork checklist), `PARTNER_RECIPE.json` already on SOLVED; write `eow/PACKAGE_INDEX.json` + `SHIP.md`; refuse SHIP unless SOLVED unless `--force-ship` with UNSOLVED_SHIP banner. CLI `--eow-package` with `--resume`. Tests for SHIP gate.
- **Files/components affected:** realm/job_os/eow_ship.py, realm/job_os/loop.py, job_coherence.py, tests/test_job_coherence_eow.py
- **Dependencies:** PR 4
