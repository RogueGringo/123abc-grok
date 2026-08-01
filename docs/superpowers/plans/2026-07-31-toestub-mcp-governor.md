# ToeStub MCP Cognitive Governor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship ToeStub as a local stdio MCP server that exposes five Job OS governor tools to agent harnesses, wrapping in-process `realm.job_os` without a second pin/negotiate implementation.

**Architecture:** Thin MCP shell (`toestub/`) over existing Job OS APIs. Tools validate free params against closed sets, reject pin-as-free, return a common envelope (`ok`, `surface`, `certified`, `paths`, optional `explore` with `not_acceptance`). CLI `job_coherence.py` remains the operator twin.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP), existing `realm/job_os`, pytest, optional minimal `pyproject.toml` for `toestub-mcp` entrypoint.

## Global Constraints

- Never expose tools that write dual-gate soft_T or Job QC pin as free params.
- Free params closed set only: `align_mode`, `window_scale`, `channel_pack`, `null_policy`, `survey_gate`, `regime_mode`.
- Pin fields only via explicit `pin_config` (`depth_mono_eps`, `max_depth_mono_violations`, survey/regime thresholds as already on `JobThresholds`).
- Explore payloads always `not_acceptance: true`; `pin_writable` always false.
- No shell tool, no handoff/protein tools in v0, no transparent LLM proxy.
- Never λ=γ.
- Windows-friendly paths; CI uses fixture LAS only (no JTOD1 required).
- In-process kernel calls — do not reimplement negotiate/loop.

**Spec:** `docs/superpowers/specs/2026-07-31-toestub-mcp-governor-design.md`

## File map

| Path | Responsibility |
|------|----------------|
| `toestub/__init__.py` | Version string |
| `toestub/schemas.py` | Free-param allowlist, pin_config allowlist, path resolve, validation errors |
| `toestub/envelope.py` | `build_envelope(...)` common JSON response |
| `toestub/tools_job.py` | Handlers: run, catalog, rotation, audit, firewall_read |
| `toestub/mcp_server.py` | FastMCP server + tool registration + stdio main |
| `pyproject.toml` | Project meta, optional deps, `toestub-mcp` script |
| `docs/examples/toestub.mcp.json` | Host MCP config snippet |
| `docs/JOB_OS.md` | ToeStub section (link tools + config) |
| `docs/TOESTUB.md` | Short agent-facing connect guide |
| `tests/test_toestub_schemas.py` | Validation / pin rejection |
| `tests/test_toestub_envelope.py` | Envelope invariants |
| `tests/test_toestub_tools.py` | Handler integration with fixture LAS |
| `tests/test_toestub_mcp_list.py` | Server lists five tools |
| `.github/workflows/job-coherence.yml` | Add toestub pytest + optional smoke |

---

### Task 1: Schemas — free-param allowlist and path resolve

**Files:**
- Create: `toestub/__init__.py`
- Create: `toestub/schemas.py`
- Test: `tests/test_toestub_schemas.py`

**Interfaces:**
- Produces:
  - `FREE_PARAM_KEYS: frozenset[str]`
  - `PIN_CONFIG_KEYS: frozenset[str]`
  - `class ToeStubValidationError(ValueError)`
  - `validate_free_params(d: dict | None) -> dict` — returns only allowed keys; raises on unknown keys or if any key in `{"pin_writable", "depth_mono_eps", "soft_T", "seq_mix", "face_weight"}` appears inside free_params
  - `validate_pin_config(d: dict | None) -> dict` — only `PIN_CONFIG_KEYS`; empty dict if None
  - `resolve_path(path: str | None, *, repo_root: Path | None = None) -> Path | None` — None stays None; relative joined to `TOESTUB_REPO_ROOT` or `repo_root` or cwd
  - `check_allow_roots(path: Path, allow_roots: list[Path] | None) -> None` — raise if allow_roots set and path not under any root
  - `get_repo_root() -> Path` — env `TOESTUB_REPO_ROOT` or cwd
  - `get_timeout_s() -> float` — env `TOESTUB_TIMEOUT_S` default 300.0
  - `get_allow_roots() -> list[Path] | None` — parse `TOESTUB_ALLOW_ROOTS` comma-separated; None if unset

- [ ] **Step 1: Write failing tests**

