# Design: ToeStub — MCP Cognitive Governor (Job OS v0)

**Date:** 2026-07-31  
**Status:** Approved for implementation planning  
**Product name:** ToeStub  
**Role:** Local stdio MCP middleware that injects Job Coherence OS constraints into agent harnesses (Grok / Claude / Cursor)  
**Kernel:** Existing `realm/job_os` + `job_coherence` CLI — pin law unchanged  
**Related:**  
- `2026-07-31-dual-stalk-ops-bridge-design.md`  
- `2026-07-31-oilfield-job-coherence-os-design.md`  
- `docs/JOB_OS.md`  

---

## 0. Problem and goals

### Problem
The Job OS governor (loop, firewall, rotation, audit) is already operational via CLI and menu, but agent harnesses cannot *call* it as structured tools. Without an MCP boundary, agents either shell ad hoc (fragile) or invent answers without pin seal.

### Goals
1. Ship **ToeStub** as a **local stdio MCP server** agents can attach mid-session.  
2. Expose **Job OS only** tool pack in v0 (run, catalog, rotation, audit, firewall read).  
3. Preserve dual-stalk / firewall law: explore ≠ accept; pin never writable via tools.  
4. Keep CLI as twin operator path — no second negotiate implementation.  
5. Yield structured JSON (surface + certified + paths); diagnostics optional.

### Non-goals (v0)
- Transparent proxy of all LLM API traffic  
- Universal “topological hash” of free-text prompts as Tier-E vs Tier-C  
- Pin-write tools; soft_T / mono ε free-param retune  
- Protein dual-gate handoff tools (later pack)  
- IDE extension  
- Cloud / remote MCP hosting  
- Arbitrary shell execution tool  
- ζ-as-acceptance UX for commercial associates  

### Primary consumer
**You + agent harnesses** (Grok / Claude / Cursor). Oilfield associate UX is second wave on the same law.

---

## 1. Identity and architecture

### Identity
| Field | Value |
|-------|--------|
| Product | ToeStub |
| Metaphor | Cognitive governor middleware — LLM proposes; pin + firewall certify |
| Transport v0 | Local **stdio MCP** |
| Approach | **Thin MCP shell over in-process `realm.job_os` API** (Approach 1) |

### Stack

```text
Host agent (Grok / Claude / Cursor)
        │  MCP stdio
        ▼
   ToeStub MCP server (toestub-mcp)
        │  in-process Python
        ▼
   realm/job_os
     loop · firewall · rotation · audit · aliases · catalog
        │
        ▼
   FIREWALL.json · COHERENCE.json · PARTNER_RECIPE · ROTATION_REPORT
```

### Law (on-shell)
- Free params: closed sets only (`align_mode`, `window_scale`, `channel_pack`, `null_policy`, `survey_gate`, `regime_mode`).  
- Pin config may be passed only as explicit **pin_config** (e.g. `max_depth_mono_violations`) — never as free.  
- `pin_writable` always false; server rejects any attempt to set it true.  
- Explore payloads always `not_acceptance: true`.  
- Certified ⇔ firewall certify tier (pin + fixed-point), not science/topo agreement.  
- Near-miss: explore promising ∧ certify fail → not ship.

### Interceptor (honest v0)
Not a free-text topological strain hasher. **Routing = which tool the agent calls.**  
Optional later: advisory `toestub_route_hint` (keywords → tool suggestion only; never certifies).

---

## 2. Tool surface

### Tools (exactly five in v0)

| Tool name | Kernel | Certifies? |
|-----------|--------|------------|
| `toestub_job_run` | `run_job_coherence_loop` | Yes if `firewall_certified` |
| `toestub_job_catalog` | `write_job_os_catalog` | No — index only |
| `toestub_job_rotation` | `run_job_rotation` | Branch `ROTATION_*` |
| `toestub_job_audit` | `audit_job_run` / `audit_rotation_batch` | Audit ok only |
| `toestub_firewall_read` | Read/rebuild FIREWALL | Read-only |

### Not tools
- Pin rewrite, soft_T, invent survey/depth reorder  
- `run_shell` / arbitrary code  
- Handoff protein / known_solutions (v0.1+ pack)  
- Dynamical topology as ACCEPTANCE  

### Common response envelope

```json
{
  "ok": true,
  "surface": "Human-readable one-liner for the agent to quote",
  "certified": true,
  "near_miss": false,
  "branch": null,
  "paths": {
    "out_root": "...",
    "run_id": "...",
    "coherence": "...",
    "firewall": "...",
    "partner_recipe": "..."
  },
  "explore": null,
  "error": null
}
```

- Default: omit heavy explore; set `include_explore: true` or `verbose: true` for diagnostic layer.  
- `toestub_job_rotation` sets `branch` (`ROTATION_PASS` | `PARTIAL` | `FAIL` | `DRY_RUN`).  
- `toestub_job_catalog` sets `certified: null`, `not_acceptance: true`.

### `toestub_job_run` inputs

| Field | Required | Notes |
|-------|----------|--------|
| `las_path` | yes | Absolute or relative to repo root |
| `micropulse_path` | no | |
| `survey_path` | no | |
| `out_root` | no | Default under repo `out/job_os` |
| `max_rounds` | no | Default 6 |
| `stability_k` | no | Default 1 |
| `free_params` | no | Closed keys only; unknown keys → error |
| `pin_config` | no | e.g. `max_depth_mono_violations`, `depth_mono_eps` — not free |
| `with_regime` / `with_science` / `with_dynamical_topology` | no | |
| `max_rows` | no | Live EDR cap |
| `eow_package` | no | Post-SOLVED ship path |
| `include_explore` | no | Diagnostic payload |

