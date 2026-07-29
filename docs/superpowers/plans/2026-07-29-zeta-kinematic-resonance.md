# Zeta-Kinematic Resonance Stub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save and run the conceptual `zeta_kinematic_resonance.py` stub headlessly, then report correspondence errors and the FFT plot artifact.

**Architecture:** Single module with class `ZetaKinematicResonance`: hardcoded simulated Laplacian eigenvalues ≈ first four ζ zeros, absolute-error correspondence test, FFT of eigenvalue gaps with zero-padding, matplotlib PNG save. No real geometry or MaxOp integration.

**Tech Stack:** Python 3, numpy, scipy, matplotlib; run with `MPLBACKEND=Agg`.

**Spec:** `docs/superpowers/specs/2026-07-29-zeta-kinematic-resonance-design.md`

## Global Constraints

- Match the user-provided architecture/API; do not rewrite into a research pipeline.
- Prefer headless safety via process env `MPLBACKEND=Agg` (do not edit script body unless backend fails).
- Unit test suite is a **non-goal** (spec); verification is run + log + artifact checks only.
- Do not add `requirements.txt`, README, MaxOp wiring, or real Coutsias roots.
- Honest readout: strong correspondence is expected (tautological λ); FFT is demo-only.

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `zeta_kinematic_resonance.py` | Full stub: class + `__main__` pipeline |
| `zeta_resonance_spikes.png` | Generated FFT plot (artifact, not hand-edited) |

---

### Task 1: Create the resonance module

**Files:**
- Create: `zeta_kinematic_resonance.py`

**Interfaces:**
- Consumes: none (greenfield)
- Produces:
  - `class ZetaKinematicResonance`
  - `__init__(self, d_distinctions: int = 3, r_relations: int = 8)`
  - `compute_root_laplacians(self, coutsias_roots) -> np.ndarray`
  - `test_zeta_correspondence(self, laplacian_eigenvalues) -> list[float]`
  - `fourier_transform_gaps(self, laplacian_eigenvalues) -> tuple[np.ndarray, np.ndarray]`
  - `plot_prime_wave_resonance(self, freqs, fft_vals) -> None` (writes `zeta_resonance_spikes.png`)

- [ ] **Step 1: Write `zeta_kinematic_resonance.py` with the full provided architecture**

Create `zeta_kinematic_resonance.py` at the repo root with exactly this content (preserve class names, defaults, zeta table, simulated eigenvalues, and pipeline):

```python
import numpy as np
from scipy.fftpack import fft, fftfreq
import matplotlib.pyplot as plt
import logging

# Configure rigorous logging for the quantum-topological run
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ZetaKinematicResonance:
    def __init__(self, d_distinctions=3, r_relations=8):
        """
        Initializes the Zeta-Kinematic Wave Functor.
        D = Minimal crossing number (Distinctions, e.g., 3 for a trefoil)
        R = Topological braiding patterns (Relations, e.g., 2^3 = 8)
        """
        self.D = d_distinctions
        self.R = r_relations
        self.topological_action_S_min = self.D * self.R * (2 * np.pi)

        # The first non-trivial zeros of the Riemann Zeta function (\gamma_n)
        # Represents the resonant harmonic frequencies of the quantum Hilbert space
        self.zeta_zeros = np.array([14.1347, 21.0220, 25.0108, 30.4248, 32.9350, 37.5861])

    def compute_root_laplacians(self, coutsias_roots):
        """
        Ingests the exact 3D Cartesian real roots from coutsias_kinematics.py
        and constructs the specific Sheaf Laplacian for each discrete state.
        Returns the simulated residual strain eigenvalues.
        """
        logging.info(f"Constructing Sheaf Laplacians for {len(coutsias_roots)} Coutsias real roots...")
        # Simulating the extraction of the lowest non-zero eigenvalues (\lambda_1)
        # from the exact 3D geometries of the 4 Cyclosporin A states.
        # In a perfectly resonant system, these should scale towards the zeta zeros.
        simulated_eigenvalues = np.array([14.13, 21.02, 25.01, 30.42])
        return simulated_eigenvalues

    def test_zeta_correspondence(self, laplacian_eigenvalues):
        """
        Tests the correspondence rule: Do the geometric strain eigenvalues
        of the Coutsias roots map to the Riemann Zeta wave frequencies?
        """
        logging.info("Testing Zeta-Kinematic Correspondence Rule...")
        correspondence_errors = []

        for i, eig in enumerate(laplacian_eigenvalues):
            target_zeta = self.zeta_zeros[i]
            error = np.abs(eig - target_zeta)
            correspondence_errors.append(error)
            logging.info(
                f"State {i+1} | Laplacian Eigenvalue: {eig:.4f} | "
                f"Target Zeta Zero: {target_zeta:.4f} | Error: {error:.4f}"
            )

        mean_error = np.mean(correspondence_errors)
        if mean_error < 0.1:
            logging.info(
                "VERDICT: Strong Resonance. The 3D geometries are collapsed onto the prime wave field."
            )
        return correspondence_errors

    def fourier_transform_gaps(self, laplacian_eigenvalues):
        """
        Extracts the energy gaps between the discrete metastable states and
        applies a Fourier transform to identify recurring frequency spikes,
        mirroring the prime wave field interference patterns.
        """
        logging.info("Running Fourier Transform on the discrete geometric energy gaps...")
        # Calculate gaps between consecutive eigenvalues
        gaps = np.diff(laplacian_eigenvalues)

        # Pad with zeros to simulate a continuous wave field for FFT
        padded_gaps = np.pad(gaps, (0, 128), 'constant')
        fft_values = np.abs(fft(padded_gaps))
        frequencies = fftfreq(len(padded_gaps))

        # Keep only positive frequencies
        pos_mask = frequencies > 0
        return frequencies[pos_mask], fft_values[pos_mask]

    def plot_prime_wave_resonance(self, freqs, fft_vals):
        """Generates the visual proof of geometric-prime wave correspondence."""
        plt.figure(figsize=(10, 6))
        plt.plot(freqs, fft_vals, color='purple', linewidth=2)
        plt.title('Fourier Transform of Coutsias Root Energy Gaps', fontsize=16)
        plt.xlabel('Frequency', fontsize=14)
        plt.ylabel('Amplitude (Resonance Spikes)', fontsize=14)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.savefig('zeta_resonance_spikes.png', dpi=300)
        logging.info("Saved visual proof to zeta_resonance_spikes.png")

if __name__ == "__main__":
    # The 4 exact real roots discovered for Cyclosporin A
    cyclosporin_roots = [0.1245, -0.8921, 1.4432, -2.0154]

    # Initialize the Wave Functor
    functor = ZetaKinematicResonance(d_distinctions=3, r_relations=8)

    # Run the Pipeline
    laplacian_spectra = functor.compute_root_laplacians(cyclosporin_roots)
    functor.test_zeta_correspondence(laplacian_spectra)

    freqs, fft_vals = functor.fourier_transform_gaps(laplacian_spectra)
    functor.plot_prime_wave_resonance(freqs, fft_vals)
```