```python
# tests/test_toestub_schemas.py
from pathlib import Path
import pytest
from toestub.schemas import (
    validate_free_params,
    validate_pin_config,
    ToeStubValidationError,
    resolve_path,
    check_allow_roots,
)

def test_free_params_accepts_closed_set():
    out = validate_free_params({"channel_pack": "surface_min", "align_mode": "depth_primary"})
    assert out["channel_pack"] == "surface_min"

def test_free_params_rejects_unknown():
    with pytest.raises(ToeStubValidationError):
        validate_free_params({"depth_mono_eps": 1e-3})

def test_free_params_rejects_pin_writable():
    with pytest.raises(ToeStubValidationError):
        validate_free_params({"pin_writable": True})

def test_pin_config_accepts_mono_violations():
    out = validate_pin_config({"max_depth_mono_violations": 5})
    assert out["max_depth_mono_violations"] == 5

def test_pin_config_rejects_channel_pack():
    with pytest.raises(ToeStubValidationError):
        validate_pin_config({"channel_pack": "surface_min"})

def test_resolve_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("TOESTUB_REPO_ROOT", str(tmp_path))
    p = resolve_path("tests/fixtures/mini_edr.las")
    assert p == tmp_path / "tests/fixtures/mini_edr.las"

def test_allow_roots_blocks(tmp_path):
    outside = Path("C:/Windows") if Path("C:/Windows").exists() else tmp_path.parent
    with pytest.raises(ToeStubValidationError):
        check_allow_roots(outside / "x.las", [tmp_path])
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

Run: `pytest tests/test_toestub_schemas.py -q --tb=line`  
Expected: import/collection error

- [ ] **Step 3: Implement `toestub/__init__.py` and `schemas.py`**

```python
# toestub/__init__.py
__version__ = "0.1.0"

# toestub/schemas.py — implement interfaces above; FREE_PARAM_KEYS from realm.job_os.types field names
```

Use exact free keys matching `FreeParams` fields. PIN_CONFIG_KEYS at minimum:
`depth_mono_eps`, `max_depth_mono_violations`, `require_survey`, `require_regime`, `min_align_score`, `survey_total_g_tol`, `survey_magf_lo`, `survey_magf_hi`, `regime_shock_k`, `science_seed`.

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_toestub_schemas.py -q`

- [ ] **Step 5: Commit**

```bash
git add toestub/__init__.py toestub/schemas.py tests/test_toestub_schemas.py
git commit -m "feat(toestub): schemas for free params and pin_config allowlists"
```

---

### Task 2: Response envelope

**Files:**
- Create: `toestub/envelope.py`
- Test: `tests/test_toestub_envelope.py`

**Interfaces:**
- Consumes: none from Task 1 required
- Produces:
  - `build_envelope(*, ok: bool, surface: str, certified: bool | None = None, near_miss: bool | None = None, branch: str | None = None, paths: dict | None = None, explore: dict | None = None, error: str | None = None, extra: dict | None = None) -> dict`
  - If `explore` is not None, force `explore["not_acceptance"] = True` and `explore["pin_writable"] = False`
  - Always include `"pin_writable": False` at top level
  - Always include `"ontology": "toestub_envelope_v1"`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_toestub_envelope.py
from toestub.envelope import build_envelope

def test_envelope_forces_explore_not_acceptance():
    env = build_envelope(
        ok=True,
        surface="ok",
        certified=False,
        explore={"looks_promising": True, "not_acceptance": False, "pin_writable": True},
    )
    assert env["explore"]["not_acceptance"] is True
    assert env["explore"]["pin_writable"] is False
    assert env["pin_writable"] is False

def test_envelope_error():
    env = build_envelope(ok=False, surface="fail", error="missing las")
    assert env["ok"] is False
    assert env["error"] == "missing las"
    assert env["certified"] is None
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/test_toestub_envelope.py -q`

- [ ] **Step 3: Implement `envelope.py`**

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add toestub/envelope.py tests/test_toestub_envelope.py
git commit -m "feat(toestub): response envelope with explore not_acceptance guard"
```

---

### Task 3: Tool handlers — firewall_read + audit + catalog

**Files:**
- Create: `toestub/tools_job.py`
- Test: `tests/test_toestub_tools.py` (partial; expand in later tasks)

**Interfaces:**
- Consumes: `schemas.*`, `build_envelope`
- Produces:
  - `tool_firewall_read(run_dir: str, *, include_explore: bool = False) -> dict`
  - `tool_job_audit(path: str, *, write_report: bool = False) -> dict`
  - `tool_job_catalog(out_dir: str) -> dict`
  - Each returns envelope dict

