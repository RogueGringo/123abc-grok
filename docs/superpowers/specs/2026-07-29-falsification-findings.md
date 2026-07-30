# Falsification findings: the R < 0.005 seal is not evidence about ζ

**Date:** 2026-07-29
**Status:** accepted. This is the first successful falsification of an *instrument* in this
stack, not of the framework.

> **RETRACTED CLAIM.** "ζ preference under the current residual" is withdrawn. The
> `null_battery_result.json` PASS (32× margin) measured self-consistency of the lock–key
> seating, not discrimination power of the zeta field. The artifacts are kept as-is for the
> record; this document supersedes their interpretation. Residual design re-opens only once
> the equal-budget table is public.
>
> **Explicitly not a licensed fix:** do not restore a λ≈γ scoring path. That would violate
> the ontology the whole stack rests on. The obstruction is in the *selector*, not the
> ontology.

**Question asked:** is the 32× ζ margin in `null_battery_result.json` real preference for the
Riemann zeta spectrum, or an artifact of evaluating an 8-parameter fit at its own optimum
against unfit controls?

**Answer:** artifact — and the mechanism is deeper than the fitting procedure. Most of the
residual is zero by construction, for any input spectrum. What the residual actually selects
is "any sufficiently regular sequence that yields ~6 usable minima under the current
action", not ζ structure.

**What survives.** The spectral-action → Crit(θ*) → multimode geometry derivation ladder is
untouched and remains the right abstraction. Only the residual used for *selection* needs
redesign.

Three independent lines of evidence, below. Two are complete and decisive; the third is a
larger compute sweep whose returns so far agree.

---

## The claim under test

`null_battery_result.json` reports:

| arm | mean F |
|---|---|
| zeta | 0.004532 |
| scramble | 0.14622 |
| goe | 0.16608 |
| poisson | 0.16114 |

Gate `F_ζ < 0.8 × min(F_null)` passes with a 32× margin.

The confound: `realm/score_worker.py:53` calls `Keymaker(...).forge(**kn)` with **no**
`gammas`, so `evolve.py` optimized all eight knobs against the real ζ field at exactly
N=13, k=14, sectors=6. `realm/validate/harness.py:38` then injects each null's ordinates
but reuses those frozen ζ-fitted knobs. The nulls never received a tuning budget.

---

## Finding 1 — the advantage does not survive one window of transfer

`transfer.py`. Freeze the champion knobs, score a **disjoint** window of genuine ζ
ordinates. No refitting, so this is independent of any optimizer-budget question.

Real ordinates come from `realm/validate/zeros.py`, which computes them with mpmath and
verifies three ways (agreement with the repo's hardcoded table to 1e-9; every value a root
of the Riemann-Siegel Z function; Riemann-von Mangoldt count N(T) = 39.74 at T = 123.4 vs
expected 40). This matters because `realm/validate/seeds.py:41` silently mean-gap
*extrapolates* past γ₁₅ — scoring "held-out zeros" through that path would have tested
extrapolation, not ζ.

| window | F(ζ) | best plausible null | ζ advantage |
|---|---|---|---|
| γ₁–γ₁₄ **(trained)** | 0.004532 | 0.174551 | **38.5×** |
| γ₁₅–γ₂₈ (held out) | 0.429140 | 0.428569 | **1.00×** |
| γ₂₉–γ₄₂ (held out) | 0.575680 | 0.575782 | **1.00×** |

On genuine ζ ordinates one window over, the margin is gone. At γ₁₅–γ₂₈ ζ is fractionally
*worse* than GOE. Both transfer conventions were run — preserving the dimensionless
`v[0] = Λ/g_last` ratio, and preserving Λ absolutely — and they agree to three decimals, so
the result does not hinge on that modelling choice. (The DE bounds at `evolve.py:506` are
dimensionless, which is why the rescaled variant is the principled one.)

**Correction — the absolute degradation is confounded; the ratio is not.** The `omega`
parameterization is not window-invariant (see the G5 section below: spread 4.30× on γ₁–γ₁₄ vs
1.47× on γ₁₅–γ₂₈, unreachable by any knob). So the rise from F = 0.0045 to 0.43 is *partly*
the parameterization failing to express a good configuration on higher windows, not purely
"ζ structure fails to transfer" — an over-reading I made initially. What survives is the
**ratio**: every arm at a given window is span-matched to that window and faces the same
compressed spread, so ζ-vs-null at fixed window is internally fair, and that ratio is 1.00×.
A held-out *gate* (rather than a ratio) requires the omega repair first.

