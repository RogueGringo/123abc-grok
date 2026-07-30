# Falsification findings: the R < 0.005 seal is not evidence about ζ

**Date:** 2026-07-29  
**Status:** accepted. First successful falsification of an *instrument* in this
stack, not of the framework.

> **RETRACTED CLAIM.** "ζ preference under the current residual" is withdrawn. The
> historical `null_battery_result.json` PASS (large margin under frozen knobs)
> measured self-consistency of the lock–key seating, not discrimination power of
> the zeta field. Artifacts are kept for the record; this document supersedes
> their interpretation.
>
> **Explicitly not a licensed fix:** do not restore a λ≈γ scoring path. The
> obstruction is in the *selector*, not the ontology.

## What was fixed in code (instrument recalibration)

| Item | Action |
|------|--------|
| Residual fitness | Default `fitness="informative"` → **density-return only**. Stationarity, crit_coverage, pin_align, theta_ladder are diagnostics. |
| Legacy residual | Still available as `fitness="legacy"` for comparison tables only. |
| GUE sampler | Pure exponential-proposal rejection; mixed fallback deleted. Arm named `gue` (`goe` alias). |
| `arith` control | Permanent constant-gap arm in seeds + null battery + fair fight. |
| Transfer protocol | `transfer.py` — train γ₁–₁₄ vs hold γ₁₅–₂₈ / γ₂₉–₄₂ on real mpmath zeros. |
| Equal-budget | `fair_fight.py` — cold start, matched DE budget, no warm start. |
| Null battery | Reports seating check as **artifact**; does not claim ζ preference. |
| Degeneracy tests | `tests/test_residual_degeneracy.py`, `tests/test_gue_sampler.py`. |

## What survives

Spectral-action → Crit(θ*) → multimode geometry derivation ladder — untouched.
External cyclic PDB ranking path is independent of this residual selector.

## What would constitute real evidence (unchanged criteria)

1. Non-degenerate residual (implemented for fitness; further hold-out-minima
   designs remain open research).
2. Report R with degrees of freedom (harness emits `dof`).
3. Pre-register window: fit γ₁–₁₄, report γ₁₅–₂₈ (`transfer.py`).
4. Keep `arith` as permanent control.
5. GUE sampler fixed; arm correctly named.

## Ontology

Never score sheaf λ against γ. Residual redesign must not reintroduce λ=γ.
