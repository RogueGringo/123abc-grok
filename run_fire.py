#!/usr/bin/env python3
"""Set fire to the rain.

Full offensive stack:
  Coutsias algebraic roots → 3D holonomy twists → MaxOp/numpy sheaf Laplacian
  → honest zeta probes → prime-wave → GUE spacing → multi-N family scan
  → multi-panel fire figure + JSON manifesto.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("fire")

from realm import KinematicSpectralRealm, ZetaField
from realm.gue import pooled_gue
from realm.prime_wave import PrimeWaveProbe
from realm.sheaf_backend import CellularSheaf
from realm.waypoints import GeometryWaypoint, pairwise_waypoint_distance


def fire_primary(N: int = 11) -> dict:
    """Primary: geometry OFF the zeta field (correct direction)."""
    logger.info(
        "🔥 PRIMARY N=%d | geometry OFF zetas (not actual zeros) | MaxOp=%s",
        N,
        CellularSheaf is not None,
    )
    field = ZetaField.first(7)
    result = KinematicSpectralRealm(N=N, n_sectors=6, twist_source="gap_phases").analyze(field=field)

    class _G:
        def __init__(self, s):
            self.root_t = s.root_t
            self.residual = s.residual
            self.positions = s.positions
            self.holonomy_angle = s.holonomy_angle
            self.twist_so2 = s.twist

    class _S:
        def __init__(self, sp):
            self.state_id = sp.sector_id
            self.eigenvalues = sp.eigenvalues
            self.spectral_gap = sp.spectral_gap
            self.twist = sp.twist

    geoms = [_G(s) for s in result.sectors]
    states = [_S(sp) for sp in result.spectra]
    waypoints = [
        GeometryWaypoint(
            state_id=w.sector_id,
            backend=w.backend,
            epsilon_star=w.epsilon_star,
            waypoints=w.waypoints,
            derivative_values=w.derivative_values,
            gini_at_onset=w.gini_at_onset,
            gini_slope_at_onset=w.gini_slope_at_onset,
            vector=w.vector,
            n_points=N,
        )
        for w in result.waypoints
    ]
    wp_dist = pairwise_waypoint_distance(waypoints)
    gaps = result.gaps()
    wave = PrimeWaveProbe(n_primes=80).analyze(np.sort(gaps)) if gaps.size else None
    gue_pool = pooled_gue([s.eigenvalues for s in result.spectra])

    # Figure still expects a "reports" object with .observed for zeta panel —
    # reframe panel as induced twists vs seed gap phases (not λ=γ).
    class _Rep:
        def __init__(self):
            self.observed = result.twists()
            self.zeta_targets = field.gap_phases()[: len(self.observed)]
            if len(self.zeta_targets) < len(self.observed):
                self.zeta_targets = np.pad(
                    self.zeta_targets, (0, len(self.observed) - len(self.zeta_targets))
                )
            self.calibrated = self.observed  # identity: both are geometric angles
            self.raw_mean_error = float(np.mean(np.abs(self.observed - self.zeta_targets[: len(self.observed)])))
            self.calibrated_mean_error = self.raw_mean_error
            self.affine_scale = 1.0

        def verdict(self):
            return "geometry OFF zeta gaps (twists vs seed phases) — not λ=actual γ"

    reports = {"spectral_gap": _Rep()}  # key kept for plot wiring; meaning flipped

    return {
        "N": N,
        "backend_maxop": CellularSheaf is not None,
        "n_free": 0,
        "best_residual": 0.0,
        "roots": [s.root_t for s in result.sectors],
        "twists": result.twists().tolist(),
        "ontology": result.summary()["ontology"],
        "waypoints": [w.to_dict() for w in result.waypoints],
        "waypoint_distance_matrix": wp_dist.tolist(),
        "states": [sp.to_dict() for sp in result.spectra],
        "probes": [p.to_dict() for p in result.probes],
        "analysis_summary": result.summary(),
        "prime_wave": wave.to_dict() if wave else {},
        "gue_pooled": gue_pool.to_dict(),
        "_states_obj": states,
        "_geoms_obj": geoms,
        "_waypoints_obj": waypoints,
        "_wp_dist": wp_dist,
        "_reports_obj": reports,
        "_wave_obj": wave,
        "_gue_pool_obj": gue_pool,
        "_result": result,
    }


def plot_fire(primary: dict, family: list, path: Path) -> None:
    states = primary["_states_obj"]
    geoms = primary["_geoms_obj"]
    reports = primary["_reports_obj"]
    wave = primary["_wave_obj"]
    gue_pool = primary["_gue_pool_obj"]
    waypoints = primary.get("_waypoints_obj") or []
    wp_dist = primary.get("_wp_dist")

    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.38, wspace=0.32)

    # 0,0 — 3D closures projected to 2D
    ax = fig.add_subplot(gs[0, 0])
    colors = plt.cm.plasma(np.linspace(0.15, 0.85, max(len(geoms), 1)))
    for i, g in enumerate(geoms):
        p = g.positions
        ax.plot(p[:, 0], p[:, 1], "o-", color=colors[i], ms=3, label=f"t={g.root_t:.2f} r={g.residual:.2f}")
        ax.plot([p[-1, 0], p[0, 0]], [p[-1, 1], p[0, 1]], "--", color=colors[i], alpha=0.5)
    ax.set_title("Zeta-induced cyclic geometries (exact closure)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(fontsize=6)
    ax.grid(True, alpha=0.3)

    # 0,1 — spectra
    ax = fig.add_subplot(gs[0, 1])
    for i, s in enumerate(states):
        ax.plot(s.eigenvalues, "o-", ms=2, color=colors[i % len(colors)], label=f"S{s.state_id}")
    ax.set_title("Sheaf / connection Laplacian spectra")
    ax.set_xlabel("k")
    ax.set_ylabel("λ_k")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7)

    # 0,2 — twists induced from zeta gaps (geometry OFF field, not λ=γ)
    ax = fig.add_subplot(gs[0, 2])
    rep = reports["spectral_gap"]
    idx = np.arange(1, len(rep.observed) + 1)
    ax.plot(idx, rep.zeta_targets[: len(idx)], "k*-", lw=2, label="seed gap-phases (from γ)")
    ax.plot(idx, rep.observed, "ro--", label="induced monodromy twists")
    ax.set_title("Geometry OFF zeta gaps (not actual zeros)")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.text(
        0.02,
        0.98,
        f"{rep.verdict()[:70]}\nshape L1~{rep.raw_mean_error:.3g}",
        transform=ax.transAxes,
        va="top",
        fontsize=7,
        family="monospace",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.75),
    )

    # 1,0 — prime wave FFT
    ax = fig.add_subplot(gs[1, 0])
    if wave is not None and wave.geom_amps.size:
        ax.plot(wave.geom_freqs, wave.geom_amps, color="purple", lw=2, label="geom gaps")
    if wave is not None and wave.prime_amps.size and wave.geom_amps.size:
        scale = np.max(wave.geom_amps) / (np.max(wave.prime_amps) + 1e-12)
        ax.plot(wave.prime_freqs, wave.prime_amps * scale, color="gray", alpha=0.75, label="prime gaps")
    ks = getattr(wave, "gap_ks_distance", float("nan")) if wave else float("nan")
    ax.set_title(f"Prime-wave FFT (induced)  KS={ks:.3f}")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 1,1 — GUE spacings
    ax = fig.add_subplot(gs[1, 1])
    sp = gue_pool.spacings
    if sp.size:
        ax.hist(sp, bins=min(25, max(5, sp.size // 2)), density=True, alpha=0.65, color="#1f77b4", label="unfolded gaps")
        grid = np.linspace(0, max(4, float(sp.max())), 300)
        p = (32.0 / (np.pi**2)) * (grid**2) * np.exp(-4.0 * (grid**2) / np.pi)
        ax.plot(grid, p, "r-", lw=2, label="GUE Wigner")
        ax.plot(grid, np.exp(-grid), "k--", lw=1.5, label="Poisson")
    ax.set_title(f"GUE probe: {gue_pool.verdict()}")
    ax.set_xlabel("normalized spacing s")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 1,2 — holonomy vs spectral gap
    ax = fig.add_subplot(gs[1, 2])
    hol = [g.holonomy_angle for g in geoms]
    gap = [s.spectral_gap for s in states]
    ax.scatter(hol, gap, c=range(len(hol)), cmap="plasma", s=80, edgecolors="k")
    for i, g in enumerate(geoms):
        ax.annotate(f"t={g.root_t:.2f}", (hol[i], gap[i]), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("SO(3) holonomy angle")
    ax.set_ylabel("spectral gap λ₁")
    ax.set_title("Geometry holonomy → friction")
    ax.grid(True, alpha=0.3)

    # 2,0 — multi-N mean gap of induced geometries
    ax = fig.add_subplot(gs[2, 0])
    Ns = [f.N for f in family]
    means = [float(np.mean(f.gaps())) if len(f.spectra) else np.nan for f in family]
    ax.bar(Ns, means, color="#d62728", alpha=0.8, label="mean λ_gap (induced)")
    ax.set_xlabel("N (cycle size)")
    ax.set_ylabel("mean spectral gap")
    ax.set_title("Multi-N zeta-induced geometry")
    ax.grid(True, alpha=0.3)

    # 2,1 — MaxOp waypoint distance matrix W(C)
    ax = fig.add_subplot(gs[2, 1])
    if wp_dist is not None and getattr(wp_dist, "size", 0) and wp_dist.size:
        im = ax.imshow(wp_dist, cmap="magma")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        labels = [f"S{w.state_id}" for w in waypoints] if waypoints else None
        if labels:
            ax.set_xticks(range(len(labels)))
            ax.set_yticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=7)
            ax.set_yticklabels(labels, fontsize=7)
        backend = waypoints[0].backend if waypoints else "?"
        ax.set_title(f"MaxOp waypoint ‖W_i−W_j‖  ({backend})")
    else:
        ks_g = []
        for f in family:
            g = pooled_gue([s.eigenvalues for s in f.spectra])
            ks_g.append(g.ks_gue)
        ax.plot(Ns, ks_g, "r-o")
        ax.set_title("Family GUE KS (induced sheaf)")
        ax.grid(True, alpha=0.3)

    # 2,2 — manifesto text
    ax = fig.add_subplot(gs[2, 2])
    ax.axis("off")
    wp_backend = waypoints[0].backend if waypoints else "none"
    eps_list = [round(w.epsilon_star, 3) for w in waypoints] if waypoints else []
    lines = [
        "ONTOLOGY",
        "geometry OFF the zeta field",
        "NOT the actual zeros as eigenvalues",
        "",
        f"MaxOp sheaf: {primary['backend_maxop']}  W(C): {wp_backend}",
        f"N={primary['N']} induced sectors: {len(primary.get('twists') or [])}",
        f"ε* = {eps_list}",
        "",
    ]
    for pr in primary.get("probes") or []:
        lines.append(f"  {pr.get('name','?')}: {str(pr.get('verdict',''))[:40]}")
    lines += [
        "",
        f"PRIME-WAVE KS: {getattr(wave, 'gap_ks_distance', float('nan')):.4f}",
        f"GUE: {gue_pool.verdict()[:40]}",
    ]
    ax.text(
        0.02,
        0.98,
        "\n".join(lines),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=7.5,
        family="monospace",
        bbox=dict(boxstyle="round", facecolor="#1a1a2e", edgecolor="#e94560", alpha=0.92),
        color="#eee",
    )

    fig.suptitle(
        "GEOMETRY OFF THE ZETAS  ·  γ-seed → twists → C_N → sheaf L → W(C)  (not actual zeros)",
        fontsize=12,
        fontweight="bold",
        color="#e94560",
    )
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("Saved fire figure → %s", path)


def main() -> int:
    logger.info("======== SET FIRE TO THE RAIN ========")
    primary = fire_primary(N=11)

    logger.info("======== MULTI-N (zeta-induced geometry) ========")
    family = []
    for Nv in [7, 9, 11, 13, 15]:
        r = KinematicSpectralRealm(N=Nv, n_sectors=5, with_waypoints=False).analyze()
        family.append(r)

    out_fig = ROOT / "fire_the_rain.png"
    plot_fire(primary, family, out_fig)

    wp_list = primary.get("waypoints") or []
    manifesto = {
        "title": "geometry off the zeta field",
        "ontology": primary.get("ontology"),
        "primary": {k: v for k, v in primary.items() if not k.startswith("_")},
        "family": [f.summary() for f in family],
        "figure": str(out_fig.resolve()),
        "summary": {
            "ontology": primary.get("ontology"),
            "maxop_sheaf": primary["backend_maxop"],
            "waypoint_backend": wp_list[0]["backend"] if wp_list else None,
            "n_sectors": len(primary.get("twists") or []),
            "twists": primary.get("twists"),
            "epsilon_stars": [w["epsilon_star"] for w in wp_list],
            "probes": primary.get("probes"),
            "gue_pooled": primary["gue_pooled"].get("verdict"),
            "family_N": [f.N for f in family],
            "family_mean_gap": [float(np.mean(f.gaps())) for f in family],
        },
    }
    man_path = ROOT / "fire_manifesto.json"
    man_path.write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
    logger.info("Wrote %s", man_path)

    print("\n" + "=" * 60)
    print("SET FIRE TO THE RAIN — SUMMARY")
    print("=" * 60)
    print(json.dumps(manifesto["summary"], indent=2))
    print(f"\nFigure: {out_fig}")
    print(f"Manifesto: {man_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
