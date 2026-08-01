# Job Coherence OS (oilfield)

Batch orchestrator for multi-source MWD/EDR job routines under a **locked QC pin**.

Commercial success = **sources glue + pin seal + optional EOW package** — not ROP / enrichment score-chase. Never λ=γ.

## Install / run

```bash
# from repo root
set PYTHONPATH=.
python job_coherence.py --os \
  --las path/to/well.las \
  --channel-pack surface_min \
  --out-dir out/job_os
```

### Common flags

| Flag | Role |
|------|------|
| `--os` | run_id / RUN.json / ledger / PARTNER_RECIPE / LATEST |
| `--micropulse DIR` | MicroPulse CSV fibers (GAMMA, SHOCK, …) |
| `--survey FILE` | Survey stations (or SURVEY fiber from MicroPulse) |
| `--require-survey` | gate SOLVED on survey QC |
| `--regime-mode persist_h0` | regime barcode stalk |
| `--with-regime` / `--with-science` | reports + dual-gate science (info only) |
| `--chunk-rows N` | out-of-core CHUNK_INSPECT |
| `--max-rows N` | cap LAS rows loaded into negotiate cycle |
| `--max-depth-mono-violations N` | EDR re-log tolerance (config, not free) |
| `--stability-k K` | fixed-point: empty board × K cycles |
| `--eow-package DIR` | post-SOLVED client package inventory |
| `--catalog` | scan `--out-dir` → INDEX.json / INDEX.md |

### Free params (negotiated)

`align_mode`, `window_scale`, `channel_pack`, `null_policy`, `survey_gate`, `regime_mode`

### Pin (never negotiated)

Depth mono (finite samples), pack required channels, unit sanity. Soft_T dual-gate protein pin is a **separate** system (`handoff_coherence`).

## Live JTOD1 example

```bash
python job_coherence.py --os \
  --las "C:\JTOD1\...\Archer ... Depth_....las" \
  --micropulse "C:\JTOD1\...\MicroPulse_799_..." \
  --survey "C:\JTOD1\...\MicroPulse_799_SURVEY_....csv" \
  --channel-pack mwd_full \
  --regime-mode persist_h0 --with-regime --with-science \
  --chunk-rows 250 --max-rows 400 --max-depth-mono-violations 5 \
  --stability-k 2 --eow-package "C:\JTOD1\...\MWD_EOW_EXAMPLES\..." \
  --out-dir out/job_os_jtod1
```

Catalog runs:

```bash
python job_coherence.py --catalog --out-dir out/job_os_jtod1
```

## Artifacts per run

```
out/job_os/<run_id>/
  RUN.json  ledger.jsonl  COHERENCE.json  PARTNER_RECIPE.json
  FIREWALL.json
  TREND_ROLLUP.json  CHUNK_INSPECT.json  CHUNK_SCIENCE_ANNEX.json
  cycle_NN/  eow/PACKAGE_INDEX.json  eow/SHIP.md
```

## Job QC Firewall (explore vs certify)

Dual-stalk with the sister program's Precision–Certification Firewall (Tier-E / Tier-C),
restricted to oilfield substrate. **Agreement is not verification.**

| Tier | Analog | Contents | Ship? |
|------|--------|----------|-------|
| **EXPLORE** | Tier-E | science annex, dynamical topology *measure*, regime structure, graph λ1 trends | Never alone |
| **CERTIFY** | Tier-C | pin hard seal + `is_solved` ∧ empty free-param board × K (+ optional `topology_stable`) | Only this seals SOLVED |

**Near-miss:** explore looks promising (e.g. native beats decoy, long topo bars) while
certify fails (pin hard fail / unsolved) → **REJECT** for partner ship.

- Written every run: `FIREWALL.json`; also embedded in `COHERENCE.json` and summarized on `RUN.json`.
- `pin_writable: false` always — explore metrics never retune mono ε / pack / soft_T.
- Never λ=γ (graph λ1 is algebraic connectivity only).

## Multi-well rotation (Mode C)

Same **pin thresholds** across a rotation group; merit = fraction `firewall_certified`, not science mean.

```bash
# manifest JSON — see design dual-stalk-ops-bridge §3
python job_coherence.py --rotation path/to/manifest.json --out-dir out/rotation
python job_coherence.py --rotation path/to/manifest.json --rotation-dry-run --out-dir out/rotation
```