**Behavior:**
- `tool_firewall_read`: resolve path; if `FIREWALL.json` load it; else if `COHERENCE.json` call `build_job_firewall(result=coh, ...)`; else error. `certified` from firewall. `surface` one line.
- `tool_job_audit`: if `path/ROTATION_REPORT.json` exists → `audit_rotation_batch`; else `audit_job_run`. `ok` from audit. Optional write `AUDIT.json`.
- `tool_job_catalog`: `write_job_os_catalog(resolve_path(out_dir))`; `certified=None`; surface with n_runs.

- [ ] **Step 1: Write failing tests using fixture smoke run**

```python
# tests/test_toestub_tools.py
from pathlib import Path
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds
from toestub.tools_job import tool_firewall_read, tool_job_audit, tool_job_catalog

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_edr.las"

def test_firewall_read_and_audit_after_run(tmp_path):
    result = run_job_coherence_loop(
        las_path=FIXTURE,
        out_root=tmp_path / "os",
        initial=FreeParams(channel_pack="surface_min"),
        thresholds=JobThresholds(),
        max_rounds=4,
        os_mode=True,
        stability_k=1,
    )
    assert result["solved"] is True
    fr = tool_firewall_read(result["out_root"])
    assert fr["ok"] is True
    assert fr["certified"] is True
    assert fr["pin_writable"] is False
    au = tool_job_audit(result["out_root"])
    assert au["ok"] is True

def test_catalog(tmp_path):
    # run one job under tmp_path first or empty catalog
    cat = tool_job_catalog(str(tmp_path))
    assert cat["ok"] is True
    assert cat["certified"] is None
```

- [ ] **Step 2: Run — expect FAIL (tools_job missing)**

Run: `pytest tests/test_toestub_tools.py::test_firewall_read_and_audit_after_run tests/test_toestub_tools.py::test_catalog -q`

- [ ] **Step 3: Implement handlers in `tools_job.py`**

Import:
```python
from realm.job_os.audit import audit_job_run, audit_rotation_batch
from realm.job_os.catalog import write_job_os_catalog
from realm.job_os.firewall import build_job_firewall
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add toestub/tools_job.py tests/test_toestub_tools.py
git commit -m "feat(toestub): firewall_read, job_audit, job_catalog handlers"
```

---

### Task 4: Tool handlers — job_run

**Files:**
- Modify: `toestub/tools_job.py`
- Modify: `tests/test_toestub_tools.py`

**Interfaces:**
- Produces:
  - `tool_job_run(*, las_path: str, micropulse_path: str | None = None, survey_path: str | None = None, out_root: str | None = None, max_rounds: int = 6, stability_k: int = 1, free_params: dict | None = None, pin_config: dict | None = None, with_regime: bool = False, with_science: bool = False, with_dynamical_topology: bool = False, max_rows: int | None = None, eow_package: str | None = None, include_explore: bool = False) -> dict`

**Behavior:**
1. `validate_free_params` / `validate_pin_config`
2. Resolve all paths; `check_allow_roots` if configured
3. Require LAS file exists
4. Build `FreeParams(**free)` and `JobThresholds(**pin_config merged with defaults)`
5. Call `run_job_coherence_loop(..., os_mode=True, ...)`
6. Envelope from result: `certified=result.get("firewall_certified")`, paths to COHERENCE/FIREWALL/PARTNER_RECIPE, near_miss from result
7. On exception: envelope ok=False with error string
8. Do **not** pass free_params keys into JobThresholds

- [ ] **Step 1: Write failing test**

```python
def test_job_run_fixture_certified(tmp_path):
    from toestub.tools_job import tool_job_run
    env = tool_job_run(
        las_path=str(FIXTURE),
        out_root=str(tmp_path / "run"),
        max_rounds=4,
        free_params={"channel_pack": "surface_min"},
    )
    assert env["ok"] is True
    assert env["certified"] is True
    assert Path(env["paths"]["firewall"]).is_file()

def test_job_run_rejects_pin_in_free(tmp_path):
    from toestub.tools_job import tool_job_run
    env = tool_job_run(
        las_path=str(FIXTURE),
        out_root=str(tmp_path / "bad"),
        free_params={"depth_mono_eps": 0.1},
    )
    assert env["ok"] is False
    assert "free" in (env.get("error") or "").lower() or "valid" in (env.get("error") or "").lower()
```