- [ ] **Step 2: Confirm file exists at repo root**

Run (PowerShell):

```powershell
Test-Path zeta_kinematic_resonance.py
```

Expected: `True`

- [ ] **Step 3: Commit**

```powershell
git add zeta_kinematic_resonance.py
git commit -m "feat: add zeta-kinematic resonance stub"
```

---

### Task 2: Install dependencies and run headlessly

**Files:**
- Runtime only (no source edits unless import/backend fails)
- Create (artifact): `zeta_resonance_spikes.png`

**Interfaces:**
- Consumes: `zeta_kinematic_resonance.py` from Task 1
- Produces: process exit 0, INFO logs, `zeta_resonance_spikes.png`

- [ ] **Step 1: Check imports**

Run:

```powershell
python -c "import numpy, scipy, matplotlib; print('ok')"
```

Expected: `ok`. If `ModuleNotFoundError`, install:

```powershell
python -m pip install numpy scipy matplotlib
```

Re-run the import check until `ok`.

- [ ] **Step 2: Run the stub headlessly**

From repo root `C:\PRIMEdEV-1\123abc-grok`:

```powershell
$env:MPLBACKEND = "Agg"
python zeta_kinematic_resonance.py
```

Expected log patterns (INFO):
- `Constructing Sheaf Laplacians for 4 Coutsias real roots...`
- Four lines: `State N | Laplacian Eigenvalue: ... | Target Zeta Zero: ... | Error: ...`
- `VERDICT: Strong Resonance. The 3D geometries are collapsed onto the prime wave field.`
- `Running Fourier Transform on the discrete geometric energy gaps...`
- `Saved visual proof to zeta_resonance_spikes.png`

Expected exit code: `0`

If matplotlib backend errors despite `MPLBACKEND=Agg`, apply the minimal script fix from the spec: insert before `import matplotlib.pyplot as plt`:

```python
import matplotlib
matplotlib.use("Agg")
```

Then re-run and note the delta in the commit message.

- [ ] **Step 3: Verify artifact**

```powershell
Get-Item zeta_resonance_spikes.png | Select-Object FullName, Length
```

Expected: file exists, `Length` > 0.

- [ ] **Step 4: Commit plot artifact (optional but preferred for reproducibility)**

```powershell
git add zeta_resonance_spikes.png
git commit -m "chore: add zeta resonance FFT plot artifact"
```

If the user prefers not to commit binary plots, skip this step and leave the PNG untracked.

---

### Task 3: Report results (operator handoff)

**Files:**
- None (conversation report only)

**Interfaces:**
- Consumes: stdout logs from Task 2, path/size of PNG
- Produces: written summary for the user

- [ ] **Step 1: Extract correspondence errors from the run log**

Record for each state i=1..4:
- Laplacian eigenvalue
- Target zeta zero
- Absolute error

Compute / note mean error (should be ≪ 0.1 given hardcoded λ).

- [ ] **Step 2: Deliver the operator report**

Report in chat, with this structure:

1. **Exit code** and command used (`MPLBACKEND=Agg python zeta_kinematic_resonance.py`)
2. **Correspondence table** (4 rows)
3. **Verdict line** (Strong Resonance expected)
4. **Plot path** absolute path + file size
5. **Honest caveat** (one sentence): correspondence is tautological; FFT is demo-only

- [ ] **Step 3: Stop**

Do not add MaxOp, real roots, packaging, or further features unless the user requests a new plan.

---

## Spec Coverage Checklist

| Spec requirement | Task |
|------------------|------|
| Save `zeta_kinematic_resonance.py` with provided API | Task 1 |
| Headless run via `MPLBACKEND=Agg` | Task 2 |
| Report errors, verdict, PNG presence | Task 3 |
| No unit test suite | Met by omission |
| No MaxOp / Coutsias / packaging | Met by omission |
| Honest readout of tautology | Task 3 Step 2 |

## Self-Review Notes

- No TBD/placeholder steps; full script body embedded in Task 1.
- Signatures consistent across tasks.
- Spec non-goals respected (no pytest, no README).
- Backend fallback path specified only if Agg env fails.
