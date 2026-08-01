# ToeStub — MCP Cognitive Governor (Job OS)

Local **stdio MCP** middleware that exposes Job Coherence OS as five structured tools for agent harnesses (Grok / Claude / Cursor). LLM proposes; pin + firewall certify.

**Kernel:** existing `realm/job_os` + `job_coherence` CLI — pin law unchanged.  
**CLI twin:** `python job_coherence.py` remains the operator path; ToeStub does not re-implement negotiate.

## What it is / is not

| Is | Is not |
|----|--------|
| Thin MCP shell over in-process Job OS APIs | Transparent proxy of all LLM traffic |
| Five tools: run, catalog, rotation, audit, firewall_read | Arbitrary shell / code execution tool |
| Common JSON envelope (`ok`, `surface`, `certified`, `paths`) | Pin-write API or soft_T retune |
| Local stdio server for host attach | Cloud / remote MCP hosting |
| Explore payloads always `not_acceptance: true` | ζ / science / topology as ACCEPTANCE |

## Install / run

From repo root (Windows PowerShell or bash):

```bash
pip install mcp
# optional editable install for console script:
# pip install -e .

set PYTHONPATH=.
# or: export PYTHONPATH=.

python -m toestub.mcp_server
# after pip install -e .:
# toestub-mcp
```

Requires Python 3.11+. Job OS fixture tests need `numpy` (same as `job-coherence` CI).

### Environment

| Env | Role | Default |
|-----|------|---------|
| `TOESTUB_REPO_ROOT` | Path resolution base for relative LAS/manifest paths | cwd |
| `TOESTUB_TIMEOUT_S` | **Reserved** wall-timeout for long `job_run` / `job_rotation` (default 300). Read via `toestub.schemas.get_timeout_s()`. **No SIGALRM enforcement on Windows** — host/process cancel only in v0; value is reserved for portable timeout wiring, not Unix-only signal handlers. | `300` |
| `TOESTUB_ALLOW_ROOTS` | Optional comma-separated path prefixes; if set, reject paths outside | unset (no check) |
| `PYTHONPATH` | Must include monorepo root so `realm` and `toestub` import | — |

## Host MCP config (Windows paths)

Example for Cursor / Claude Desktop–style `mcpServers` maps. Copy from [docs/examples/toestub.mcp.json](examples/toestub.mcp.json); adjust roots to your clone:

```json
{
  "mcpServers": {
    "toestub": {
      "command": "python",
      "args": ["-m", "toestub.mcp_server"],
      "env": {
        "PYTHONPATH": "C:/PRIMEdEV-1/123abc-grok",
        "TOESTUB_REPO_ROOT": "C:/PRIMEdEV-1/123abc-grok"
      }
    }
  }
}
```

Alternate entry after `pip install -e .`: `"command": "toestub-mcp"`, `"args": []`.

## Tools (exactly five in v0)

| Tool | Kernel | Certifies? |
|------|--------|------------|
| `toestub_job_run` | `run_job_coherence_loop` | Yes if `firewall_certified` |
| `toestub_job_catalog` | `write_job_os_catalog` | No — index only (`certified: null`, not_acceptance) |
| `toestub_job_rotation` | `run_job_rotation` | Branch `ROTATION_PASS` / `PARTIAL` / `FAIL` / `DRY_RUN` |
| `toestub_job_audit` | `audit_job_run` / `audit_rotation_batch` | Audit ok only |
| `toestub_firewall_read` | Load/rebuild `FIREWALL.json` | Read-only |

### Envelope (surface)

Tools return a JSON string envelope (`ontology: toestub_envelope_v1`):

- `ok`, `surface`, `certified`, `near_miss`, `branch`, `paths`, optional `explore` (`not_acceptance: true`), `error`
- Default: omit heavy explore; set `include_explore: true` for diagnostics
- Never fake `certified` on timeout or error

### Free params vs pin

**Free (closed set only):** `align_mode`, `window_scale`, `channel_pack`, `null_policy`, `survey_gate`, `regime_mode`  
**Pin config (explicit only):** e.g. `max_depth_mono_violations`, `depth_mono_eps` — never as free  
**Always:** `pin_writable` false; server rejects pin-as-free / soft_T in free_params

## Pin law + non-goals (v0)

- Explore ≠ accept; certified ⇔ firewall certify tier (pin + fixed-point), not science/topo agreement.
- Near-miss: explore promising ∧ certify fail → not ship.
- No pin-write tools; no soft_T / mono ε free-param retune.
- No protein dual-gate handoff tools (later pack).
- No IDE extension; no cloud MCP; no free-text “topological hash” of prompts as Tier-E vs Tier-C.
- Never λ=γ.

## Package layout

```text
toestub/
  __init__.py       # version
  mcp_server.py     # FastMCP stdio main + tool registration
  tools_job.py      # handlers
  schemas.py        # free/pin allowlists, path resolve, env helpers
  envelope.py       # build_envelope
docs/examples/toestub.mcp.json
tests/test_toestub_*.py
```

Console script: `toestub-mcp` → `toestub.mcp_server:main` (`pyproject.toml`).

## Related

- Job OS operator guide: [JOB_OS.md](JOB_OS.md)
- Design: [2026-07-31-toestub-mcp-governor-design.md](superpowers/specs/2026-07-31-toestub-mcp-governor-design.md)
- Dual-stalk / firewall: [2026-07-31-dual-stalk-ops-bridge-design.md](superpowers/specs/2026-07-31-dual-stalk-ops-bridge-design.md)
- Plan: [2026-07-31-toestub-mcp-governor.md](superpowers/plans/2026-07-31-toestub-mcp-governor.md)