Residuals tell the same story more sharply. On the trained window ζ's R is 36× better than
the nulls'; on held-out windows it lands within 1% of them:

| window | R(ζ) | R(scramble) | R(goe) | occupancy, all arms |
|---|---|---|---|---|
| γ₁–γ₁₄ | 0.004532 | 0.165705 | 0.159551 | ~100% |
| γ₁₅–γ₂₈ | 0.133307 | 0.135436 | **0.132735** | 75% |
| γ₂₉–γ₄₂ | 0.025680 | 0.025782 | 0.027196 | 33% |

Occupancy collapses identically for every arm, so off-window the frozen knobs stop molding
anything at all.

---

## Finding 2 — 70% of the residual is zero by construction

This is the structural result, and it is not about fitting at all.

`derive.py:410` fills the sector pool from the critical **minima** of the spectral action
(`pool = _take_diverse(mins, self.n_sectors, [])`). `build_key` then takes `key.thetas` to
be those sector twists, while `build_lock` takes `lock.minima_theta` from the same critical
minima. When the action yields at least `n_sectors` minima, **the lock and the key are the
same set of numbers**, and every residual term that compares them vanishes identically.

Verified directly: at sectors=6 all six key θ coincide with the six lock minima to better
than 1e-12.

| term | weight in R | value at the seal | why |
|---|---|---|---|
| stationarity | 0.30 | 1.7e-13 | keys *are* critical points of S, where dS ≡ 0 |
| crit_coverage | 0.25 | 0.0 | minima are always a subset of keys |
| pin_align | 0.20×0.40 = 0.08 | 0.0 | the two sets coincide |
| theta_ladder_l1 | 0.20×0.35 = 0.07 | 0.0 | the two sets coincide |
| **tautological subtotal** | **0.70** | | |
| corr_penalty | 0.25 | 9.0e-5 | \|Pearson r\| over 6 points, 8 free knobs |
| density_return | 0.20×0.25 = 0.05 | 0.0902 | the only term doing real work |

So `R = 0.004532 ≈ 0.05 × 0.0902`. The entire seal value is 5% of the residual weight
multiplied by a *mediocre* density-return error. The remaining 95% is either structurally
zero or a correlation over six data points fitted by eight parameters.

**The degeneracy is not ζ-specific.** Any spectrum whose action yields ≥6 minima gets the
same free zeros — confirmed for `arith`, `primes`, `outlier`, `sorted_uniform`, `goe`, and
`poisson`. Only `geometric` (3 minima) and `reversed`/`scramble` (5 minima) break the
coincidence, and only because they produce fewer minima than there are sectors.
`crit_coverage` is 0.0 for *every* spectrum tested, without exception.

This also explains `sec_scale_result.json` without invoking any physics. Past sectors=6 the
minima count stays at 6 while keys grow to 8/10/12, so the surplus keys are filled from
non-minima, the coincidence breaks, and `pin_align`/`theta_ladder` wake up — exactly the
observed monotone degradation (R 0.0045 → 0.120 → 0.190 → 0.229, corr_S_λ 0.99991 → 0.649 →
0.365 → 0.166). It is the coincidence breaking, not a scale-dependent relation.

Pinned as executable assertions in `tests/test_residual_degeneracy.py` (19 tests).

### On the one heavy informative term

`_corr_term` (`lock_key.py:41`) returns `1 − |corr(x, y)|` — an **absolute** correlation, so
perfect anti-correlation scores as perfect. The derivation log confirms negative values are
accepted (`corr(S(θ*), λ_gap) = −0.9833`). It correlates `key.S_at` against
`key.spectral_gaps`: six points, eight free knobs.

A short refit reaching |r| for each spectrum shows how cheap that is:

| spectrum | best F | corr_S_λ | dens_return |
|---|---|---|---|
| arith | 0.002442 | **0.999925** | 0.0485 |
| poisson | 0.062442 | 0.983519 | 0.1288 |
| outlier | 0.018401 | 0.974599 | 0.2410 |
| goe | 0.016860 | 0.945032 | 0.0624 |
| zeta | 0.023850 | 0.934350 | 0.1487 |
| geometric | 0.026305 | 0.927506 | 0.1636 |

At equal (small) budget ζ scores the *second worst* correlation of the six. A constant-gap
arithmetic progression achieves 0.99993.

