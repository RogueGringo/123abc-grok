"""Adaptive evolutionary policy — natural selection on dual fitness.

4D-selection framing (AXiomZ-compatible, never λ=γ)
----------------------------------------------------
  Genotype   : SpectralAction knobs (Λ, ω_s, w_p, tier, boost, w1–3)
  Phenotype  : Crit molds → R³ projection (+ MaxOp dual diagnostics)
  Environment: cyclic native-vs-decoy ranking (probe set only in selection)
  Dual fitness:
    F_int  — informative residual + occupancy (internal seal)
    F_ext  — 1 − probe_enrichment (+ soft floor on weak mid-length IDs)
  Adaptive policy (mutation temperature τ):
    · shrink τ when elite improves (exploitation / niche lock)
    · expand τ on plateau (exploration / adaptive radiation)
    · tournament + elitism = survival of the fittest under environment

Ontology: ζ is substrate seed only. Selection optimizes *projection*
phenotype fitness, not numerical identity with zeros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from realm.score_worker import score_vec, vec_to_knobs
from realm.validate.harness import score_configuration


# Canonical 8D knob bounds (same as evolve.py)
KNOB_BOUNDS: list[tuple[float, float]] = [
    (0.35, 4.5),   # Lambda / g_last
    (0.35, 2.9),   # omega_scale
    (0.35, 2.9),   # weight_power
    (0.12, 0.80),  # tier_split
    (0.5, 3.8),    # low_boost
    (0.80, 1.20),  # w1
    (0.80, 1.20),  # w2
    (0.80, 1.20),  # w3
]


def knobs_to_vec(knobs: dict[str, float], g_last: float) -> np.ndarray:
    return np.array(
        [
            float(knobs["Lambda"]) / float(g_last),
            float(knobs.get("omega_scale", 1.0)),
            float(knobs.get("weight_power", 1.0)),
            float(knobs.get("tier_split", 0.45)),
            float(knobs.get("low_boost", 1.0)),
            float(knobs.get("w1_mult", 1.0)),
            float(knobs.get("w2_mult", 1.0)),
            float(knobs.get("w3_mult", 1.0)),
        ],
        dtype=float,
    )


def clip_vec(x: np.ndarray, bounds: list[tuple[float, float]] | None = None) -> np.ndarray:
    b = bounds or KNOB_BOUNDS
    out = np.asarray(x, dtype=float).copy()
    for i, (lo, hi) in enumerate(b):
        out[i] = float(np.clip(out[i], lo, hi))
    return out


@dataclass
class Individual:
    """One organism in the selection population."""

    vec: np.ndarray
    knobs: dict[str, float]
    F_int: float = 9.9
    R: float = 9.9
    occupancy: float = 0.0
    n_keys: int = 0
    n_valleys: int = 0
    F_ext: float = 1.0
    probe_enrichment: float = 0.0
    floor_enrichment: float | None = None
    F_total: float = 9.9
    generation: int = 0
    lineage: str = "founder"

    def to_dict(self) -> dict[str, Any]:
        return {
            "knobs": self.knobs,
            "F_int": self.F_int,
            "R": self.R,
            "occupancy": self.occupancy,
            "n_keys": self.n_keys,
            "n_valleys": self.n_valleys,
            "F_ext": self.F_ext,
            "probe_enrichment": self.probe_enrichment,
            "floor_enrichment": self.floor_enrichment,
            "F_total": self.F_total,
            "generation": self.generation,
            "lineage": self.lineage,
        }


@dataclass
class AdaptivePolicy:
    """Mutation temperature + selection hyperparameters (4D adaptive rates)."""

    tau: float = 0.08  # mutation scale
    tau_min: float = 0.015
    tau_max: float = 0.28
    improve_shrink: float = 0.82
    plateau_expand: float = 1.18
    plateau_patience: int = 2
    elite_k: int = 2
    tournament_k: int = 3
    crossover_rate: float = 0.45
    w_int: float = 0.35
    w_ext: float = 0.55
    w_floor: float = 0.10
    r_soft_cap: float = 0.015
    plateau_streak: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def on_epoch(self, improved: bool, best_F: float, mean_F: float) -> None:
        if improved:
            self.tau = max(self.tau_min, self.tau * self.improve_shrink)
            self.plateau_streak = 0
        else:
            self.plateau_streak += 1
            if self.plateau_streak >= self.plateau_patience:
                self.tau = min(self.tau_max, self.tau * self.plateau_expand)
        self.history.append(
            {
                "tau": self.tau,
                "improved": improved,
                "best_F": best_F,
                "mean_F": mean_F,
                "plateau_streak": self.plateau_streak,
            }
        )


def score_internal(
    vec: np.ndarray,
    *,
    N: int,
    n_zeros: int,
    n_sectors: int,
    g_last: float,
    n_target: int,
) -> dict[str, Any]:
    return score_vec(
        vec,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        g_last=g_last,
        n_target=n_target,
    )


def combine_fitness(
    F_int: float,
    R: float,
    probe_enrichment: float,
    floor_enrichment: float | None,
    policy: AdaptivePolicy,
) -> tuple[float, float]:
    """Return (F_total, F_ext). Lower is better."""
    F_ext = 1.0 - float(probe_enrichment)
    if floor_enrichment is not None:
        F_ext = (
            (1.0 - policy.w_floor) * F_ext
            + policy.w_floor * (1.0 - float(floor_enrichment))
        )
    # Soft barrier if seal residual drifts above cap
    barrier = max(0.0, float(R) - policy.r_soft_cap) * 4.0
    F_total = (
        policy.w_int * float(F_int)
        + policy.w_ext * F_ext
        + barrier
    )
    return float(F_total), float(F_ext)


def mutate(
    parent: np.ndarray,
    tau: float,
    rng: np.random.Generator,
    bounds: list[tuple[float, float]] | None = None,
    *,
    ir_focus: bool = False,
) -> np.ndarray:
    """Mutate genotype. ir_focus=True → microevolution on IR mults / boost only."""
    b = bounds or KNOB_BOUNDS
    n = len(b)
    # anisotropic: IR mults (last 3) mutate harder — phenotype micro-sculpture
    scale = np.ones(n, dtype=float) * tau
    if n >= 8:
        scale[5:] = tau * 1.6
        scale[0] = tau * 0.7  # Λ coarser
    if ir_focus and n >= 8:
        # protect bulk SpectralAction when seal already tight
        scale[:3] = tau * 0.15
        scale[3:5] = tau * 0.55
        scale[5:] = tau * 1.8
    noise = rng.normal(0.0, 1.0, size=n) * scale
    # occasional large jump (saltation) — rarer under ir_focus
    salt_p = 0.04 if ir_focus else 0.08
    if rng.random() < salt_p:
        axis = int(rng.integers(5, n)) if (ir_focus and n >= 8) else int(rng.integers(0, n))
        noise[axis] += rng.choice([-1.0, 1.0]) * tau * 3.0
    return clip_vec(parent + noise, b)


def crossover(
    a: np.ndarray,
    b: np.ndarray,
    rng: np.random.Generator,
    rate: float,
    bounds: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    if rng.random() > rate:
        return a.copy()
    mask = rng.random(a.size) < 0.5
    child = np.where(mask, a, b)
    # blend on one random axis
    i = int(rng.integers(0, a.size))
    alpha = float(rng.uniform(0.25, 0.75))
    child[i] = alpha * a[i] + (1.0 - alpha) * b[i]
    return clip_vec(child, bounds)


def tournament_select(
    pop: list[Individual],
    k: int,
    rng: np.random.Generator,
) -> Individual:
    k = min(k, len(pop))
    idxs = rng.choice(len(pop), size=k, replace=False)
    contenders = [pop[i] for i in idxs]
    return min(contenders, key=lambda ind: ind.F_total)


def init_population(
    founder_vec: np.ndarray,
    n_pop: int,
    tau: float,
    rng: np.random.Generator,
    g_last: float,
    *,
    ir_focus: bool = False,
) -> list[np.ndarray]:
    pop = [clip_vec(founder_vec)]
    for i in range(n_pop - 1):
        scale = tau * (0.6 + 0.5 * (i % 5))
        pop.append(mutate(founder_vec, scale, rng, ir_focus=ir_focus))
    return pop


def evaluate_individual(
    vec: np.ndarray,
    *,
    g_last: float,
    N: int,
    n_zeros: int,
    n_sectors: int,
    n_target: int,
    policy: AdaptivePolicy,
    probe_fn: Callable[[dict[str, float]], tuple[float, float | None]],
    generation: int,
    lineage: str,
) -> Individual:
    sc = score_internal(
        vec,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        g_last=g_last,
        n_target=n_target,
    )
    kn = sc.get("knobs") or vec_to_knobs(vec, g_last)
    probe_enr, floor_enr = probe_fn(kn)
    F_total, F_ext = combine_fitness(
        float(sc.get("F", 9.9)),
        float(sc.get("R", 9.9)),
        probe_enr,
        floor_enr,
        policy,
    )
    return Individual(
        vec=np.asarray(vec, float),
        knobs=kn,
        F_int=float(sc.get("F", 9.9)),
        R=float(sc.get("R", 9.9)),
        occupancy=float(sc.get("occupancy", 0.0)),
        n_keys=int(sc.get("n_keys", 0)),
        n_valleys=int(sc.get("n_valleys", 0)),
        F_ext=F_ext,
        probe_enrichment=float(probe_enr),
        floor_enrichment=floor_enr,
        F_total=F_total,
        generation=generation,
        lineage=lineage,
    )


def run_natural_selection(
    founder_knobs: dict[str, float],
    *,
    g_last: float,
    N: int = 13,
    n_zeros: int = 14,
    n_sectors: int = 6,
    n_pop: int = 8,
    n_epochs: int = 6,
    policy: AdaptivePolicy | None = None,
    probe_fn: Callable[[dict[str, float]], tuple[float, float | None]],
    rng: np.random.Generator | None = None,
    log: Callable[[str], None] | None = None,
    ir_focus: bool = True,
) -> dict[str, Any]:
    """Multi-epoch population loop with adaptive mutation temperature.

    probe_fn(knobs) → (mean_probe_enrichment, optional_floor_enrichment)
    ir_focus: when True, mutate IR mults preferentially (sealed-niche microevolution).
    """
    policy = policy or AdaptivePolicy()
    rng = rng or np.random.default_rng(42)
    log = log or (lambda m: None)
    n_target = n_sectors

    founder_vec = knobs_to_vec(founder_knobs, g_last)
    vecs = init_population(
        founder_vec, n_pop, policy.tau, rng, g_last, ir_focus=ir_focus
    )

    population: list[Individual] = []
    for i, v in enumerate(vecs):
        lineage = "founder" if i == 0 else f"mutant0_{i}"
        ind = evaluate_individual(
            v,
            g_last=g_last,
            N=N,
            n_zeros=n_zeros,
            n_sectors=n_sectors,
            n_target=n_target,
            policy=policy,
            probe_fn=probe_fn,
            generation=0,
            lineage=lineage,
        )
        population.append(ind)
        log(
            f"  init[{i}] F_tot={ind.F_total:.4f} F_int={ind.F_int:.4f} "
            f"enr={ind.probe_enrichment:.1%} R={ind.R:.4f} τ={policy.tau:.3f}"
        )

    elite = min(population, key=lambda ind: ind.F_total)
    epoch_log: list[dict[str, Any]] = []
    best_ever = elite

    for epoch in range(1, n_epochs + 1):
        # --- selection + variation ---
        population.sort(key=lambda ind: ind.F_total)
        elites = population[: policy.elite_k]
        next_gen: list[Individual] = list(elites)  # elitism
        next_vecs: list[tuple[np.ndarray, str]] = []

        while len(next_vecs) + len(next_gen) < n_pop:
            p1 = tournament_select(population, policy.tournament_k, rng)
            p2 = tournament_select(population, policy.tournament_k, rng)
            child = crossover(p1.vec, p2.vec, rng, policy.crossover_rate)
            child = mutate(child, policy.tau, rng, ir_focus=ir_focus)
            next_vecs.append((child, f"e{epoch}_x_{p1.lineage[:8]}"))

        for v, lin in next_vecs:
            ind = evaluate_individual(
                v,
                g_last=g_last,
                N=N,
                n_zeros=n_zeros,
                n_sectors=n_sectors,
                n_target=n_target,
                policy=policy,
                probe_fn=probe_fn,
                generation=epoch,
                lineage=lin,
            )
            next_gen.append(ind)

        population = next_gen
        population.sort(key=lambda ind: ind.F_total)
        epoch_best = population[0]
        mean_F = float(np.mean([ind.F_total for ind in population]))
        improved = epoch_best.F_total < best_ever.F_total - 1e-6
        if improved:
            best_ever = epoch_best
        policy.on_epoch(improved, epoch_best.F_total, mean_F)

        snap = {
            "epoch": epoch,
            "best_F_total": epoch_best.F_total,
            "best_probe_enrichment": epoch_best.probe_enrichment,
            "best_R": epoch_best.R,
            "best_F_int": epoch_best.F_int,
            "mean_F_total": mean_F,
            "tau": policy.tau,
            "improved": improved,
            "elite_knobs": epoch_best.knobs,
        }
        epoch_log.append(snap)
        log(
            f"  epoch {epoch}/{n_epochs}  best F_tot={epoch_best.F_total:.4f} "
            f"enr={epoch_best.probe_enrichment:.1%} R={epoch_best.R:.4f} "
            f"meanF={mean_F:.4f} τ={policy.tau:.3f} "
            f"{'↑ improve' if improved else '— plateau'}"
        )

    # Final seal diagnostics on champion
    seal = score_configuration(
        kind="zeta",
        knobs=best_ever.knobs,
        N=N,
        n_zeros=n_zeros,
        n_sectors=n_sectors,
        rng_seed=0,
    )

    return {
        "champion": best_ever.to_dict(),
        "founder_knobs": founder_knobs,
        "epochs": epoch_log,
        "policy": {
            "final_tau": policy.tau,
            "tau_history": policy.history,
            "w_int": policy.w_int,
            "w_ext": policy.w_ext,
            "w_floor": policy.w_floor,
            "elite_k": policy.elite_k,
            "n_pop": n_pop,
            "n_epochs": n_epochs,
        },
        "seal": {
            "R": seal.get("R"),
            "occupancy": seal.get("occupancy"),
            "n_keys": seal.get("n_keys"),
            "n_valleys": seal.get("n_valleys"),
        },
        "ontology": (
            "adaptive_natural_selection_projection_phenotype; "
            "zeta_substrate_seed_only; never_lambda_eq_gamma"
        ),
        "framing": {
            "genotype": "SpectralAction knobs",
            "phenotype": "Crit→geometry projection ranking",
            "environment": "probe cyclic native-vs-decoy enrichment",
            "adaptive_policy": "mutation temperature τ shrink/expand on improve/plateau",
            "dimensionality": "8D genotype + dual fitness landscape (int×ext)",
            "ir_focus": bool(ir_focus),
        },
    }
