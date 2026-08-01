# Dynamical Topology Dual Spine + Navigator Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One stage-axis dynamical topology engine (zigzag-faithful) with measure + pin-safe control interfaces, Job/handoff/Crit wiring, and a stdlib navigator menu that runs the same effects without flag memorization.

**Architecture:** Domain stage builders feed ordered point clouds into a shared engine that builds per-stage kNN complexes and tracks birth/death along the stage axis. Measure writes `DynamicalTopologyReport` (never ACCEPTANCE). Control adds optional `topology_stable` to Job/handoff fixed-point when `--topo-stability` is on. Menu is a pure UI shell over existing CLIs/APIs. MaxOp sheaf L remains spatial dual; pin never written.

**Tech Stack:** Python 3.11+, numpy, existing `realm/job_os`, `realm/handoff`, `realm/kb_geometry`, `realm/sheaf_backend`; stdlib menu (`input`); pytest.

## Global Constraints

- Never write dual-gate LengthPolicy pin (`soft_T`, `seq_mix`, `face_weight`) or Job QC pin thresholds from topology scores.
- Every topology report: `not_acceptance: true`, `pin_writable: false`, `acceptance_writable: false`.
- Provenance: `kb_source` cites `arXiv:2410.11042` + AXiomZ dual spine.
- Stages = discrete time (not LLM transformer layers).
- Menu must not duplicate negotiate/loop logic — call `run_job_coherence_loop` / CLI subprocess only.
- Windows-friendly (dev target).
- Never λ=γ.

**Spec:** `docs/superpowers/specs/2026-07-31-dynamical-topology-dual-spine-design.md`

## File map

| Path | Responsibility |
|------|----------------|
| `realm/dynamical_topology/__init__.py` | Public exports |
| `realm/dynamical_topology/types.py` | Stage, report schema helpers |
| `realm/dynamical_topology/complexes.py` | Per-stage kNN complex |
| `realm/dynamical_topology/engine.py` | Stage-axis barcode + phases + `topology_stable` |
| `realm/dynamical_topology/stages_job.py` | Build stages from Job run_dir / cycle reports |
| `realm/dynamical_topology/stages_crit.py` | Build stages from Crit filtration / action samples |
| `realm/dynamical_topology/stages_handoff.py` | Build stages from handoff coherence ledger |
| `realm/dynamical_topology/sheaf_dual.py` | Optional MaxOp/aqft co-report (read-only) |
| `realm/job_os/loop.py` | MEASURE wire + CONTROL flag |
| `realm/handoff/coherence.py` | Optional measure on rounds |
| `job_coherence.py` | `--topo-stability`, `--with-dynamical-topology` |
| `handoff_coherence.py` | Optional flags if cheap |
| `realm_menu.py` | Navigator entrypoint |
| `realm/menu/__init__.py`, `realm/menu/app.py` | Menu wizard |
| `docs/JOB_OS.md` | Menu-first onboarding note |
| `tests/test_dynamical_topology_*.py` | Engine, stages, control, menu |

---

### Task 1: Types + report schema

**Files:**
- Create: `realm/dynamical_topology/__init__.py`
- Create: `realm/dynamical_topology/types.py`
- Test: `tests/test_dynamical_topology_types.py`

**Interfaces:**
- Produces: `Stage` dataclass `(index: int, label: str, points: np.ndarray)`; `empty_report() -> dict`; `finalize_report(d: dict) -> dict` forces not_acceptance guards

- [ ] **Step 1: Write failing test**

```python
# tests/test_dynamical_topology_types.py
from realm.dynamical_topology.types import Stage, empty_report, finalize_report
import numpy as np

def test_empty_report_guards():
    r = empty_report()
    assert r["kind"] == "dynamical_topology"
    assert r["not_acceptance"] is True
    assert r["pin_writable"] is False
    assert r["acceptance_writable"] is False
    assert "2410.11042" in r["kb_source"]

def test_finalize_forces_guards():
    bad = {"kind": "dynamical_topology", "not_acceptance": False, "pin_writable": True}
    r = finalize_report(bad)
    assert r["not_acceptance"] is True
    assert r["pin_writable"] is False

def test_stage_holds_points():
    s = Stage(index=0, label="s0", points=np.zeros((3, 2)))
    assert s.points.shape == (3, 2)
```