---

## Finding 3 — equal-budget refit (sweep in progress)

`fair_fight.py` gives every arm its own identical budget from a neutral start. Fairness
guarantees, each load-bearing:

- **no warm start** — `evolve.py:517` seeds from `evolve_result.json`, which would hand ζ a
  head start and bias every null's initialization;
- **identical eval count** — `tol=0, atol=0` disables DE's early-convergence exit, so an arm
  that converges early does not receive a smaller effective budget;
- **decoupled randomness** — spectrum draw and optimizer path come from independently
  spawned `SeedSequence` streams;
- **convergence evidence** — each run records where in the budget its best appeared and how
  much the final polish moved it, so a high F can be read as "no good optimum exists"
  rather than "the search ran out of road".

**COMPLETE — 50/50 runs, n=5 per arm, 12,120 DE evals each, exact rank tests.**

| arm | F_best | F_median | exact p vs ζ | relation |
|---|---|---|---|---|
| **arith** | **0.002040** | **0.002040** | **0.0040** | **arm better, disjoint** |
| scramble | 0.002865 | 0.009282 | 0.345 | overlap |
| **zeta** | **0.004421** | **0.004523** | — | — |
| goe | 0.004587 | 0.036415 | 0.0159 | overlap |
| sorted_uniform | 0.004920 | 0.009789 | 0.0079 | overlap |
| reversed | 0.005793 | 0.011664 | 0.0079 | overlap |
| poisson | 0.009482 | 0.036024 | 0.0040 | ζ better, disjoint |
| outlier | 0.014200 | 0.017209 | 0.0040 | ζ better, disjoint |
| geometric | 0.015823 | 0.015829 | 0.0040 | ζ better, disjoint |
| primes | 0.016896 | 0.016897 | 0.0040 | ζ better, disjoint |

Attainable p floor at n=5 vs 5 is 1/C(10,5) = 0.0040; Bonferroni across 9 arms = 0.0357.

**`arith` beats ζ with statistical significance.** Fully disjoint distributions, p = 0.0040,
which survives Bonferroni correction (0.0357). A constant-gap ladder — 13 identical gaps, so
all 13! orderings are the same object, zero information content — is the objective's
*preferred* spectrum. This is the framework's own pre-registered falsifiability criterion,
tripped with significance rather than by a single lucky run.

**But ζ ranks second by median and beats 6 of 9 arms at the floor.** `scramble` (0.002865) and
`goe` (0.004587) post good *best* values on lucky single draws while their medians are 2–8×
worse (0.009282, 0.036415). ζ's median is 0.004523 against a best of 0.004421 — a tight
distribution. So ζ occupies a robust basin where the nulls occasionally get lucky. That is a
real signal, but it is about basin robustness under this optimizer, not about arithmetic.

**The cold-start ζ arm reproduces the published seal.** Three of five ζ instances converge to
F = 0.004523 against the published champion's 0.004532 — from a neutral start, with no warm
start from `evolve_result.json`. That independently validates the refit machinery: `arith`
beating ζ is a like-for-like comparison, not an artifact of a broken optimizer.

Earlier, at a deliberately small 720-eval budget (conservative for this purpose — a small
budget can only *understate* how well an arm does), `arith` reached F = 0.002562 against ζ's
0.005807, and every arm fell between 0.0026 and 0.070 versus the published nulls at ~0.15.

Giving the nulls a budget collapses the published margin, and a zero-information spectrum
beats ζ. The full 10-spectrum × 5-instance sweep is running; every completed run is flushed
to `fair_fight_result.runs.jsonl`, and `--resume` skips finished (kind, instance) pairs so a
sweep can outlive any single invocation.

**Caveats, stated because they cut against the conclusion:**

- ζ's 12,120-eval instances report `best_found_at_eval` at ~100% of budget, meaning the
  budget was still binding rather than converged. Polish gain was ~1e-10, so the surface was
  flat there, but "equal budget" is not yet "equal convergence" for any arm.
- The `goe` arm here inherits the broken sampler documented in recommendation 5 below, so
  that one arm is not a clean random-matrix null. `scramble` (exact gap permutation),
  `poisson` (`rng.exponential`), and crucially `arith` — the decisive falsifier — are
  unaffected.

Findings 1 and 2 do not depend on either caveat.

---

## What this does and does not establish

