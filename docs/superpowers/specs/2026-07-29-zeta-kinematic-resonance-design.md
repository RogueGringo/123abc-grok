# Zeta-Kinematic Resonance Stub — Design Spec

**Date:** 2026-07-29  
**Status:** Approved approach B (pending user review of this written spec)  
**Workspace:** `123abc-grok` (greenfield)

## Intent

Deliver a **runnable conceptual stub** of the Zeta-Kinematic Correspondence Rule: map four discrete Cyclosporin A geometric states (placeholder Coutsias roots) through simulated Sheaf Laplacian eigenvalues onto the first non-trivial Riemann zeta zeros, then Fourier-transform energy gaps and save a frequency plot.

This pass is **not** a scientific validation of “biology computes structure via ζ.” It is an executable architecture sketch with honest expectations about tautological inputs.

## Goals

1. Save `zeta_kinematic_resonance.py` with the provided class API and pipeline.
2. Run it headlessly (`MPLBACKEND=Agg`) so `savefig` works without a display.
3. Report: per-state correspondence errors, mean-error verdict log line, presence of `zeta_resonance_spikes.png`.

## Non-goals

- Real Coutsias polynomial root-finding or 3D closure geometry.
- Real sheaf Laplacian construction from peptide coordinates.
- Integration with `primed-topology` / MaxOp `CellularSheaf` (deferred).
- Claims that matching pre-tuned eigenvalues to ζ zeros constitutes a proof.
- Packaging (`requirements.txt`, README) unless requested later.
- Unit test suite (stub is single-script demo).

## Context

| Asset | Role |
|-------|------|
| This repo | Empty at design time; only this stub + artifacts |
| Sibling `primed-topology` | Real sheaf Laplacian + honest ζ-spacing demo; **not** wired in this pass |
| Draft script | Hardcodes λ ≈ γₙ; correspondence is tautological by construction |

## Architecture

Single module, single class, CLI entrypoint.

```
cyclosporin_roots (4 placeholder floats)
        │
        ▼
compute_root_laplacians(roots)
  → ignores geometry; returns simulated λ = [14.13, 21.02, 25.01, 30.42]
        │
        ▼
test_zeta_correspondence(λ)
  → abs(λ_i − γ_i) for i = 0..3 against first four ζ imag parts
  → log mean error; if mean < 0.1 log “Strong Resonance”
        │
        ▼
fourier_transform_gaps(λ)
  → gaps = diff(λ); pad to length 131; |FFT|; positive freqs
        │
        ▼
plot_prime_wave_resonance(freqs, fft_vals)
  → savefig zeta_resonance_spikes.png (dpi=300)
```

### Components

| Symbol | Responsibility |
|--------|----------------|
| `ZetaKinematicResonance.__init__` | Store D, R; `S_min = D·R·2π`; table of first six γₙ |
| `compute_root_laplacians` | Log root count; return fixed simulated eigenvalues |
| `test_zeta_correspondence` | Per-state error list; mean-error threshold 0.1 |
| `fourier_transform_gaps` | Diff → pad → FFT → positive frequency branch |
| `plot_prime_wave_resonance` | Matplotlib line plot; purple; grid; save PNG |
| `__main__` | Wire pipeline end-to-end |

### Data contracts

- **Input roots:** `list[float]` length ≥ 1 (only length is logged; values unused).
- **Laplacian eigenvalues:** 1-D `np.ndarray` of length 4 (this stub).
- **Zeta targets:** `self.zeta_zeros[:len(eigenvalues)]` (indices 0..3).
- **FFT return:** `(frequencies_pos, amplitudes_pos)` same length.
- **Plot artifact:** `zeta_resonance_spikes.png` in CWD.

## Runtime plan

1. Write `zeta_kinematic_resonance.py` (source matches user architecture; no logic rewrites beyond what is required to run).
2. Ensure `numpy`, `scipy`, `matplotlib` are importable (install if missing).
3. Run: `MPLBACKEND=Agg python zeta_kinematic_resonance.py` from repo root.
4. Capture logs; confirm PNG exists; report mean error and plot path.

### Headless safety (approach B)

- Prefer process environment `MPLBACKEND=Agg` at run time rather than editing the script body, so the published architecture stays as given.
- If the default backend still fails, set `matplotlib.use("Agg")` before `pyplot` import as a minimal fix and note the delta.

## Error handling

- Import failures: install deps, re-run once.
- Plot failures: report traceback; do not claim success without PNG.
- No custom exception hierarchy for this stub.

## Testing / verification

| Check | Pass criterion |
|-------|----------------|
| Script runs | Exit code 0 |
| Correspondence logs | Four state lines with errors ≈ 0.00x |
| Verdict | “Strong Resonance” logged (expected under hardcoded λ) |
| Artifact | `zeta_resonance_spikes.png` exists and size > 0 |

## Honest readout (documentation for operators)

- Correspondence “success” is expected because simulated eigenvalues are rounded ζ zeros.
- FFT of three gaps zero-padded does not validate prime-gap interference structure.
- Future work (out of scope): real roots → real `L_F` spectra via MaxOp → falsifiable distance to γₙ and prime-gap spectra.

## Open questions (resolved)

| Question | Decision |
|----------|----------|
| Deliverable level | Runnable stub as given |
| Success definition | Save + run + report |
| Approach | B — headless-safe run without rewriting the architecture |
| MaxOp integration | Not this pass |

## Implementation order

1. Create `zeta_kinematic_resonance.py`.
2. Install runtime deps if needed.
3. Run under `MPLBACKEND=Agg`.
4. Report logs, errors, plot path.
5. Stop (no further features).
