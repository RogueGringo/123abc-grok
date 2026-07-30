"""Sub-spec II Stage 9 — powered spectrum tournament on Stage 7/8 carriers.

Framing (design §7.1 / Stage 9): **one fixed ζ spectrum** vs M independent null
spectra. Floor p = 1/(M+1). M≥59 with Bonferroni across primary stochastic arms
gives adjusted α = 0.05 when n_arms=3.

Carriers (from Stage 8 signal):
- ``rigidity_delta3`` — mean Δ₃(L=5) across W windows (lower = more rigid)
- optional component series under G5 (expensive; opt-in)

Deterministic arms (arith, …) remain existence-only — no sampling p-value.

Does not modify dual-gate LengthPolicy. Never λ=γ.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from realm.validate.cross_window import (
    advantage_series,
    multi_carrier_persistence,
    persistence_barcode,
    score_rigidity_filtration,
)
from realm.validate.length_policy import policy_for


STOCHASTIC_ARMS = ("gue", "poisson", "scramble")
DETERMINISTIC_ARMS = ("arith",)


def monte_carlo_spectrum_p(
    zeta_score: float,
    null_scores: list[float] | np.ndarray,
    *,
    lower_is_better: bool = True,
) -> dict[str, Any]:
    """One-sided MC p: ζ better than null population (design floor 1/(M+1)).

    p = (1 + #{null as extreme as ζ}) / (M+1)
    """
    z = float(zeta_score)
    nuls = np.asarray(null_scores, dtype=float).ravel()
    nuls = nuls[np.isfinite(nuls)]
    M = int(nuls.size)
    if M == 0 or not np.isfinite(z):
        return {"M": M, "p": 1.0, "n_extreme": 0, "zeta": z, "null_mean": float("nan")}
    if lower_is_better:
        n_ext = int(np.sum(nuls <= z + 1e-15))
    else:
        n_ext = int(np.sum(nuls >= z - 1e-15))
    p = (1.0 + n_ext) / (M + 1.0)
    return {
        "M": M,
        "p": float(p),
        "n_extreme": n_ext,
        "zeta": z,
        "null_mean": float(np.mean(nuls)),
        "null_std": float(np.std(nuls)),
        "null_min": float(np.min(nuls)),
        "null_max": float(np.max(nuls)),
        "floor": 1.0 / (M + 1.0),
        "lower_is_better": lower_is_better,
    }


def bonferroni(p: float, n_tests: int) -> float:
    return float(min(1.0, float(p) * max(int(n_tests), 1)))


def rigidity_instance(arm: str, *, n_windows: int, n_zeros: int, seed: int) -> dict[str, Any]:
    """One spectrum instance → Stage 7 carrier summary."""
    out = score_rigidity_filtration(
        n_windows=n_windows,
        n_zeros=n_zeros,
        arm=arm,
        rng_seed=int(seed),
    )
    return {
        "arm": arm,
        "seed": int(seed),
        "carrier_mean": out["carrier_mean"],
        "carrier_series": out["carrier_series"],
        "W": out["W"],
    }


def run_rigidity_tournament(
    *,
    M: int = 59,
    n_windows: int = 7,
    n_zeros: int = 14,
    stochastic_arms: tuple[str, ...] = STOCHASTIC_ARMS,
    deterministic_arms: tuple[str, ...] = DETERMINISTIC_ARMS,
    base_seed: int = 0,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Stage 9 rigidity track: ζ vs M null spectra on Δ₃ carrier mean + persistence.

    For each null instance also records Stage 8 barcode of windowwise Δ₃ advantage.
    """
    M = int(M)
    W = int(n_windows)
    k = int(n_zeros)
    log = progress or (lambda _m: None)

    t0 = time.perf_counter()
    log(f"zeta rigidity W={W} k={k}")
    zeta = rigidity_instance("zeta", n_windows=W, n_zeros=k, seed=base_seed)
    zeta_score = float(zeta["carrier_mean"])
    zeta_series = list(zeta["carrier_series"])

    results: dict[str, Any] = {
        "stage": 9,
        "stage_name": "powered_rigidity_tournament",
        "M": M,
        "W": W,
        "n_zeros": k,
        "carrier": "delta3_L5_mean",
        "lower_is_better": True,
        "zeta": {
            "carrier_mean": zeta_score,
            "carrier_series": zeta_series,
        },
        "stochastic": {},
        "deterministic": {},
        "bonferroni_n_tests": len(stochastic_arms),
    }

    # Deterministic existence (one spectrum each)
    for arm in deterministic_arms:
        log(f"deterministic {arm}")
        inst = rigidity_instance(arm, n_windows=W, n_zeros=k, seed=base_seed)
        wins = advantage_series(
            zeta_series, inst["carrier_series"], lower_is_better=True
        )
        bc = persistence_barcode(wins)
        results["deterministic"][arm] = {
            "carrier_mean": inst["carrier_mean"],
            "zeta_better_mean": bool(zeta_score < float(inst["carrier_mean"])),
            "persistence": bc,
            "framing": "existence_one_spectrum",
        }

    # Stochastic arms (stable seed offsets — never hash(str))
    _ARM_OFF = {"gue": 10_000, "poisson": 20_000, "scramble": 30_000, "goe_true": 40_000}
    for arm in stochastic_arms:
        log(f"stochastic {arm} M={M}")
        scores: list[float] = []
        stage8_passes = 0
        max_lives: list[int] = []
        off = int(_ARM_OFF.get(arm, 50_000))
        for i in range(M):
            inst = rigidity_instance(
                arm, n_windows=W, n_zeros=k, seed=base_seed + off + i
            )
            scores.append(float(inst["carrier_mean"]))
            wins = advantage_series(
                zeta_series, inst["carrier_series"], lower_is_better=True
            )
            bc = persistence_barcode(wins)
            max_lives.append(int(bc["max_lifespan"]))
            if bc["stage8_pass"]:
                stage8_passes += 1
        mc = monte_carlo_spectrum_p(zeta_score, scores, lower_is_better=True)
        n_tests = len(stochastic_arms)
        p_adj = bonferroni(mc["p"], n_tests)
        # fraction of null instances where Stage 8 persists
        frac_s8 = stage8_passes / float(M)
        results["stochastic"][arm] = {
            "monte_carlo": mc,
            "p_bonferroni": p_adj,
            "significant_bonferroni_0.05": bool(p_adj <= 0.05),
            "stage8_pass_count": int(stage8_passes),
            "stage8_pass_fraction": float(frac_s8),
            "mean_max_lifespan": float(np.mean(max_lives)),
            "null_scores_head": scores[:10],
            "framing": "monte_carlo_one_zeta_vs_M_null_spectra",
        }
        log(
            f"  {arm}: p={mc['p']:.4f} p_adj={p_adj:.4f} s8_frac={frac_s8:.3f} "
            f"null_mean={mc['null_mean']:.5g}"
        )

    # Pass criterion design Stage 7: ζ separates from gue p≤0.05 after Bonferroni
    # in ≥3 of 4 window-pairs — we approximate with mean carrier MC + Stage8 fraction
    gue = results["stochastic"].get("gue", {})
    poisson = results["stochastic"].get("poisson", {})
    results["summary"] = {
        "zeta_beats_gue_bonferroni": bool(gue.get("significant_bonferroni_0.05")),
        "zeta_beats_poisson_bonferroni": bool(poisson.get("significant_bonferroni_0.05")),
        "gue_stage8_fraction": gue.get("stage8_pass_fraction"),
        "poisson_stage8_fraction": poisson.get("stage8_pass_fraction"),
        "elapsed_s": float(time.perf_counter() - t0),
        "dual_gate_soft_T_12": float(policy_for(12, base_beta=0.20).soft_T),
    }
    results["ontology"] = "stage9_rigidity_tournament_not_lambda_eq_gamma"
    results["note"] = (
        "Stage 9 rigidity track only (fast spectral stats). Component residual "
        "tournament is separate and expensive. Dual-gate LengthPolicy untouched. "
        "Never λ=γ."
    )
    return results


def save_tournament(result: dict[str, Any], path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return p


def run_component_tournament(
    knobs: dict[str, Any],
    *,
    M: int = 59,
    n_windows: int = 7,
    n_zeros: int = 14,
    N: int = 13,
    n_sectors: int = 6,
    carriers: tuple[str, ...] = ("stationarity", "density_return_l1", "corr_penalty"),
    stochastic_arms: tuple[str, ...] = ("gue", "poisson"),
    base_seed: int = 0,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Stage 9 residual-component track under G5 independent baseline.

    For each carrier: ζ mean across W windows vs M null spectra (one-sided MC p).
    Also Stage 8 windowwise persistence fraction of ζ advantage per null instance.

    Expensive relative to rigidity track (Keymaker forges per window).
    """
    from realm.validate.cross_window import score_arm_component_series
    from realm.validate.window_filtration import load_champion_knobs

    M = int(M)
    W = int(n_windows)
    log = progress or (lambda _m: None)
    kn = dict(knobs) if knobs else load_champion_knobs()
    t0 = time.perf_counter()

    log(f"zeta components W={W} carriers={carriers}")
    zeta = score_arm_component_series(
        kn,
        "zeta",
        n_windows=W,
        n_zeros=n_zeros,
        N=N,
        n_sectors=n_sectors,
        component_keys=carriers,
        use_g5_span=True,
        rng_seed=base_seed,
        skip_rigidity=True,
    )

    results: dict[str, Any] = {
        "stage": "9-component",
        "stage_name": "powered_component_tournament_g5",
        "M": M,
        "W": W,
        "n_zeros": int(n_zeros),
        "N": int(N),
        "n_sectors": int(n_sectors),
        "carriers": list(carriers),
        "lower_is_better": True,
        "use_g5_span": True,
        "omega_span": zeta.get("omega_span"),
        "zeta": {
            "means": zeta["means"],
            "series": zeta["series"],
            "guard_clear": zeta["guard_clear"],
        },
        "by_carrier": {},
        "bonferroni_n_tests": len(stochastic_arms) * len(carriers),
        "ontology": "stage9_component_tournament_g5_not_lambda_eq_gamma",
    }

    _ARM_OFF = {"gue": 100_000, "poisson": 200_000, "scramble": 300_000}
    n_tests = len(stochastic_arms) * len(carriers)

    for carrier in carriers:
        results["by_carrier"][carrier] = {
            "zeta_mean": float(zeta["means"][carrier]),
            "stochastic": {},
        }

    # One Keymaker pass per (arm, instance); all carriers filled together
    for arm in stochastic_arms:
        log(f"arm={arm} M={M} (all carriers)")
        off = int(_ARM_OFF.get(arm, 400_000))
        scores: dict[str, list[float]] = {c: [] for c in carriers}
        s8_count: dict[str, int] = {c: 0 for c in carriers}
        lives: dict[str, list[int]] = {c: [] for c in carriers}
        or_passes = 0
        for i in range(M):
            inst = score_arm_component_series(
                kn,
                arm,
                n_windows=W,
                n_zeros=n_zeros,
                N=N,
                n_sectors=n_sectors,
                component_keys=carriers,
                use_g5_span=True,
                omega_span=zeta.get("omega_span"),
                rng_seed=base_seed + off + i,
                skip_rigidity=True,
            )
            masks = {}
            for carrier in carriers:
                scores[carrier].append(float(inst["means"][carrier]))
                wins = advantage_series(
                    zeta["series"][carrier],
                    inst["series"][carrier],
                    lower_is_better=True,
                )
                bc = persistence_barcode(wins)
                lives[carrier].append(int(bc["max_lifespan"]))
                if bc["stage8_pass"]:
                    s8_count[carrier] += 1
                masks[carrier] = wins
            if multi_carrier_persistence(masks)["stage8_pass_or"]:
                or_passes += 1

        for carrier in carriers:
            mc = monte_carlo_spectrum_p(
                float(zeta["means"][carrier]),
                scores[carrier],
                lower_is_better=True,
            )
            p_adj = bonferroni(mc["p"], n_tests)
            results["by_carrier"][carrier]["stochastic"][arm] = {
                "monte_carlo": mc,
                "p_bonferroni": p_adj,
                "significant_bonferroni_0.05": bool(p_adj <= 0.05),
                "stage8_pass_count": int(s8_count[carrier]),
                "stage8_pass_fraction": float(s8_count[carrier]) / float(M),
                "mean_max_lifespan": float(np.mean(lives[carrier])),
                "null_scores_head": scores[carrier][:5],
            }
            log(
                f"  {carrier}/{arm}: p={mc['p']:.4f} p_adj={p_adj:.4f} "
                f"s8={s8_count[carrier] / M:.3f} null_mean={mc['null_mean']:.5g}"
            )
        results[f"multi_carrier_or_vs_{arm}"] = {
            "stage8_or_pass_fraction": float(or_passes) / float(M),
            "M": M,
        }

    results["summary"] = {
        "elapsed_s": float(time.perf_counter() - t0),
        "dual_gate_soft_T_12": float(policy_for(12, base_beta=0.20).soft_T),
        "n_bonferroni_tests": n_tests,
        "any_significant": any(
            results["by_carrier"][c]["stochastic"][a].get("significant_bonferroni_0.05")
            for c in carriers
            for a in stochastic_arms
        ),
    }
    results["note"] = (
        "Stage 9 component track under G5 independent baseline. "
        "Bonferroni over |arms|×|carriers|. Dual-gate LengthPolicy untouched. Never λ=γ."
    )
    return results
