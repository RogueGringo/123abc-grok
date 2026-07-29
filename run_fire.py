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

from realm.coutsias import CoutsiasKinematics
from realm.gue import analyze_spectrum_gue, gue_wigner_surmise_cdf, pooled_gue
from realm.pipeline import RealmPipeline
from realm.prime_wave import PrimeWaveProbe
from realm.scan import MultiNScan
from realm.sheaf_backend import CellularSheaf
from realm.zeta_probe import ZetaProbe


def fire_primary(N: int = 11) -> dict:
    """Primary cyclosporin-like N: algebraic roots + geometric holonomy → full probes."""
    logger.info("🔥 PRIMARY N=%d  |  MaxOp=%s", N, CellularSheaf is not None)
    kin = CoutsiasKinematics(N=N, residual_tol=0.55)
    geoms = kin.find_real_roots()
    if len(geoms) < 2:
        kin.residual_tol = 1.0
        geoms = kin.find_real_roots()
    geoms = geoms[:6]
    roots = [g.root_t for g in geoms]
    twists = [g.twist_so2 for g in geoms]

    from realm.cohesive import CohesiveHomotopyFunctor

    functor = CohesiveHomotopyFunctor(N=N, d=2)
    states = []
    for i, (r, th, g) in enumerate(zip(roots, twists, geoms)):
        states.append(
            functor.evaluate_state_from_twist(
                i + 1,
                r,
                th,
                prefer_maxop=True,
                geometry_meta={
                    "holonomy_angle": g.holonomy_angle,
                    "position_error": g.position_error,
                    "residual": g.residual,
                },
            )
        )

    gaps = np.array([s.spectral_gap for s in states], dtype=float)
    frust = np.array([s.frustration_closed_form for s in states], dtype=float)
    zeta = ZetaProbe()
    reports = {
        "spectral_gap": zeta.probe(gaps, "spectral_gap"),
        "gap_ladder": zeta.probe(np.sort(gaps), "gap_ladder"),
        "frustration": zeta.probe(frust, "frustration"),
    }
    wave = PrimeWaveProbe(n_primes=80).analyze(np.sort(gaps))
    gue_each = [analyze_spectrum_gue(s.eigenvalues) for s in states]
    gue_pool = pooled_gue([s.eigenvalues for s in states])

    return {
        "N": N,
        "backend_maxop": CellularSheaf is not None,
        "roots": roots,
        "twists": twists,
        "geometries": [g.to_dict() for g in geoms],
        "states": [s.to_dict() for s in states],
        "zeta": {k: v.to_dict() for k, v in reports.items()},
        "prime_wave": wave.to_dict(),
        "gue_each": [g.to_dict() for g in gue_each],
        "gue_pooled": gue_pool.to_dict(),
        "_states_obj": states,
        "_geoms_obj": geoms,
        "_reports_obj": reports,
        "_wave_obj": wave,
        "_gue_pool_obj": gue_pool,
        "_gue_each_obj": gue_each,
    }