**Established.** A low R is not by itself evidence that the seed spectrum is special. 70% of
R is structurally zero for any spectrum with enough minima; 25% more is an absolute
correlation over six points with eight free parameters. The published 32× margin does not
survive either a held-out window of real ζ ordinates or an equal tuning budget.

**Not established.** None of this shows the geometry, the projection machinery, or the
Coutsias/waypoint path is wrong. It shows the *validation instrument* cannot currently
distinguish ζ from an arithmetic progression, so it cannot support claims about ζ either
way. The framework is not falsified; the evidence for it is.

**Not addressed.** Phase 3 (`pdb_decoy_result.json`) remains the offline 5-CA fixture run
rather than the `--pdb 1CSA` deep dive Task 10 specifies, with `native_rank: 12` of 17 and
`method: FALLBACK_THETA_PROXY`. Nothing here improves or refutes it.

## Finding 4 — held-out transfer IS non-vacuous, but has no power against GUE

`fair_transfer.py`. The refit sits **inside** the transfer loop: each arm cold-starts on its
own γ₁–γ₁₄ and is scored on its own γ₁₅–γ₂₈ with no refit. Without this, a held-out gate that
scores every arm with ζ-fitted knobs silently reinstates the original confound.

| arm | trained_dens | heldout_dens | degradation | exact p vs ζ | relation |
|---|---|---|---|---|---|
| **zeta** | 0.033894 | **0.117680** | 1.67× | — | — |
| goe | 0.053362 | 0.126305 | 2.37× | **0.500** | overlap |
| poisson | 0.081850 | 0.127535 | 1.08× | **0.500** | overlap |
| scramble | 0.074988 | 0.170958 | 1.72× | 0.050 | ζ better, disjoint |
| arith | 0.040680 | 0.374229 | **9.20×** | 0.050 | ζ better, disjoint |

Two results, both load-bearing:

1. **The ordering reverses out-of-sample.** `arith` wins in-sample (0.00204) and degrades 9.20×
   to the worst held-out value; `scramble` wins in-sample (0.002865) and also loses out-of-sample.
   ζ degrades least among competitive arms and comes out best. A held-out gate is therefore
   **not vacuous** — `arith` can fail it, so property 5 is satisfiable, which it demonstrably
   is not for an in-sample gate.
2. **No power against random-matrix nulls.** `goe` and `poisson` sit at p = 0.500 — exact
   chance, not a narrow margin. Separation from degenerate controls is at the n=3 floor
   (p = 0.050, → 0.200 Bonferroni), so **nothing is significant**.

**Why this is the expected result, not a shortfall.** ζ's unfolded spacing distribution is
approximately stationary across windows (measured: mean gap 3.592 → 2.366 while normalized
spread holds 0.406 → 0.344). That stationarity is what transfers — and GUE has it too, by
Montgomery-Odlyzko. `arith` lacks it (a single gap that rescales between windows), which is
why it collapses. So the gate detects *spacing-distribution stationarity*, a real spectral
property that ζ possesses but does not own.

Getting ζ-specificity requires a statistic sensitive to **long-range** structure — spectral
rigidity, number variance, Δ₃, pair correlation at larger separation — where ζ and GUE
genuinely differ. `density_return` reads ~12 reals of normalized nearest-neighbour gap shape;
no long-range information reaches it. `scramble` is the informative arm precisely because it
preserves the gap multiset and destroys those correlations.

## Convergence with the Jones axioms (Volume 0 / II / III)

Three axioms already in `01-DEVELOPMENT-AXiomZ` independently mandate the same repairs
that the measurements and the adversarial review arrived at. That the three lines converge
raises confidence the repairs are right rather than merely plausible.

**Axiom G5 (Scale-Free Structure)** — "patterns are self-similar, so knowledge gained at one
scale can be transferred to another." The implementation *violates* G5. `derive.py:113` sets
`omega = (g / g[0]) * omega_scale`, so the frequency spread is a property of the window, not
of the knobs:

| window | g[0] | g[-1] | spread g[-1]/g[0] |
|---|---|---|---|
| γ₁–γ₁₄ | 14.135 | 60.832 | **4.3037** |
| γ₁₅–γ₂₈ | 65.113 | 95.871 | 1.4724 |
| γ₂₉–γ₄₂ | 98.831 | 127.517 | 1.2902 |

