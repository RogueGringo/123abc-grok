# Validation Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a three-phase validation ladder (null battery → sec≈k → cyclic PDB/HF deep dive) that hard-gates on real ζ preference without λ=γ scoring.

**Architecture:** Shared `realm/validate/` harness injects seed ordinates into the existing forge/residual/mold path; three thin CLIs write JSON artifacts; HF Hub is optional data plane only.

**Tech Stack:** Python 3.11+, NumPy, SciPy, existing `realm.*`; optional `huggingface_hub`; multi-process via `realm.hw` / `ProcessPoolExecutor`.

**Spec:** `docs/superpowers/specs/2026-07-30-validation-ladder-design.md`

## Global Constraints

- Ontology: never score sheaf λ against γ (no λ=γ residual path).
- Phase 1 gate: `mean_F_ζ < 0.8 * min(mean_F_scramble, mean_F_goe, mean_F_poisson)`.
- Phase 3 v1: single PDB deep dive; RCSB primary; HF optional fallback.
- HF: demo/metadata downloads only — no full CPSea2 load on 8 GB RAM.
- Default knobs from `evolve_result.json`; N=13, k=14, sectors=6 unless CLI overrides.
- Workers: `recommend_workers()`; BLAS 1 thread in workers.
- Exit codes: 0 pass, 2 gate fail, 3 I/O fail.

---

## File map

| Path | Responsibility |
|------|----------------|
| `realm/zeta_field.py` | Add `ZetaField.from_gammas(g)` factory |
| `realm/derive.py` | Optional `gammas=` inject into `Deriver` |
| `realm/lock_key.py` | Pass-through if Deriver needs seed override via knobs/`field` |
| `realm/validate/__init__.py` | Package exports |
| `realm/validate/seeds.py` | ζ / scramble / GOE / Poisson ordinate factories |
| `realm/validate/harness.py` | `score_seed(...)` → F, R, mold metrics |
| `realm/validate/report.py` | JSON write helpers |
| `realm/validate/pdb_io.py` | RCSB fetch + CA backbone parse |
| `realm/validate/hf_io.py` | `hf_hub_download` demo/metadata |
| `realm/validate/decoys.py` | CA jitter / torsion decoys |
| `null_battery.py` | Phase 1 CLI |
| `sec_scale.py` | Phase 2 CLI |
| `pdb_decoy.py` | Phase 3 CLI |
| `tests/test_validate_seeds.py` | Seed unit tests |
| `tests/test_validate_harness.py` | Harness vs Keymaker |
| `tests/fixtures/mini_cyclic.pdb` | Tiny fixture for offline parse |
| `.gitignore` | `data/pdb/`, `data/hf/` if missing |

---

### Task 1: ZetaField / Deriver seed injection

**Files:**
- Modify: `realm/zeta_field.py`
- Modify: `realm/derive.py` (`Deriver` + `run` D0)
- Modify: `realm/lock_key.py` (`Keymaker.forge` optional `gammas`)
- Test: `tests/test_validate_seeds.py` (created here for field factory; expanded in Task 2)

**Interfaces:**
- Produces: `ZetaField.from_gammas(gammas: np.ndarray) -> ZetaField`
- Produces: `Deriver(..., gammas: np.ndarray | None = None)` uses inject if set else `ZetaField.first`
- Produces: `Keymaker.forge(**knobs)` accepts optional `gammas=`

- [ ] **Step 1: Write failing test**

```python
# tests/test_validate_seeds.py
import numpy as np
from realm.zeta_field import ZetaField

def test_from_gammas_gaps():
    g = np.array([10.0, 12.0, 15.0, 20.0])
    f = ZetaField.from_gammas(g)
    assert np.allclose(f.gammas, g)
    assert np.allclose(f.gaps, np.diff(g))
```

- [ ] **Step 2: Run test — expect FAIL** (`from_gammas` missing)

Run: `python -m pytest tests/test_validate_seeds.py::test_from_gammas_gaps -v`

- [ ] **Step 3: Implement `from_gammas`**

```python
@classmethod
def from_gammas(cls, gammas: np.ndarray) -> "ZetaField":
    g = np.asarray(gammas, dtype=float).ravel()
    g = np.sort(g[g > 0])
    if g.size < 2:
        raise ValueError("need at least 2 positive ordinates")
    return cls(gammas=g, gaps=np.diff(g))
```

- [ ] **Step 4: Wire Deriver**

In `Deriver`, add field `gammas: np.ndarray | None = None`. In `run()` D0:

