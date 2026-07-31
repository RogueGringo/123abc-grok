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
  TREND_ROLLUP.json  CHUNK_INSPECT.json  CHUNK_SCIENCE_ANNEX.json
  cycle_NN/  eow/PACKAGE_INDEX.json  eow/SHIP.md
```

## Design / KB

- [docs/superpowers/specs/2026-07-31-oilfield-job-coherence-os-design.md](superpowers/specs/2026-07-31-oilfield-job-coherence-os-design.md)
- [docs/superpowers/specs/2026-07-31-academic-kb-knowledge-integration-design.md](superpowers/specs/2026-07-31-academic-kb-knowledge-integration-design.md)
- [docs/superpowers/specs/2026-07-31-parent-kb-h1-audit.md](superpowers/specs/2026-07-31-parent-kb-h1-audit.md)