- [ ] **Step 2: Run test — expect FAIL (import error)**

```bash
pytest tests/test_dynamical_topology_types.py -q
```

- [ ] **Step 3: Implement types**

```python
# realm/dynamical_topology/types.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np

KB_SOURCE = "arXiv:2410.11042 + AXiomZ dual spine"
TRANSFER_NOTE = "stages as discrete time (not LLM layers)"

@dataclass
class Stage:
    index: int
    label: str
    points: np.ndarray  # (n, d)

def empty_report() -> dict[str, Any]:
    return {
        "kind": "dynamical_topology",
        "not_acceptance": True,
        "ontology": "dynamical_topology_dual_spine_not_lambda_eq_gamma",
        "kb_source": KB_SOURCE,
        "transfer_note": TRANSFER_NOTE,
        "n_stages": 0,
        "bars": [],
        "n_long": 0,
        "n_short": 0,
        "phases": {"labels": [], "dominant": None},
        "sheaf_dual": None,
        "pin_writable": False,
        "acceptance_writable": False,
    }

def finalize_report(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    out["not_acceptance"] = True
    out["pin_writable"] = False
    out["acceptance_writable"] = False
    out.setdefault("kind", "dynamical_topology")
    out.setdefault("kb_source", KB_SOURCE)
    out.setdefault("transfer_note", TRANSFER_NOTE)
    out.setdefault("ontology", "dynamical_topology_dual_spine_not_lambda_eq_gamma")
    return out
```

```python
# realm/dynamical_topology/__init__.py
from realm.dynamical_topology.types import Stage, empty_report, finalize_report
__all__ = ["Stage", "empty_report", "finalize_report"]
```

- [ ] **Step 4: Run tests — PASS**

```bash
pytest tests/test_dynamical_topology_types.py -q
```

- [ ] **Step 5: Commit**

```bash
git add realm/dynamical_topology tests/test_dynamical_topology_types.py
git commit -m "feat: dynamical_topology types and report guards"
```

---

### Task 2: Complex builder + stage-axis engine

**Files:**
- Create: `realm/dynamical_topology/complexes.py`
- Create: `realm/dynamical_topology/engine.py`
- Modify: `realm/dynamical_topology/__init__.py`
- Test: `tests/test_dynamical_topology_engine.py`

**Interfaces:**
- Consumes: `Stage`, `finalize_report`
- Produces: `knn_adjacency(points, k) -> ndarray`; `run_dynamical_topology(stages, *, knn_k=5, long_frac=0.25) -> dict`; `topology_stable(report, *, prev=None, drop_tol=0.5) -> bool`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dynamical_topology_engine.py
import numpy as np
from realm.dynamical_topology.types import Stage
from realm.dynamical_topology.engine import run_dynamical_topology, topology_stable