`omega_scale` is bounded (0.4, 2.8) and multiplies uniformly, so no knob can recover a 4.30×
spread from a 1.47× one. The feasible configuration space is therefore not scale-free across
windows — a G5 violation, and the same defect the review flagged. Any window-invariant
reparameterization (e.g. `omega_n = 1 + (g_n−g_1)/(g_K−g_1)·(omega_span−1)`) restores G5.

**Axiom 4.3 (Persistence Principle)** — "features that persist across many scales are robust
structure; features that appear and disappear quickly are noise." This gives Finding 1 a
principled in-framework reading that does not depend on any ad-hoc ratio threshold: the 38.5×
advantage exists at exactly one window and dies immediately at the next. Persistence 1 of 3.
By 4.3 that is **noise**, not structure. It also prescribes the right gate shape — measure the
*persistence of the advantage across a filtration of windows*, i.e. a barcode over windows,
rather than a score at one window.

**Axiom 6.1 (Topological Verification Principle)** — verification is `d(T, T₀) < ε` against a
**known-good baseline** T₀. Finding 2 shows the current residual is the degenerate case
T₀ = T: the lock and key are the same array, so `d(T, T₀) ≡ 0` by construction. 6.1 is
violated in the sense that matters — there is no independent baseline. The repair 6.1 implies
is exactly the review's: forge the lock reference from a **disjoint** ordinate block with the
same knobs, so `crit_coverage` / `pin_align` / `theta_ladder` / occupancy become real
comparisons.

**Axiom 9.3 (Parameter Importance Inversion)** — "a parameter critical in one regime may be
irrelevant in another." Observed exactly, across the two regimes measured here:

| regime | corr_penalty share of the ζ–null gap | density_return share of R |
|---|---|---|
| frozen ζ-fitted knobs | 87–96% | small |
| equal-budget cold refit | ~0 for ζ (1.9e-6) and arith (2.7e-5) | 99.7–99.99% |

This is `w_A₁(θⱼ) >> w_A₂(θⱼ)`. Its consequence for redesign: any **static** weighting of
residual components — including the current fixed {0.30, 0.25, 0.25, 0.20} — will misweight
across regimes. 9.3 argues for reporting components separately rather than summing them with
frozen weights.

## What would constitute real evidence

1. **Make the residual non-degenerate.** Compare keys against something not derived from the
   same critical set — e.g. hold out minima not used to seed sectors, or score the sector
   twists against independently derived lock features. Until then `pin_align`,
   `theta_ladder_l1`, `crit_coverage`, and `stationarity` should be reported as diagnostics,
   not summed into a fitness.
2. **Report R with degrees of freedom.** Eight knobs against six sectors is not a constrained
   fit. Either raise the sector/ordinate count well above the parameter count, or penalize
   parameters explicitly.
3. **Pre-register the window.** Fit on γ₁–γ₁₄, report on γ₁₅–γ₂₈. Finding 1 shows this
   currently yields no preference, which is the honest headline number.
4. **Keep `arith` as a permanent control arm.** It is the cheapest possible falsifier and it
   currently wins. Any future gate should require ζ to beat a constant-gap progression.
5. **Fix the `goe` arm — it samples neither surmise.** Measured against 200,000 draws from
   `_sample_gue_spacings` (`seeds.py:10`):

   | target | KS D | p | |
   |---|---|---|---|
   | GUE surmise, p(s) = (32/π²)s²e^(−4s²/π) | 0.0851 | ≈0 | rejected |
   | GOE surmise, p(s) = (π/2)s·e^(−πs²/4) | 0.1176 | ≈0 | rejected |

   Sample mean is 0.9223 (both surmises have mean 1) and variance 0.1354 (GUE: 3π/8 − 1 ≈
   0.1781), so it is mean-shifted and under-dispersed.

   The cause is a broken rejection loop. The exponential-proposal branch is sound — the
   envelope 2.5·e^(−s) does dominate p(s), which peaks at 0.772 at s = √(π/8) ≈ 0.627 — but
   on **rejection** the code falls through to a second, different proposal
   (`abs(normal(0.8, 0.4))`) with its own independent accept test rather than retrying the
   first. Mixing two proposals that way does not sample the target density. Deleting the
   fallback and letting the `while` loop retry the exponential proposal fixes it.

   Separately, the arm is misnamed: the intended density is the **GUE** surmise (correct for
   ζ, whose spacings follow Montgomery-Odlyzko / GUE statistics) but it is registered as
   `goe` in `null_battery.py:22`.