```python
if self.gammas is not None:
    field = ZetaField.from_gammas(self.gammas)
else:
    field = ZetaField.first(self.n_zeros)
```

`Keymaker.forge`: if knobs contain `gammas`, pass to Deriver (convert list→array).

- [ ] **Step 5: Test pass + commit**

```bash
python -m pytest tests/test_validate_seeds.py::test_from_gammas_gaps -v
git add realm/zeta_field.py realm/derive.py realm/lock_key.py tests/test_validate_seeds.py
git commit -m "feat: ZetaField.from_gammas + Deriver seed injection for nulls"
```

---

### Task 2: Seed factories (ζ, scramble, GOE, Poisson)

**Files:**
- Create: `realm/validate/__init__.py`
- Create: `realm/validate/seeds.py`
- Modify: `tests/test_validate_seeds.py`

**Interfaces:**
- Produces: `make_seed(kind: str, k: int, rng: np.random.Generator) -> np.ndarray` shape `(k,)` increasing positive
- Kinds: `"zeta" | "scramble" | "goe" | "poisson"`

- [ ] **Step 1: Failing tests**

```python
from realm.validate.seeds import make_seed
import numpy as np

def test_zeta_matches_table():
    g = make_seed("zeta", 6, np.random.default_rng(0))
    from realm.zeta_field import ZETA_ZEROS_IMAG
    assert np.allclose(g, ZETA_ZEROS_IMAG[:6])

def test_scramble_preserves_gap_multiset():
    rng = np.random.default_rng(1)
    z = make_seed("zeta", 10, rng)
    s = make_seed("scramble", 10, np.random.default_rng(1))
    assert np.allclose(sorted(np.diff(z)), sorted(np.diff(s)))

def test_goe_poisson_length_and_positive():
    for kind in ("goe", "poisson"):
        g = make_seed(kind, 14, np.random.default_rng(2))
        assert g.shape == (14,)
        assert np.all(np.diff(g) > 0)
```

- [ ] **Step 2: Implement `seeds.py`**

```python
def make_seed(kind: str, k: int, rng: np.random.Generator) -> np.ndarray:
    from realm.zeta_field import ZETA_ZEROS_IMAG, ZetaField
    k = max(int(k), 2)
    if kind == "zeta":
        return ZETA_ZEROS_IMAG[:k].copy()
    z = ZETA_ZEROS_IMAG[:k].copy()
    span = float(z[-1] - z[0])
    g0 = float(z[0])
    if kind == "scramble":
        gaps = np.diff(z)
        rng.shuffle(gaps)
        out = np.concatenate([[g0], g0 + np.cumsum(gaps)])
        return out
    # unit-mean spacings → map to same span
    if kind == "goe":
        # Wigner surmise sample via inverse CDF approximation / rejection
        s = _sample_gue_spacings(k - 1, rng)
    elif kind == "poisson":
        s = rng.exponential(1.0, size=k - 1)
    else:
        raise ValueError(kind)
    s = s / (s.sum() + 1e-15) * span
    return np.concatenate([[g0], g0 + np.cumsum(s)])
```

Implement `_sample_gue_spacings` via transform sampling from known p(s) or scipy if available.

- [ ] **Step 3: pytest pass + commit**

```bash
python -m pytest tests/test_validate_seeds.py -v
git add realm/validate tests/test_validate_seeds.py
git commit -m "feat: validate seed factories zeta/scramble/goe/poisson"
```

---

### Task 3: Score harness

**Files:**
- Create: `realm/validate/harness.py`
- Create: `tests/test_validate_harness.py`

**Interfaces:**
- Consumes: `make_seed`, `Keymaker`, `residual`, mold tests
- Produces:

```python
def score_configuration(
    *,
    kind: str,
    knobs: dict,
    N: int,
    n_zeros: int,
    n_sectors: int,
    rng_seed: int = 0,
    alpha: float = 0.45,
    beta: float = 0.25,
    gamma: float = 0.15,
) -> dict:
    """Return JSON-safe dict with F, R, occupancy, breakdown, kind, ..."""
```

- [ ] **Step 1: Failing test — ζ harness ≈ evolve residual scale**

```python
import json
from pathlib import Path
from realm.validate.harness import score_configuration

def test_zeta_harness_low_R():
    kn = json.loads(Path("evolve_result.json").read_text())["best_knobs"]
    out = score_configuration(
        kind="zeta", knobs=kn, N=13, n_zeros=14, n_sectors=6, rng_seed=0
    )
    assert out["R"] < 0.05
    assert out["occupancy"] >= 0.8
    assert "lambda" not in out.get("verdict", "").lower() or "not" in out["verdict"].lower()
```