def plot_fire(primary: dict, family: list, path: Path) -> None:
    states = primary["_states_obj"]
    geoms = primary["_geoms_obj"]
    reports = primary["_reports_obj"]
    wave = primary["_wave_obj"]
    gue_pool = primary["_gue_pool_obj"]

    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.38, wspace=0.32)

    # 0,0 — 3D closures projected to 2D
    ax = fig.add_subplot(gs[0, 0])
    colors = plt.cm.plasma(np.linspace(0.15, 0.85, max(len(geoms), 1)))
    for i, g in enumerate(geoms):
        p = g.positions
        ax.plot(p[:, 0], p[:, 1], "o-", color=colors[i], ms=3, label=f"t={g.root_t:.3f}")
        ax.plot([p[-1, 0], p[0, 0]], [p[-1, 1], p[0, 1]], "--", color=colors[i], alpha=0.5)
    ax.set_title("Coutsias 3D closures (xy projection)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(fontsize=7)
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

    # 0,2 — zeta honest
    ax = fig.add_subplot(gs[0, 2])
    rep = reports["spectral_gap"]
    idx = np.arange(1, len(rep.observed) + 1)
    ax.plot(idx, rep.zeta_targets, "k*-", lw=2, label="γ_n")
    ax.plot(idx, rep.observed, "ro--", label="raw λ_gap")
    ax.plot(idx, rep.calibrated, "bs--", label="affine aλ+b")
    ax.set_title("Honest ζ correspondence")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.text(
        0.02,
        0.98,
        f"{rep.verdict()[:60]}…\nraw={rep.raw_mean_error:.3g} cal={rep.calibrated_mean_error:.3g}",
        transform=ax.transAxes,
        va="top",
        fontsize=7,
        family="monospace",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.75),
    )

    # 1,0 — prime wave FFT
    ax = fig.add_subplot(gs[1, 0])
    if wave.geom_amps.size:
        ax.plot(wave.geom_freqs, wave.geom_amps, color="purple", lw=2, label="geom gaps")
    if wave.prime_amps.size and wave.geom_amps.size:
        scale = np.max(wave.geom_amps) / (np.max(wave.prime_amps) + 1e-12)
        ax.plot(wave.prime_freqs, wave.prime_amps * scale, color="gray", alpha=0.75, label="prime gaps")
    ax.set_title(f"Prime-wave FFT  KS={wave.gap_ks_distance:.3f}")
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

    # 2,0 — multi-N mean gap
    ax = fig.add_subplot(gs[2, 0])
    Ns = [f.N for f in family]
    means = [f.mean_gap for f in family]
    nroots = [f.n_roots for f in family]
    ax.bar(Ns, means, color="#d62728", alpha=0.8, label="mean λ_gap")
    ax.set_xlabel("N (cycle size)")
    ax.set_ylabel("mean spectral gap")
    ax.set_title("Multi-N family scan")
    ax2 = ax.twinx()
    ax2.plot(Ns, nroots, "ko-", label="# algebraic roots")
    ax2.set_ylabel("# roots")
    ax.grid(True, alpha=0.3)

    # 2,1 — multi-N GUE KS
    ax = fig.add_subplot(gs[2, 1])
    ks_g, ks_p = [], []
    for f in family:
        if f.gue_pooled:
            ks_g.append(f.gue_pooled.ks_gue)
            ks_p.append(f.gue_pooled.ks_poisson)
        else:
            ks_g.append(np.nan)
            ks_p.append(np.nan)
    ax.plot(Ns, ks_g, "r-o", label="KS → GUE")
    ax.plot(Ns, ks_p, "k--s", label="KS → Poisson")
    ax.set_xlabel("N")
    ax.set_ylabel("KS distance")
    ax.set_title("Family RMT: GUE vs Poisson")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 2,2 — manifesto text
    ax = fig.add_subplot(gs[2, 2])
    ax.axis("off")
    lines = [
        "FIRE MANIFESTO",
        f"MaxOp sheaf backend: {primary['backend_maxop']}",
        f"N={primary['N']} algebraic roots: {len(primary['roots'])}",
        f"roots t = {[round(r,4) for r in primary['roots']]}",
        "",
        "ZETA:",
    ]
    for name, rep in reports.items():
        lines.append(f"  {name}: {rep.verdict()[:48]}")
    lines += [
        "",
        f"PRIME-WAVE KS: {wave.gap_ks_distance:.4f}",
        f"GUE POOLED: {gue_pool.verdict()}",
        f"  KS_GUE={gue_pool.ks_gue:.4f}  KS_Pois={gue_pool.ks_poisson:.4f}",
        "",
        "Twists from 3D holonomy — not r·π fantasy.",
        "No hardcoded λ≈γ. Resonance must be earned.",
    ]
    ax.text(
        0.02,
        0.98,
        "\n".join(lines),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=8,
        family="monospace",
        bbox=dict(boxstyle="round", facecolor="#1a1a2e", edgecolor="#e94560", alpha=0.92),
        color="#eee",
    )

    fig.suptitle(
        "SET FIRE TO THE RAIN  ·  Coutsias → Holonomy → Sheaf L → ζ / primes / GUE",
        fontsize=14,
        fontweight="bold",
        color="#e94560",
    )
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("Saved fire figure → %s", path)


def main() -> int:
    logger.info("======== SET FIRE TO THE RAIN ========")
    primary = fire_primary(N=11)

    logger.info("======== MULTI-N FAMILY SCAN ========")
    scan = MultiNScan(N_values=[7, 9, 11, 13, 15], residual_tol=0.6)
    family = scan.run()

    out_fig = ROOT / "fire_the_rain.png"
    plot_fire(primary, family, out_fig)

    # JSON without private object keys
    manifesto = {
        "title": "set fire to the rain",
        "primary": {k: v for k, v in primary.items() if not k.startswith("_")},
        "family": [f.to_dict() for f in family],
        "figure": str(out_fig.resolve()),
        "summary": {
            "maxop": primary["backend_maxop"],
            "n_roots_N11": len(primary["roots"]),
            "zeta_verdicts": {k: primary["zeta"][k]["verdict"] for k in primary["zeta"]},
            "gue_pooled": primary["gue_pooled"]["verdict"],
            "prime_wave_ks": primary["prime_wave"]["gap_ks_distance"],
            "family_N": [f.N for f in family],
            "family_n_roots": [f.n_roots for f in family],
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
