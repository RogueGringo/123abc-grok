# Residual Rectification — Design Spec

**Date:** 2026-07-30
**Status:** Sub-spec I implemented (PR #2). Sub-spec II **Stages 6–8 implemented**
(`window_filtration.py`, `cross_window.py`). Stage 9 (powered tournament) open.
**Gate condition met:** the equal-budget table is public (PR #2, `fair_fight_result.json`),
which was the precondition for re-opening residual design.
**Supersedes for selection purposes:** `2026-07-30-validation-ladder-design.md` (retracted)
**Evidence base:** `2026-07-29-falsification-findings.md`
**Axiom source:** `01-DEVELOPMENT-AXiomZ` (Jones Axiomatic Framework v2.0)

---

## 1. The obstruction, as measured

Four facts, all reproduced in committed artifacts. They constrain the design absolutely.

| # | Fact | Evidence |
|---|---|---|
| O1 | `F = R` exactly, and `R = 0.25·corr_penalty + 0.05·density_return` to ~1e-13 in 24/24 runs. 0.70 of residual weight is identically zero. | `fair_fight_result.json` |
| O2 | At n_sectors=6, key θ and lock minima are bit-identical (<1e-12). Not ζ-specific: holds for any spectrum yielding ≥6 minima. | `tests/test_residual_degeneracy.py` |
| O3 | `arith` (constant gap, zero information) beats ζ in-sample: 0.002040 vs 0.004421, disjoint across 5/5 optimizer restarts each. **An existence result** — see §7.1 on why this needs no p-value. | `fair_fight_result.json` |
| O4 | Held-out transfer reverses it (ζ best, `arith` degrades 9.20×) but has **no power** against random matrices: `goe` and `poisson` at p=0.500, exact chance. | `fair_transfer_result.json` |

**Diagnosis.** The instrument reads ~12 reals of normalized nearest-neighbour gap shape. ζ and
GUE agree there (Montgomery-Odlyzko), so no ζ/GUE separation is *reachable* by the current
term set — O4 is the correct answer, not a shortfall. Separation requires **long-range**
structure, and the surviving degrees-of-freedom ratio (8 knobs : 2 live scalars) means no new
term is interpretable until the constraint count rises.

## 2. Required properties (carried forward, with axiom bindings)

| # | Property | Axiom binding |
|---|---|---|
| P1 | No free terms by construction. The four degenerate terms may be diagnostics, never fitness. | 6.1 — verification needs an *independent* baseline T₀; today T₀ = T |
| P2 | Predictive / transfer character. Evaluable on held-out windows without re-optimizing. | 4.3 — one-window features are noise by definition |
| P3 | Ontology preservation. Geometry derived off the ζ field. Never score λ against γ. | — (project invariant, non-negotiable) |
| P4 | Equal-budget / equal-convergence comparability. No warm start, no unequal polish. | 6.2 — reject configurations that violate the guard |
| P5 | Falsifiability. `arith` must be *able* to fail. | G1 — ontological selection requires a rejectable alternative |
| **P6** | **Cross-window sensitivity.** The fitness carrier must read structure invisible in any single window. | **8.2 — "patterns that span multiple frequency windows reveal structure invisible in any single window"** |

P6 is new and is the load-bearing addition. It is not an invention: Axiom 8.2 already states
it, and O4 is the measurement showing its absence is exactly what blocks discrimination.

## 3. Approach selection (L1 filtration)

Three components in the approach cloud; one bar is decisively longer.

- **A. In-window rigidity term** — add number variance / Δ₃ at a single window, raise sectors
  to capacity. **Rejected:** 5 λ-gaps (11 at sectors=12) cannot estimate rigidity, and it
  leaves P6 unsatisfied. Short bar, dies on capacity.
- **C. Two-sided disjoint-block comparison** — forge two geometries from disjoint ordinate
  blocks with shared knobs, score mutual agreement. **Retained as a stage**, not a rival: it
  is B at W=2 with no rigidity content.
- **B. Cross-window persistence functional** — **SELECTED.** Geometry forged on a filtration
  of W windows under shared knobs; fitness is the persistence of cross-window agreement.

**Why B is the long bar.** It satisfies 6.1, G5, 8.1, 8.2, 4.2, 4.3 and 9.3 simultaneously,
and it fixes the DOF ratio *by aggregation* rather than by straining sector capacity:

| configuration | constraint scalars | vs 8 knobs |
|---|---|---|
| today (W=1, sec=6) | 6 | 0.8× |
| W=1, sec=12 (max reachable) | 12 | 1.5× |
| **W=10, sec=6** | **60** | **7.5×** |
| W=10, sec=12 | 120 | 15.0× |

Ordinate supply is not a constraint: 140 verified zeros cost ~14 s once, cached
(`realm/validate/zeros.py`).

## 4. H₁ features and how they are broken

L2 found four circular consistency constraints. Four exceeds the split threshold, so the work
is partitioned into two sub-specs (§5, §6) along the cut that severs the most loops.

| loop | circularity | break |
|---|---|---|
| L1 | Can't aggregate windows without G5 invariance; can't validate invariance without a cross-window test | Reparameterize omega with an anchor that **reproduces the existing window-1 optimum**, then validate on windows 2..W. Anchor is a fixed point, not a fit. |
| L2 | "Degenerate" is defined by the baseline being independent, but the baseline can itself collapse | The guard measures **observed** coincidence (exact-match count between key θ and lock minima), never assumes independence |
| L3 | Rigidity needs points → points need windows → windows need G5 | Resolved by L1's break; strictly orders Sub-spec I before II |
| L4 | Persistence gate needs windows; tournament needs instances; both consume budget | **Windows are the inferential unit** (validity); instances are power. Separable axes, budgeted independently. |

---

## 5. Sub-spec I — Instrument Rectification

Makes the instrument honest. Does **not** attempt ζ-specificity. Must complete and pass before
Sub-spec II means anything.

### Stage 1 — Independent lock baseline (Axiom 6.1)

**Change.** Forge the lock reference (`minima_theta`, `landscape.valleys`) from an action built
on a **disjoint** ordinate block under the *same* knobs, rather than from the same action that
produced the key.

**Why.** O2. Verification is `d(T, T₀) < ε` against a known-good baseline; today T₀ = T, so
`d ≡ 0` by construction and `stationarity`, `crit_coverage`, `pin_align`, `theta_ladder` are
tautological.

**Decision it makes.** Do the four dead terms carry information once the baseline is
independent?

**Pass criterion.** Across ≥20 spectra spanning all arms, each of the four terms has non-zero
variance and its 5th percentile is > 1e-6. Any term still pinned at zero is deleted from
fitness permanently and kept as a diagnostic.

### Stage 2 — Window-invariant frequency parameterization (Axiom G5)

**Change.** Replace `omega = (g/g[0]) · omega_scale` (`derive.py:113`) with a span
parameterization, e.g. `omega_n = 1 + (g_n − g_1)/(g_K − g_1)·(omega_span − 1)`.

**Why.** G5 promises transfer because patterns are self-similar. The current form makes
frequency spread a *window property* no bounded uniform multiplier can restore:

| window | spread g[-1]/g[0] |
|---|---|
| γ₁–γ₁₄ | 4.3037 |
| γ₁₅–γ₂₈ | 1.4724 |
| γ₂₉–γ₄₂ | 1.2902 |

With `omega_scale ∈ (0.4, 2.8)` the feasible set differs per window — a G5 violation, and the
reason Finding 1's *absolute* degradation is confounded (its ratio is not).

**Anchor (breaks loop L1).** Choose `omega_span` bounds so the current window-1 optimum is
reproduced at mid-box (`omega_span ≈ 7.00`). The anchor is a fixed point carried over, not a
refit, so Stage 2 cannot manufacture an improvement.

**Decision it makes.** Is the feasible configuration set window-invariant?

**Pass criterion.** For a fixed knob vector, the reachable `(min, max)` of derived λ-gap shape
agrees across ≥5 windows to within 5%. And the reproduced window-1 F matches the pre-change
value to <1%.

### Stage 3 — Degeneracy guard (Axiom 6.2)

**Change.** A runtime check that stamps every scored configuration with a measured degeneracy
signature and **rejects** (not merely flags) any configuration used for selection where the
signature fires.

**Signature** (measured, per loop L2's break):
`n_exact_coincident(key θ, lock minima) > 0` **or** `occupancy == 1.0` **or**
`stationarity < 1e-6` **or** `crit_coverage == 0`.

**Why.** 6.2 — operations that destroy topological signature are invalid and must be rejected.
O1/O2 are exactly such a destruction, and they went undetected for the whole ladder.

**Decision it makes.** Can a degenerate configuration still reach the fitness path?

**Pass criterion.** Re-running the *published* champion configuration through the guard raises
`DEGENERATE_OBJECTIVE`. If it does not, the guard is wrong.

### Stage 4 — Components reported, never summed with static weights (Axiom 9.3)

**Change.** Emit a component vector. Any scalar reduction is declared per-experiment and
recorded in the artifact; the fixed `{0.30, 0.25, 0.25, 0.20}` blend is retired.

**Why.** 9.3, observed directly: `corr_penalty` carries 87–96% of the ζ–null gap under frozen
knobs and collapses to ~1e-6 after refit, where `density_return` carries 99.7–99.99%. A static
weighting is provably mis-weighted across regimes.

**Decision it makes.** None — this is a reporting invariant that makes later decisions legible.

### Stage 5 — Repair the null samplers

**Change.** Rewrite `_sample_gue_spacings` as inverse-CDF sampling on a precomputed grid of the
β=2 surmise; delete the dual-proposal fallback; rename the arm `gue`; add a genuine `goe` arm
with `(π/2)s·exp(−πs²/4)`; add a KS unit test against the closed-form CDF. Delete the mean-gap
extrapolation branch (`seeds.py:41`) so `make_seed` raises rather than fabricating ordinates.

**Why.** Measured: the current sampler matches neither surmise (KS D=0.085 vs GUE, 0.118 vs
GOE, both p≈0 at n=200k; mean 0.922 vs 1, variance 0.135 vs GUE 0.178). The arm that ties ζ in
O4 is this one, so that tie is **unmeasured**, not small.

**Note.** This changes published null semantics. It is in scope only because O4's conclusion
depends on it.

**Pass criterion.** KS vs the β=2 closed-form CDF has p > 0.05 at n=200k; sample mean 1.000
±0.005; variance 0.1781 ±0.005.

---

## 6. Sub-spec II — Cross-Window Discriminator

Runs only after Sub-spec I passes every stage. This is what decides whether *anything* can
separate ζ from GUE.

### Stage 6 — Frequency-window filtration (Axioms 8.1, 4.2)

**Change.** Score a knob vector against a **filtration of W windows** `{W_f₁ … W_f_W}` under
shared knobs, producing a component vector per window.

**Why.** 8.1 defines the window; 4.2 says structure is revealed across a nested sequence of
scales, not at one. This also lifts the constraint count to 6W (§3).

**Decision it makes.** Does the DOF ratio clear the interpretability threshold?

**Pass criterion.** Constraint scalars ≥ 5× knob count (W ≥ 7 at sectors=6), and every window
independently clears the Stage 3 guard.

### Stage 7 — Cross-window rigidity statistic (Axiom 8.2)

**Change.** The fitness carrier becomes a long-range statistic evaluated *across* the
filtration — candidates, to be selected by measurement in Stage 8, not by preference:
number variance Σ²(L), spectral rigidity Δ₃(L), and pair correlation at separation L > 1.

**Why.** 8.2. This is the only stage that targets the measured obstruction. ζ = RvM smooth
density **+** GUE-like local fluctuation **+** long-range rigidity. A span-matched GUE null has
the local part; `rvm_smooth` and `gram_points` have the density part. Only a statistic
requiring all three jointly can separate ζ from every control.

**Decision it makes.** Is there any statistic in this family that separates ζ from a correctly
sampled GUE null?

**Pass criterion.** Pre-registered: on held-out windows at equal budget, ζ separates from
`gue` with exact rank p ≤ 0.05 after Bonferroni, in ≥3 of 4 window-pairs.

### Stage 8 — Persistence gate (Axiom 4.3)

**Change.** The gate is not a score at a window. It is the **persistence of ζ's advantage
across the filtration**: birth/death of the advantage over the window index, gated on lifespan.

**Why.** 4.3 — features persisting across many scales are robust structure; features that
appear and vanish are noise. This reads Finding 1 correctly *by definition*: a 38.5× advantage
alive at one window of three has persistence 1 and is noise. No ad-hoc ratio threshold needed.

**Decision it makes.** Does ζ's advantage persist, or is it a single-window artifact?

**Pass criterion.** Advantage lifespan ≥ ⌈W/2⌉ consecutive windows, with the barcode recorded.

### Stage 9 — Powered tournament

**Change.** Full arm set at M ≥ 59 instances, cold start, `tol=0`, exact enumerated rank tests,
Bonferroni across arms, convergence evidence per run (F at 25/50/75/100% of budget, last
improvement > 1e-4, best-of-r flatness).

**Why.** P4, and arithmetic. Two different floors apply and must not be conflated (see §7.1):

| framing | inferential unit | floor | at M=59 |
|---|---|---|---|
| Monte-Carlo: ζ (one fixed spectrum) vs M null **spectra** | spectrum | 1/(M+1) | 0.0167 |
| Two-sample rank: M ζ **restarts** vs M null restarts | optimizer path | 1/C(2M,M) | ~0 |

Only the first is a claim about spectra. Bonferroni-corrected 0.05 across 3 primary arms needs
`3/(M+1) ≤ 0.05`, hence **M ≥ 59**. Verified: M=19 gives 0.15 (insufficient), M=59 gives
exactly 0.0500.

**M means independent null spectra, not restarts.** For deterministic arms (`arith`,
`gram_points`, `rvm_smooth`, `geometric_desc`, `sorted_desc_gaps`) there is only ever **one**
spectrum, so M is undefined for them and no sampling p-value exists — they are handled as
existence results per §7.1. M ≥ 59 applies to the stochastic arms (`gue`, `goe_true`,
`poisson`, `scramble`), which are the ones a distributional claim can be made about.

**Arm set** (adversarial controls promoted to primary, per O3):
`zeta` · `arith` · `geometric_desc` · `sorted_desc_gaps` · `rvm_smooth` · `gram_points` ·
`scramble` · `gue` · `goe_true` · `poisson` · `dirichlet_L_zeros` · `davenport_heilbronn_zeros`

`rvm_smooth` and `gram_points` are the sharpest controls: identical counting density to ζ,
zero RH content. `davenport_heilbronn_zeros` violates RH — if the framework has any RH content
that arm must lose; if it wins or ties, the framework has none.

**Cost.** ~5.7 min/instance at 12,120 evals. 12 arms × 59 × 5.7 min ≈ 67 core-hours; ~11 h
wall-clock at 6 workers. Affordable, and resumable checkpointing already exists.

---

## 7. Pre-registered decision rules

### 7.1 Existence results vs distributional claims

L3 caught a conflation worth fixing before it propagates into the plan. The two classes of
claim here need different evidence, and only one of them needs a p-value.

**Existence claims need no p-value.** "There exists a zero-information spectrum this objective
prefers to ζ" is settled by exhibiting one. `arith` is a single fixed spectrum — 13 identical
gaps, every ordering the same object — so there is no population of `arith` spectra to sample
and no sampling distribution to test against. The 5/5 disjoint restarts do not make it
*significant*; they make it **reproducible**, which is the property that matters for an
existence claim. O3 is therefore a falsification by construction, and it stands independently
of any M.

**Distributional claims need M, and M counts spectra.** "ζ scores better than a GUE draw" is a
claim about a population, so it needs independent spectrum draws. Optimizer restarts are
**pseudoreplication** — they measure search-path variance, not spectrum variance, and using
them inflates apparent significance whenever the optimizer happens to be stable. The exact
rank p-values already reported (0.0040 etc.) are valid statements about optimizer-path
distributions and must be labelled as such; they are **not** evidence about spectra.

**Consequence for the plan.** Adversarial deterministic arms are graded pass/fail by existence.
Stochastic arms are graded distributionally at M ≥ 59. No artifact may report a single p-value
that mixes the two.



Fixed **before** running, so no outcome can be rationalized after the fact.

**Falsified — the framework has no ζ content:**
- Any adversarial arm reaches `F_best ≤ F_best(ζ)` after Sub-spec I, at converged equal budget; **or**
- `davenport_heilbronn_zeros` ties or beats ζ (it violates RH); **or**
- ζ's advantage persistence < ⌈W/2⌉ windows; **or**
- any `DEGENERATE_OBJECTIVE` stamp appears in a run used for a claim.

**Supported — jointly, and nothing less:**
- Every capability arm at `F_best ≥ 3 × F_best(ζ)` with zero degeneracy stamps; **and**
- ζ separates from correctly sampled `gue` at Bonferroni-corrected p ≤ 0.05 in ≥3 of 4 window-pairs; **and**
- advantage persistence ≥ ⌈W/2⌉ windows; **and**
- `rvm_smooth` and `gram_points` both lose (the signal is the zeros, not the counting function).

**Inconclusive** is a real outcome and must be reported as such. Given §1, it is the most
likely one.

## 8. Known limits that survive every stage

1. **The objective cannot see anything arithmetic.** The spectrum reaches the residual only
   through `omega_n` and `w_n`. After span- and density-matching that is ~12 reals of gap
   shape per window. No primes, no Euler product, no functional equation. If Stage 7 produces
   a win, the first hypothesis should be a **bug** — leakage, confound, sampler defect — not a
   discovery.
2. **ζ contributes exactly one spectrum per window.** Optimizer restarts are not replicates of
   the data; only windows are. The strongest defensible conclusion is about gap ordering in W
   specific real windows under this pre-registered pipeline. Nothing about L-functions
   generally, and nothing whatsoever about RH.
3. **No p-value computed on γ₁–γ₁₄ is calibrated**, because the search box was widened during
   the original ζ fitting. Window 1 is training data permanently.
4. **Sub-spec II may pass every stage and still be uninteresting** if what transfers is only
   spacing-distribution stationarity, which GUE shares.

## 9. Task ladder

Strictly ordered; Sub-spec I gates Sub-spec II (loop L3).

| # | Task | Axiom | Blocks |
|---|---|---|---|
| 1 | Disjoint-block lock baseline | 6.1 | 2 |
| 2 | Verify the four dead terms revive; delete any that don't | 6.1 | 6 |
| 3 | Window-invariant omega, anchored at the window-1 optimum | G5 | 6 |
| 4 | Degeneracy guard + reject path; must fire on the published champion | 6.2 | 6 |
| 5 | Component-vector reporting; retire static weights | 9.3 | — |
| 6 | Repair GUE sampler, add true GOE, delete extrapolation branch | — | 9 |
| 7 | Window filtration scoring, W ≥ 7 | 8.1, 4.2 | 8 |
| 8 | Cross-window rigidity statistic (Σ², Δ₃, pair correlation) | 8.2 | 9 |
| 9 | Persistence gate over the window barcode | 4.3 | 10 |
| 10 | Powered tournament, M ≥ 59, 12 arms | P4 | — |
| 11 | Report: falsified / supported / inconclusive per §7 | — | — |

## 10. L3 gate

This spec is a sheaf section over the stage cover. Restriction maps checked: every stage's
local spec is compatible with its neighbours' interfaces (Stage 1's baseline feeds Stage 2's
invariance test; Stage 3's guard consumes Stage 1's coincidence count; Stage 7's statistic
consumes Stage 6's filtration; Stage 8's barcode consumes Stage 7's per-window advantage).
No obstruction found on the overlaps.

**Human gate.** Awaiting approval before any implementation. The implementation plan follows
approval, not this document.