| Exit | Branch |
|------|--------|
| 0 | `ROTATION_PASS` or dry-run |
| 3 | `ROTATION_PARTIAL` |
| 4 | `ROTATION_FAIL` / errors |

Artifacts: `out/rotation/<batch_id>/MANIFEST.json`, `ROTATION_REPORT.json|md`, `wells/<well_id>/…`.

**Live JTOD1 example manifest:** [docs/examples/job_rotation_jtod1.manifest.json](examples/job_rotation_jtod1.manifest.json)

```bash
python job_coherence.py --rotation docs/examples/job_rotation_jtod1.manifest.json --out-dir out/rotation_jtod1
```

Example result (host with `C:\JTOD1` corpus): multi-well `firewall_certified` under identical pin (Archer depth+MP/survey, LINK VJ RANCH time, Archer time; Chevron Drlg_Mech via C6 WOBX→WOB alias).

### Channel aliases (C6 inherited dictionary)

Vendor curve names map onto pack canonicals **only when series already exist** — never invent samples, never retune pin.

| Canonical | Accepted sources |
|-----------|------------------|
| WOB | WOB, WOBX, SWOB |
| TOR | TOR, TQA, TQX |
| SPP | SPP, SPPA |
| GAMMA | GAMMA, GAM, GRC, GR |
| RPM | RPM, RPM_P |

Module: `realm/job_os/aliases.py` (applied every cycle after LAS parse).

Design: [2026-07-31-dual-stalk-ops-bridge-design.md](superpowers/specs/2026-07-31-dual-stalk-ops-bridge-design.md)

## Navigator menu (non-CLI)

Keyboard-driven wizard for the same Job OS + dynamical topology effects without memorizing flags. Pin is **read-only** (never soft_T / mono ε rewrite). Topology measure reports are **not ACCEPTANCE**.

```bash
# from repo root
set PYTHONPATH=.
python realm_menu.py
```

| Choice | Item | Effect |
|--------|------|--------|
| 1 | Job OS — fixture quick smoke | In-process fixture LAS smoke (`tests/fixtures/mini_edr.las`) + optional dynamical topology wire |
| 2 | Job OS — custom paths (wizard) | Prompt for LAS / MicroPulse / survey / out-dir; confirm CLI; run loop |
| 3 | Catalog runs (INDEX) | Scan `--out-dir` → INDEX.json / INDEX.md |
| 4 | Dynamical topology report | Stage-axis zigzag report on a run dir → `DYNAMICAL_TOPOLOGY.json` (measure only) |
| 5 | Handoff coherence (protein) | Suggested handoff CLI / optional in-process dual-gate path |
| 6 | Open docs / LATEST paths | Print `docs/JOB_OS.md`, design spec, LATEST, fixtures |
| 0 | Exit | Quit |

Non-interactive exit: `echo 0 | python realm_menu.py`

### Time zigzag vs space sheaf (dual spine)

```text
 stage_0 → stage_1 → … → stage_T     ← TIME dual: DynamicalTopology zigzag / stage-axis barcode
      │         │              │
   complex   complex        complex
      └──── measure report + topology_stable(K) control ────┘
                     │
              SPACE dual: sheaf MaxOp L / AQFT local fingerprint (unchanged)
                     │
              pin read-only every cycle — never λ=γ
```

- **Measure:** `run_dynamical_topology` → TREND / science annex / `DYNAMICAL_TOPOLOGY.json` (`not_acceptance: true`)
- **Control:** `--topo-stability` / menu toggle → `topology_stable(K)` joins fixed-point only with `is_solved ∧ empty free-param board`
- Design: [2026-07-31-dynamical-topology-dual-spine-design.md](superpowers/specs/2026-07-31-dynamical-topology-dual-spine-design.md)

## Design / KB

- [docs/superpowers/specs/2026-07-31-oilfield-job-coherence-os-design.md](superpowers/specs/2026-07-31-oilfield-job-coherence-os-design.md)
- [docs/superpowers/specs/2026-07-31-dynamical-topology-dual-spine-design.md](superpowers/specs/2026-07-31-dynamical-topology-dual-spine-design.md)
- [docs/superpowers/specs/2026-07-31-academic-kb-knowledge-integration-design.md](superpowers/specs/2026-07-31-academic-kb-knowledge-integration-design.md)
- [docs/superpowers/specs/2026-07-31-parent-kb-h1-audit.md](superpowers/specs/2026-07-31-parent-kb-h1-audit.md)