- [ ] **Step 2: Implement harness**

1. `gammas = make_seed(kind, n_zeros, np.random.default_rng(rng_seed))`  
2. `der = Keymaker(N=..., n_zeros=..., n_sectors=...).forge(**knobs, gammas=gammas)`  
3. residual + mold occupancy as in `evolve.evaluate_knobs` / `score_worker`  
4. Return dict without live objects  

- [ ] **Step 3: pytest + commit**

```bash
python -m pytest tests/test_validate_harness.py -v
git add realm/validate/harness.py tests/test_validate_harness.py
git commit -m "feat: validate score harness for null/decoy path"
```

---

### Task 4: Null battery CLI

**Files:**
- Create: `realm/validate/report.py`
- Create: `null_battery.py`

**Interfaces:**
- CLI: `python null_battery.py --knobs evolve_result.json --reps 5 --workers -1 --json null_battery_result.json`
- Gate field: `passed: bool` when `F_zeta < 0.8 * min(other means)`

- [ ] **Step 1: Implement report helper**

```python
def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 2: Implement `null_battery.py`**

- Load knobs; build list of jobs `(kind, rep)` for kinds `zeta,scramble,goe,poisson` and `rep in range(reps)`.
- Parallel map via ProcessPoolExecutor + picklable worker wrapping `score_configuration`.
- Aggregate mean F/R/dens per kind.
- `passed = mean_F["zeta"] < 0.8 * min(mean_F[k] for k in nulls)`.
- Print table; write JSON; `sys.exit(0 if passed else 2)`.

- [ ] **Step 3: Smoke run serial**

```bash
python null_battery.py --reps 1 --workers 1
```

Expected: JSON written; exit 0 or 2 with clear gate line.

- [ ] **Step 4: Commit**

```bash
git add null_battery.py realm/validate/report.py
git commit -m "feat: null_battery CLI hard zeta preference gate"
```

---

### Task 5: sec_scale CLI (Strategy B)

**Files:**
- Create: `sec_scale.py`

**Interfaces:**
- CLI: `python sec_scale.py --knobs evolve_result.json --sectors 6,8,10,12 --workers -1`

- [ ] **Step 1: Implement**

For each `sec` in list:
- `score_configuration(kind="zeta", n_sectors=sec, ...)`
- If `n_valleys < max(3, sec//2)`: status `FAIL_CAPACITY`
- Collect table rows

Write `sec_scale_result.json` with best dens_return among sealed rows.

- [ ] **Step 2: Smoke**

```bash
python sec_scale.py --sectors 6,8 --workers 1
```

- [ ] **Step 3: Commit**

```bash
git add sec_scale.py
git commit -m "feat: sec_scale CLI strategy B dens_return table"
```

---

### Task 6: PDB I/O + fixture

**Files:**
- Create: `realm/validate/pdb_io.py`
- Create: `tests/fixtures/mini_cyclic.pdb`
- Create: `tests/test_pdb_io.py`
- Modify: `.gitignore` → add `data/pdb/`, `data/hf/`

**Interfaces:**
- `fetch_pdb(pdb_id: str, cache_dir: Path) -> Path`
- `parse_ca_trace(pdb_text: str, chain: str | None) -> np.ndarray` shape `(L, 3)`

- [ ] **Step 1: Minimal fixture** (3–5 CA ATOM lines forming a rough cycle)

- [ ] **Step 2: Test parse**

```python
from pathlib import Path
from realm.validate.pdb_io import parse_ca_trace

def test_parse_fixture():
    text = Path("tests/fixtures/mini_cyclic.pdb").read_text()
    xyz = parse_ca_trace(text, chain="A")
    assert xyz.ndim == 2 and xyz.shape[1] == 3 and xyz.shape[0] >= 3
```

- [ ] **Step 3: Implement fetch (urllib) + parse ATOM CA**

Cache path: `data/pdb/{id}.pdb`. On HTTP error raise `PdbIOError`.

- [ ] **Step 4: pytest + commit**

```bash
python -m pytest tests/test_pdb_io.py -v
git add realm/validate/pdb_io.py tests/fixtures tests/test_pdb_io.py .gitignore
git commit -m "feat: RCSB fetch + CA parse for cyclic PDB deep dive"
```

---

### Task 7: HF I/O (optional data plane)

**Files:**
- Create: `realm/validate/hf_io.py`
- Create: `tests/test_hf_io.py`

**Interfaces:**
- `hf_available() -> bool`
- `download_cpsea_demo(cache_dir: Path) -> Path`  # metadata demo TSV only
- `list_cpsea_demo_pdb_ids(demo_path: Path) -> list[str]`

- [ ] **Step 1: Test with mock** — if `huggingface_hub` missing, `hf_available` is False; download raises clear `ImportError`/`RuntimeError`.

- [ ] **Step 2: Implement** using `hf_hub_download(repo_id="YZY010418/CPSea2", filename=...demo..., repo_type="dataset")` — pin filename to demo path from dataset card (`CPbase_PDB_demo/...` or AFDB demo). If exact path uncertain at implement time, probe list via `list_repo_files` and pick `*demo*metadata*`.

- [ ] **Step 3: Commit**

```bash
git add realm/validate/hf_io.py tests/test_hf_io.py
git commit -m "feat: HF Hub data plane for CPSea demo metadata"
```

---

### Task 8: Decoys + mold ranking

**Files:**
- Create: `realm/validate/decoys.py`
- Create: `tests/test_decoys.py`

**Interfaces:**
- `make_ca_decoys(xyz: np.ndarray, n: int, rng: Generator, noise: float = 0.5) -> list[np.ndarray]`
- `closure_residual(xyz: np.ndarray) -> float`  # ||first-last|| 
- `score_geometry_on_mold(xyz, landscape, key_thetas) -> dict` with `mean_dist`, `in_basin`

Scoring strategy (v1 labeled in report):
1. Build ζ landscape from champion knobs (existing `build_moduli_landscape`).
2. Map each CA ring to a scalar θ proxy: e.g. principal torsion / first PCA plane angle of chord, or mean dihedral; place on [0, 2π).
3. Distance to nearest valley (reuse circular dist from `lock_key`).
4. Report `FALLBACK_THETA_PROXY` in JSON so we never pretend full Coutsias holonomy without work.

- [ ] **Step 1–4:** TDD decoys preserve shape `(L,3)`; native noise=0 clone ranks best under self-distance.

- [ ] **Step 5: Commit**

```bash
git add realm/validate/decoys.py tests/test_decoys.py
git commit -m "feat: CA decoys + mold distance ranking helpers"
```

---

### Task 9: pdb_decoy CLI

**Files:**
- Create: `pdb_decoy.py`

**Interfaces:**
- `python pdb_decoy.py --pdb 1CSA --knobs evolve_result.json --n-decoys 32 --workers -1 --source rcsb`
- Flags: `--allow-hf-fallback`, `--force` (ignore null gate file), `--chain A`

- [ ] **Step 1: Implement end-to-end**

1. Optionally read `null_battery_result.json` — if not `passed` and not `--force`, exit 2 with message.  
2. Fetch/parse native CA.  
3. Build landscape from knobs (ζ).  
4. Score native + decoys (parallel).  
5. Rank; write `pdb_decoy_result.json` + simple matplotlib rank plot.  
6. Exit 0 always if I/O ok (science fail is in JSON `enrichment` fields, not necessarily exit 2 — **except** null gate).  

- [ ] **Step 2: Offline smoke with fixture**

```bash
python pdb_decoy.py --pdb-file tests/fixtures/mini_cyclic.pdb --n-decoys 8 --workers 1 --force
```

- [ ] **Step 3: Commit**

```bash
git add pdb_decoy.py
git commit -m "feat: pdb_decoy CLI native vs decoy mold ranking"
```

---

### Task 10: Integration pass + docs touch

**Files:**
- Modify: short note in design or README only if repo already has README user-facing — prefer `docs/superpowers/specs` cross-link only
- Run full ladder serially

- [ ] **Step 1: Run**

```bash
python null_battery.py --reps 3 --workers -1
python sec_scale.py --sectors 6,8,10,12 --workers -1
python pdb_decoy.py --pdb 1CSA --n-decoys 32 --workers -1
```

- [ ] **Step 2: Record outcomes** in commit message / `validation_ladder_summary.json` (optional aggregate)

- [ ] **Step 3: Commit results artifacts if not gitignored**

```bash
git add null_battery_result.json sec_scale_result.json pdb_decoy_result.json pdb_decoy.png 2>/dev/null || true
git commit -m "chore: validation ladder first-run artifacts"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Seed injection | 1–2 |
| Hard F gate 0.8× | 4 |
| sec≈k table | 5 |
| RCSB single deep dive | 6, 8–9 |
| HF data plane | 7 |
| No λ=γ | harness + ontology tests 3 |
| Multi-core | 4, 9 |
| Exit codes | 4, 9 |

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-30-validation-ladder.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, executing-plans with checkpoints  

Which approach?