### `toestub_job_rotation` inputs
- `manifest_path` **or** inline `manifest` object (same schema as `job_rotation_manifest`)  
- `out_root`, `dry_run`, `max_rows`, `include_explore`

### `toestub_job_audit` inputs
- `path` — run_dir or rotation batch_dir (auto-detect `ROTATION_REPORT.json`)  
- `write_report` optional → write `AUDIT.json` beside target  

### `toestub_firewall_read` inputs
- `run_dir` — load `FIREWALL.json` or rebuild from `COHERENCE.json`

### Error model

| Case | `ok` | `certified` | Notes |
|------|------|-------------|--------|
| Missing LAS | false | null | Clear error |
| Ran, pin fail | true | false | near_miss if explore promising |
| Timeout | false | null | partial paths; suggest audit/resume |
| Rotation PARTIAL/FAIL | true | false | `branch` set honestly |
| Audit findings fail | false | per report | findings list |

**Timeouts (v0):** sync tool calls; default wall timeout 300s for `job_run` / `job_rotation` (configurable env `TOESTUB_TIMEOUT_S`). No fake certified on timeout.

---

## 3. Packaging and host config

### Layout

```text
toestub/
  __init__.py          # version
  mcp_server.py        # stdio MCP main
  tools_job.py         # handlers
  schemas.py           # validation / free-param allowlist
  envelope.py          # common response builder
pyproject.toml         # optional extra [toestub]; script toestub-mcp
docs/examples/toestub.mcp.json   # host config snippet
```

### Entrypoint
- Console script: `toestub-mcp` → `toestub.mcp_server:main`  
- Env:  
  - `TOESTUB_REPO_ROOT` — path resolution base  
  - `TOESTUB_TIMEOUT_S` — long-run timeout  
  - `TOESTUB_ALLOW_ROOTS` — optional comma-separated path prefixes (if set, reject paths outside)

### Host config example

```json
{
  "mcpServers": {
    "toestub": {
      "command": "toestub-mcp",
      "args": [],
      "env": {
        "PYTHONPATH": "C:/PRIMEdEV-1/123abc-grok",
        "TOESTUB_REPO_ROOT": "C:/PRIMEdEV-1/123abc-grok"
      }
    }
  }
}
```

### Security
1. No pin-write tools.  
2. Optional path allowlist via `TOESTUB_ALLOW_ROOTS`.  
3. No shell tool.  
4. Explore never certifies (server-enforced).  
5. Audit read-only unless `write_report`.  
6. No cloud secrets in v0.

---

## 4. UX layers

| Layer | Content |
|-------|---------|
| **Surface** | `surface` string + `certified` / `branch` — what agents quote by default |
| **Diagnostic** | `explore`, near_miss, full paths, alias maps — when `include_explore` / `verbose` |

Complexity stays invisible unless the agent (or user) requests diagnostics. Partner truth remains on-disk artifacts + audit tool.

---

## 5. Testing and CI

### Unit
- Schema rejects unknown free keys and pin-as-free  
- Envelope always sets explore `not_acceptance` when present  
- Handlers call kernel correctly (mock or fixture)

### Integration
- Fixture LAS `job_run` → certified + FIREWALL on disk  
- `job_audit` that run → ok  
- Fixture rotation manifest → `ROTATION_PASS`  
- `firewall_read` returns pin_writable false  

### CI
- Extend `job-coherence.yml` with ToeStub handler/integration smoke once package lands  
- Never require `C:\JTOD1` in CI  

---

## 6. Success criteria (v0 complete)

- [x] `toestub-mcp` starts and advertises five tools  
- [x] Agent (or test client) runs fixture job → `certified=true`  
- [x] Audit of that run → ok  
- [x] Fixture rotation via tool → `ROTATION_PASS`  
- [x] Free-param pin rewrite rejected  
- [x] Docs: host config snippet + non-goals  
- [x] This design committed  

**Shipped:** implementation commits `d5e96b3`..`887b6e5` on main (2026-07-31 SDD).

---

## 7. Implementation order

1. Package skeleton + MCP list-tools hello  
2. `toestub_firewall_read` + `toestub_job_audit`  
3. `toestub_job_catalog`  
4. `toestub_job_run` (fixture-proven)  
5. `toestub_job_rotation`  
6. Host config docs + CI smoke  

### Later packs (not v0)
- Handoff / known_solutions tools  
- HTTP/SSE transport  
- Path allowlist default-on for associates  
- Advisory route hint  
- Async run jobs with poll tool  

---

## 8. Approach decision record

| Approach | Verdict |
|----------|---------|
| Thin MCP over in-process job_os | **Chosen** |
| MCP subprocess-only to CLI | Deferred (isolation later if needed) |
| Rewrite governor for chat | **Rejected** — pin drift risk |

---

## 9. Open decisions closed in brainstorm

| Decision | Choice |
|----------|--------|
| Product name | ToeStub |
| First consumer | Agent harnesses |
| Tool pack v0 | Job OS only |
| Transport | Local stdio MCP |
| Architecture | Thin shell, Approach 1 |