def _cloud(center, n=12, scale=0.05, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(center, scale, size=(n, 2))

def test_stable_phases_have_long_structure():
    # rearrange: scatter; stable: two tight clusters repeated
    stages = [
        Stage(0, "rearrange", _cloud(0, n=20, scale=1.0, seed=1)),
        Stage(1, "stable", np.vstack([_cloud(0, seed=2), _cloud(5, seed=3)])),
        Stage(2, "stable", np.vstack([_cloud(0, seed=4), _cloud(5, seed=5)])),
        Stage(3, "emit", np.vstack([_cloud(0, seed=6), _cloud(5, seed=7)])),
    ]
    rep = run_dynamical_topology(stages, knn_k=4, long_frac=0.2)
    assert rep["not_acceptance"] is True
    assert rep["n_stages"] == 4
    assert rep["n_long"] >= 1
    assert rep["phases"]["dominant"] in ("rearrange", "stable", "refine", "emit")

def test_topology_stable_detects_collapse():
    good = run_dynamical_topology([
        Stage(0, "a", _cloud(0, seed=1)),
        Stage(1, "b", _cloud(0, seed=2)),
    ])
    # Force collapse in a synthetic prev/curr comparison via n_long
    prev = dict(good)
    prev["n_long"] = 10
    curr = dict(good)
    curr["n_long"] = 1
    curr["phases"] = {"labels": ["rearrange"], "dominant": "rearrange"}
    assert topology_stable(curr, prev=prev, drop_tol=0.3) is False
    assert topology_stable(good, prev=None) in (True, False)  # defined, no crash
```

- [ ] **Step 2: Run — FAIL**

```bash
pytest tests/test_dynamical_topology_engine.py -q
```

- [ ] **Step 3: Implement complexes + engine**

Implementation notes (must follow):
- `complexes.knn_adjacency`: reuse pattern from `realm/kb_geometry/graph.py` knn (or import `knn_graph` and use matrix).
- `engine.run_dynamical_topology`:
  1. For each stage, if `points.shape[0] < 2`, skip or emit empty stage bar.
  2. Per stage compute a scalar structure score = mean edge length of kNN graph **or** H0 long-bar count from `vietoris_rips_h0(points)` (prefer import `realm.kb_geometry.rips_h0.vietoris_rips_h0`).
  3. Stage-axis barcode: treat structure series `s[t]` as 1-D values; call `zigzag_window_barcode` style elder H0 across stages by building a 1-D series of length T (structure scores), plus attach per-stage VR H0 n_long into report.
  4. Phases: map stage labels if provided; else use `phase_summary` logic on windowed structure (import from `kb_geometry.zigzag_windows.phase_summary` where possible).
  5. Always `finalize_report`.
- `topology_stable`:
  - If report missing/empty stages → False when prev required else True if n_stages>=1 and dominant in stable|emit.
  - If prev and prev.n_long > 0 and curr.n_long < (1-drop_tol)*prev.n_long → False.
  - If dominant == "rearrange" and prev is not None → False.
  - Else True.

- [ ] **Step 4: Tests PASS**

```bash
pytest tests/test_dynamical_topology_engine.py tests/test_dynamical_topology_types.py -q
```

- [ ] **Step 5: Commit**

```bash
git add realm/dynamical_topology tests/test_dynamical_topology_engine.py
git commit -m "feat: dynamical topology stage-axis engine and topology_stable"
```

---

### Task 3: Job OS stage builder + MEASURE wire

**Files:**
- Create: `realm/dynamical_topology/stages_job.py`
- Modify: `realm/job_os/loop.py` (execute cycle summary + optional report write)
- Modify: `job_coherence.py` (flags)
- Test: `tests/test_dynamical_topology_job.py`

**Interfaces:**
- Consumes: `run_dynamical_topology`, cycle dirs with `sources_summary.json` / regime channel data
- Produces: `build_stages_from_job_run(run_dir: Path) -> list[Stage]`; loop writes `DYNAMICAL_TOPOLOGY.json` when enabled

- [ ] **Step 1: Failing test**

```python
# tests/test_dynamical_topology_job.py
from pathlib import Path
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.types import FreeParams, JobThresholds
import json

def test_job_loop_writes_dynamical_topology(tmp_path):
    result = run_job_coherence_loop(
        las_path=Path("tests/fixtures/mini_edr.las"),
        out_root=tmp_path / "j",
        initial=FreeParams(channel_pack="surface_min", regime_mode="persist_h0"),
        thresholds=JobThresholds(),
        max_rounds=2,
        os_mode=True,
        run_id="dt1",
        with_regime=True,
        with_dynamical_topology=True,  # new kwarg
        stability_k=1,
    )
    root = Path(result["out_root"])
    # After run, either cycle report or run-level report exists
    assert (root / "DYNAMICAL_TOPOLOGY.json").is_file() or list(root.glob("cycle_*/DYNAMICAL_TOPOLOGY.json"))
    # Load and check guards
    p = root / "DYNAMICAL_TOPOLOGY.json"
    if not p.is_file():
        p = list(root.glob("cycle_*/DYNAMICAL_TOPOLOGY.json"))[0]
    body = json.loads(p.read_text(encoding="utf-8"))
    assert body["not_acceptance"] is True
    assert body["pin_writable"] is False
```

- [ ] **Step 2: Implement `stages_job.py`**

```python
# build_stages_from_series_history(list of channel dicts or structure scores)
# build_stages_from_job_run(run_dir): for each cycle_*/sources_summary.json or regime_report,
#   extract a point cloud via series_point_cloud from regime channels if available,
#   else 1-D from structure_score repeated as 2-D points for engine
```

- [ ] **Step 3: Wire loop**

Add kwargs to `run_job_coherence_loop` and `execute_job_cycle`:
- `with_dynamical_topology: bool = False`
- After each cycle (or at end of run using all cycles): if flag, `build_stages_from_job_run` + `run_dynamical_topology`, write JSON, attach path to result and TREND_ROLLUP optional field `dynamical_topology`.

Add CLI:
```text
--with-dynamical-topology
```

- [ ] **Step 4: Tests PASS + no pin writes**

```bash
pytest tests/test_dynamical_topology_job.py tests/test_job_coherence_core.py -q
rg -n "soft_T|LengthPolicy" realm/dynamical_topology || true
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: Job OS dynamical topology measure wire"
```

---

### Task 4: CONTROL — topo-stability fixed-point

**Files:**
- Modify: `realm/job_os/loop.py` fixed-point block
- Modify: `job_coherence.py` `--topo-stability`
- Modify: `realm/dynamical_topology/engine.py` if needed
- Test: `tests/test_dynamical_topology_control.py`

**Interfaces:**
- Consumes: `topology_stable`, cycle reports
- Produces: SOLVED only if `topology_stable` holds for K when flag on

- [ ] **Step 1: Failing test**

```python
def test_topo_stability_blocks_solve_when_unstable(monkeypatch, tmp_path):
    # Monkeypatch topology_stable to always False when flag on
    import realm.dynamical_topology.engine as eng
    monkeypatch.setattr(eng, "topology_stable", lambda *a, **k: False)
    from realm.job_os.loop import run_job_coherence_loop
    # ... run with with_dynamical_topology=True, topo_stability=True, max_rounds=2
    # expect solved False OR stop_reason indicates topo (if implementation uses that)
```

Also:

```python
def test_topo_stability_off_preserves_solve(tmp_path):
    # flag off, fixture → solved True (existing behavior)
```

- [ ] **Step 2: Implement**

In loop fixed-point section when `topo_stability` True:
- Maintain `prev_topo_report`
- Compute current report each cycle (requires with_dynamical_topology True; if control on without measure, auto-enable measure)
- `topo_ok = topology_stable(curr, prev=prev_topo)`
- SOLVED requires existing conditions **and** `topo_ok` for streak (use same stability_k or dedicated; default same K)
- Reset streak if topo_ok False

- [ ] **Step 3: Tests PASS**

```bash
pytest tests/test_dynamical_topology_control.py tests/test_dynamical_topology_job.py -q
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: topology_stable control gate for Job OS fixed-point"
```

---

### Task 5: Handoff measure + Crit stage builder + sheaf dual

**Files:**
- Create: `realm/dynamical_topology/stages_handoff.py`
- Create: `realm/dynamical_topology/stages_crit.py`
- Create: `realm/dynamical_topology/sheaf_dual.py`
- Modify: `realm/handoff/coherence.py` optional write report (flag `with_dynamical_topology`)
- Modify: `realm/axiomz.py` or crit path: optional engine instead of thin zigzag only
- Test: `tests/test_dynamical_topology_crit_handoff.py`

**Interfaces:**
- `build_stages_from_handoff_ledger(ledger) -> list[Stage]`
- `build_stages_from_crit_filtration(filt) -> list[Stage]`
- `sheaf_dual_fingerprint(...) -> dict | None` read-only from existing operators if available

- [ ] **Step 1: Tests** for synthetic ledger stages and crit filtration stages produce report with guards; sheaf_dual None when MaxOp missing is OK.

- [ ] **Step 2: Implement builders**  
  - Handoff: each ledger round → points from free-param numeric encoding (one-hot decorate/physics + top_k) as small vectors  
  - Crit: sample action S on grid windows as 1-D→2-D points or use diagram persistence series as points  

- [ ] **Step 3: Wire handoff optional flag; crit `with_zigzag` can call engine**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: Crit and handoff dynamical topology stage builders"
```

---

### Task 6: Navigator menu

**Files:**
- Create: `realm/menu/__init__.py`
- Create: `realm/menu/app.py`
- Create: `realm_menu.py`
- Test: `tests/test_realm_menu.py`

**Interfaces:**
- `build_job_smoke_argv(out_dir) -> list[str]`
- `build_job_wizard_kwargs(...) -> dict` for `run_job_coherence_loop`
- `main()` interactive; tests only hit pure builders (no interactive input)

- [ ] **Step 1: Failing tests**

```python
from realm.menu.app import build_job_smoke_argv, menu_items

def test_menu_items_include_core():
    labels = [x["label"] for x in menu_items()]
    assert any("Job OS" in L for L in labels)
    assert any("Catalog" in L for L in labels)
    assert any("topology" in L.lower() for L in labels)

def test_smoke_argv_contains_fixture():
    argv = build_job_smoke_argv("out/x")
    assert "--os" in argv
    assert "mini_edr.las" in " ".join(argv)
```

- [ ] **Step 2: Implement menu**

```text
menu_items(): list of {id, label}
build_job_smoke_argv(out_dir) -> argv for job_coherence.py
run_job_smoke(): subprocess or run_job_coherence_loop with fixture paths
wizard: input() prompts; print CLI equivalent; confirm; run
catalog: write_job_os_catalog
topology report: load last LATEST or prompt path, run_dynamical_topology on job run
docs: print path to docs/JOB_OS.md and design spec
```

`realm_menu.py`:
```python
from realm.menu.app import main
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Manual smoke (document in commit message)**

```bash
# non-interactive path already tested; optional:
echo 0 | python realm_menu.py   # exit
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: realm_menu navigator for Job OS and dynamical topology"
```

---

### Task 7: Docs + CI + package exports

**Files:**
- Modify: `docs/JOB_OS.md` — menu-first section
- Modify: `docs/superpowers/specs/2026-07-31-dynamical-topology-dual-spine-design.md` status → Implemented when done
- Modify: `.github/workflows/job-coherence.yml` — add dynamical topology + menu unit tests
- Modify: `realm/dynamical_topology/__init__.py` full exports

- [ ] **Step 1: Update JOB_OS.md** with:

```markdown
## Navigator menu (non-CLI)

python realm_menu.py

1) Job OS fixture smoke
2) Job OS custom wizard
3) Catalog
4) Dynamical topology report
...
```

- [ ] **Step 2: Extend CI pytest list** with `tests/test_dynamical_topology_*.py` `tests/test_realm_menu.py`

- [ ] **Step 3: Run full related suite**

```bash
pytest tests/test_dynamical_topology_*.py tests/test_realm_menu.py tests/test_job_coherence_core.py tests/test_trend_rollup.py -q
```

- [ ] **Step 4: Commit**

```bash
git commit -m "docs+ci: dynamical topology dual spine menu onboarding"
```

---

## Spec coverage checklist

| Spec section | Task |
|--------------|------|
| Engine API + report | 1–2 |
| Job MEASURE | 3 |
| CONTROL topo-stability | 4 |
| Crit + handoff + sheaf dual | 5 |
| Navigator menu | 6 |
| Docs D5 | 7 |
| Pin / not_acceptance | 1, 2, 3, 4 |
| Never LLM layers | types TRANSFER_NOTE |
| Phases D0–D5 | Tasks 1–7 |

## Placeholder scan

None intentional. Engine may approximate full zigzag intersections in v1 but must use **stage axis** (Task 2).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-31-dynamical-topology-dual-spine.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, task-by-task with checkpoints  

**Which approach?**