- [ ] **Step 2: Run — expect FAIL on missing function or incomplete**

- [ ] **Step 3: Implement `tool_job_run`**

- [ ] **Step 4: Run full `tests/test_toestub_tools.py` — PASS**

- [ ] **Step 5: Commit**

```bash
git add toestub/tools_job.py tests/test_toestub_tools.py
git commit -m "feat(toestub): job_run handler with pin-safe free params"
```

---

### Task 5: Tool handlers — job_rotation

**Files:**
- Modify: `toestub/tools_job.py`
- Modify: `tests/test_toestub_tools.py`

**Interfaces:**
- Produces:
  - `tool_job_rotation(*, manifest_path: str | None = None, manifest: dict | None = None, out_root: str | None = None, dry_run: bool = False, max_rows: int | None = None, include_explore: bool = False) -> dict`

**Behavior:**
- Require exactly one of `manifest_path` or `manifest`
- If path: load JSON via `load_rotation_manifest` or pass path to `run_job_rotation`
- Call `run_job_rotation(..., dry_run=dry_run, max_rows=max_rows)`
- Envelope: `branch=report["branch"]`, `certified=(branch=="ROTATION_PASS")`, paths include `batch_dir`, `rotation_report`

- [ ] **Step 1: Write failing test**

```python
def test_job_rotation_fixture_manifest(tmp_path):
    from toestub.tools_job import tool_job_rotation
    # Prefer docs/examples/job_rotation_fixture.manifest.json with absolute las override via inline:
    man = {
        "prereg_id": "toestub_test",
        "stability_k": 1,
        "max_rounds": 4,
        "free_params": {"channel_pack": "surface_min"},
        "wells": [
            {"well_id": "w1", "las": str(FIXTURE)},
            {"well_id": "w2", "las": str(FIXTURE)},
        ],
    }
    env = tool_job_rotation(manifest=man, out_root=str(tmp_path / "rot"))
    assert env["ok"] is True
    assert env["branch"] == "ROTATION_PASS"
    assert env["certified"] is True
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `tool_job_rotation`**

If `manifest` dict given without writing file: write temp MANIFEST under out_root or pass dict to `run_job_rotation` (kernel already accepts dict).

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add toestub/tools_job.py tests/test_toestub_tools.py
git commit -m "feat(toestub): job_rotation handler"
```

---

### Task 6: FastMCP server + five tools + entrypoint

**Files:**
- Create: `toestub/mcp_server.py`
- Create: `pyproject.toml` (minimal)
- Test: `tests/test_toestub_mcp_list.py`

**Interfaces:**
- Produces: `create_server() -> FastMCP`, `main() -> None` runs stdio
- Tools registered with names:
  - `toestub_job_run`
  - `toestub_job_catalog`
  - `toestub_job_rotation`
  - `toestub_job_audit`
  - `toestub_firewall_read`
- Each tool returns **JSON string** (hosts expect text) via `json.dumps(envelope)` OR dict if FastMCP serializes — prefer `json.dumps` for stability

**pyproject.toml minimal:**

```toml
[project]
name = "123abc-grok-toestub"
version = "0.1.0"
description = "ToeStub MCP governor for Job Coherence OS"
requires-python = ">=3.11"
dependencies = ["mcp>=1.0"]

[project.optional-dependencies]
dev = ["pytest", "numpy"]

[project.scripts]
toestub-mcp = "toestub.mcp_server:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["toestub*", "realm*"]
```

If monorepo packaging of `realm*` is awkward, document `PYTHONPATH=.` and keep script as module:

```python
# mcp_server.py
def main():
    import sys
    # ensure repo root on path
    ...
    mcp.run(transport="stdio")
```

Use FastMCP:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("toestub", instructions="Job OS cognitive governor. Pin sealed. Explore never certifies.")

@mcp.tool(name="toestub_job_audit")
def toestub_job_audit(path: str, write_report: bool = False) -> str:
    import json
    from toestub.tools_job import tool_job_audit
    return json.dumps(tool_job_audit(path, write_report=write_report))
# ... similarly for other tools
```

- [ ] **Step 1: Write failing test for tool name list**

```python
# tests/test_toestub_mcp_list.py
from toestub.mcp_server import TOOL_NAMES, create_server

def test_five_tool_names():
    assert set(TOOL_NAMES) == {
        "toestub_job_run",
        "toestub_job_catalog",
        "toestub_job_rotation",
        "toestub_job_audit",
        "toestub_firewall_read",
    }
    assert len(TOOL_NAMES) == 5

def test_create_server():
    s = create_server()
    assert s is not None
```

Keep `TOOL_NAMES` as a module-level tuple for easy testing without async list_tools.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `mcp_server.py` + `pyproject.toml`**

- [ ] **Step 4: Run tests + manual import**

```bash
pytest tests/test_toestub_mcp_list.py tests/test_toestub_tools.py -q
python -c "from toestub.mcp_server import create_server; create_server(); print('ok')"
```

- [ ] **Step 5: Commit**

```bash
git add toestub/mcp_server.py pyproject.toml tests/test_toestub_mcp_list.py
git commit -m "feat(toestub): FastMCP stdio server with five Job OS tools"
```

---

### Task 7: Docs + CI wire

**Files:**
- Create: `docs/TOESTUB.md`
- Create: `docs/examples/toestub.mcp.json`
- Modify: `docs/JOB_OS.md` (short ToeStub section)
- Modify: `.github/workflows/job-coherence.yml` (add toestub tests)

**Docs content for `docs/TOESTUB.md`:**
- What ToeStub is / is not
- Install: `pip install mcp`, `PYTHONPATH=.`, run `python -m toestub.mcp_server` or `toestub-mcp`
- Host JSON example (Windows paths)
- Tool table (five tools)
- Pin law + non-goals
- Link to design spec

**`docs/examples/toestub.mcp.json`:**

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

**CI:** add to pytest list:
```
tests/test_toestub_schemas.py
tests/test_toestub_envelope.py
tests/test_toestub_tools.py
tests/test_toestub_mcp_list.py
```
paths filter: `toestub/**`, `docs/TOESTUB.md`

- [ ] **Step 1: Write docs files**

- [ ] **Step 2: Update workflow**

- [ ] **Step 3: Run full toestub + job_os audit suite**

```bash
pytest tests/test_toestub_*.py tests/test_job_os_audit.py -q
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add docs/TOESTUB.md docs/examples/toestub.mcp.json docs/JOB_OS.md .github/workflows/job-coherence.yml
git commit -m "docs+ci: ToeStub connect guide and CI coverage"
```

---

### Task 8: Spec success criteria check + final commit

**Files:** none new (verify only)

- [ ] **Step 1: Manual checklist against design §6**

| Criterion | How to verify |
|-----------|----------------|
| Server advertises 5 tools | `TOOL_NAMES` test + create_server |
| Fixture job certified | `test_job_run_fixture_certified` |
| Audit ok | `test_firewall_read_and_audit_after_run` |
| Rotation PASS | `test_job_rotation_fixture_manifest` |
| Free pin rewrite rejected | `test_job_run_rejects_pin_in_free` |
| Docs present | `docs/TOESTUB.md`, example mcp json |

- [ ] **Step 2: Mark design success criteria checkboxes in spec** (optional edit)

- [ ] **Step 3: Final status commit if any doc checkbox updates**

```bash
git status
# if clean, done; else commit docs only
```

---

## Spec coverage matrix

| Spec requirement | Task |
|------------------|------|
| stdio MCP | Task 6 |
| Five Job tools only | Tasks 3–6 |
| Free-param closed set | Task 1, 4 |
| pin_config explicit | Task 1, 4 |
| Envelope + explore not_acceptance | Task 2 |
| firewall_read | Task 3 |
| job_audit | Task 3 |
| job_catalog | Task 3 |
| job_run | Task 4 |
| job_rotation | Task 5 |
| Host config snippet | Task 7 |
| CI | Task 7 |
| No shell / no handoff | Global + no tasks add them |
| TOESTUB_ALLOW_ROOTS | Task 1 (+ call in tools_job path resolve) |
| Timeout env | Task 1 API; Task 4/5 may use for documentation only in v0 (optional signal.alarm/not on Windows — **v0: document timeout; do not require Unix signals**) |

**Windows timeout note:** Do not use `signal.SIGALRM`. v0 success does not require enforced wall-clock kill; env `TOESTUB_TIMEOUT_S` is reserved for future cooperative timeout. Document this in `docs/TOESTUB.md`.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-31-toestub-mcp-governor.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, executing-plans style with checkpoints  

Which approach?
