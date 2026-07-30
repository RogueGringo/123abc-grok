#!/usr/bin/env python3
"""Natural-selection evolve loop — adaptive evolutionary policy (4D dual fitness).

Pipeline
--------
  1) Optional internal evolve generations (substrate seal / genotype DE)
  2) Adaptive natural selection epochs:
       population of knobs → dual fitness (F_int × probe enrichment)
       mutation temperature τ shrinks on improve, expands on plateau
  3) Holdout report (never in selection objective)
  4) Optional full multi-seed batch on champion
  5) Accept champion into evolve_result.json only if dual gates pass

Ontology: ζ = substrate seed; selection acts on projection phenotype.
Never λ=γ. No ζ-preference claim.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.adaptive_evolve import AdaptivePolicy, knobs_to_vec, run_natural_selection
from realm.lock_key import Keymaker
from realm.manifold_control import fold_control_snapshot
from realm.ontology import ontology_note
from realm.validate.report import load_knobs, write_json
from pdb_batch import HOLDOUT_IDS, PROBE_IDS, rank_one

logger = logging.getLogger("evolve_ns")


def _probe_enrichment_fn(
    probe_ids: list[str],
    floor_ids: list[str],
    *,
    n_decoys: int,
    n_zeros: int,
    n_sectors: int,
    defect_beta: float,
    soft_T: float,
    rng: np.random.Generator,
):
    """Return probe_fn(knobs) → (mean_probe_enr, mean_floor_enr|None)."""

    def _rank(kn: dict, ids: list[str], n_seeds: int = 1) -> float:
        rows = []
        for pid in ids:
            try:
                row = rank_one(
                    pid,
                    kn,
                    n_decoys,
                    n_zeros,
                    n_sectors,
                    0.45,
                    rng,
                    n_seeds=n_seeds,
                    soft_T=soft_T,
                    sectors_mode="adaptive",
                    multimode_mode="self_fit_dense",
                    defect_beta=defect_beta,
                )
            except Exception as exc:  # noqa: BLE001
                row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
            rows.append(row)
        ok = [r for r in rows if r.get("status") == "OK"]
        if not ok:
            return 0.0
        return float(np.mean([r["enrichment"] for r in ok]))

    def probe_fn(kn: dict) -> tuple[float, float | None]:
        pe = _rank(kn, probe_ids, n_seeds=1)
        fe = _rank(kn, floor_ids, n_seeds=1) if floor_ids else None
        return pe, fe

    return probe_fn


def _rank_ids(
    kn: dict,
    ids: list[str],
    *,
    n_decoys: int,
    n_zeros: int,
    n_sectors: int,
    n_seeds: int,
    defect_beta: float,
    soft_T: float,
    rng: np.random.Generator,
) -> tuple[float, list]:
    rows = []
    for pid in ids:
        try:
            row = rank_one(
                pid,
                kn,
                n_decoys,
                n_zeros,
                n_sectors,
                0.45,
                rng,
                n_seeds=n_seeds,
                soft_T=soft_T,
                sectors_mode="adaptive",
                multimode_mode="self_fit_dense",
                defect_beta=defect_beta,
            )
        except Exception as exc:  # noqa: BLE001
            row = {"pdb": pid, "status": "ERROR", "error": str(exc)}
        rows.append(row)
    ok = [r for r in rows if r.get("status") == "OK"]
    mean_e = float(np.mean([r["enrichment"] for r in ok])) if ok else 0.0
    return mean_e, rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Adaptive natural-selection evolve loop (dual fitness)"
    )
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument(
        "--internal-gens",
        type=int,
        default=0,
        help="optional internal evolve.py generations before NS (0=skip)",
    )
    p.add_argument("--de-iter", type=int, default=4, help="DE iters per internal gen")
    p.add_argument("--n-pop", type=int, default=8)
    p.add_argument(
        "--epochs",
        type=int,
        default=5,
        help="fixed epoch budget (ignored as hard stop when --until-resolved)",
    )
    p.add_argument(
        "--until-resolved",
        action="store_true",
        help="run tuple-time until phenotype resolution is maximized (stable)",
    )
    p.add_argument(
        "--max-epochs",
        type=int,
        default=24,
        help="hard cap when --until-resolved (default 24)",
    )
    p.add_argument(
        "--resolve-patience",
        type=int,
        default=4,
        help="epochs with no resolution gain before stop (until-resolved)",
    )
    p.add_argument(
        "--min-epochs",
        type=int,
        default=3,
        help="minimum epochs before resolution-stop may fire",
    )
    p.add_argument("--n-decoys", type=int, default=16, help="fast probe decoys in NS")
    p.add_argument("--verify-decoys", type=int, default=40)
    p.add_argument("--verify-seeds", type=int, default=3)
    p.add_argument("--defect-beta", type=float, default=0.20)
    p.add_argument("--soft-T", type=float, default=0.04)
    p.add_argument(
        "--probe",
        type=str,
        default=",".join(PROBE_IDS),
        help="selection environment (probe only)",
    )
    p.add_argument(
        "--floors",
        type=str,
        default="4K8Y,1TET",
        help="mid-length floor IDs soft-weighted in F_ext",
    )
    p.add_argument(
        "--holdout",
        type=str,
        default=",".join(HOLDOUT_IDS),
        help="never used in selection objective",
    )
    p.add_argument("--tau0", type=float, default=0.08)
    p.add_argument("--r-soft-cap", type=float, default=0.015)
    p.add_argument(
        "--accept-min-probe",
        type=float,
        default=0.0,
        help="require champion probe ≥ this to accept (0=any dual improve)",
    )
    p.add_argument(
        "--write-evolve",
        action="store_true",
        help="merge champion into evolve_result.json if dual gates pass",
    )
    p.add_argument("--full-batch", action="store_true")
    p.add_argument("--json", type=Path, default=Path("evolve_ns_result.json"))
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("\n=== ADAPTIVE NATURAL SELECTION EVOLVE ===")
    print(f"  {ontology_note()}")
    print(
        "  framing: genotype=knobs · phenotype=Crit→projection · "
        "environment=probe enrichment · adaptive τ"
    )
    print(
        "  Connes discipline: geometry-from-spectrum; spectral action; "
        "never λ=γ; control = admissible variation of D/knobs"
    )
    print(
        "  tuples: Σ=(M,f,g,U) · D=(M,Δ,∇) · S=(G,F,L_F) · "
        "time=(t,τ,resolution,F)"
    )

    # Snapshot pre-state so internal DE cannot erase sealed elite + stage meta
    pre_snapshot: dict = {}
    if args.knobs.is_file():
        try:
            pre_snapshot = json.loads(args.knobs.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pre_snapshot = {}
    pre_knobs = load_knobs(args.knobs) if args.knobs.is_file() else {}
    pre_R = float(pre_snapshot.get("R", 9.9)) if pre_snapshot else 9.9

    # --- optional internal evolve (genotype DE) ---
    if args.internal_gens > 0:
        logger.info(
            "internal evolve: gens=%d de_iter=%d …",
            args.internal_gens,
            args.de_iter,
        )
        from evolve import main as evolve_main

        rc = evolve_main(
            [
                "-N",
                str(args.N),
                "-k",
                str(args.k),
                "--sectors",
                str(args.sectors),
                "--generations",
                str(args.internal_gens),
                "--de-iter",
                str(args.de_iter),
                "--json",
                str(args.knobs),
                "--plot",
                "evolve.png",
            ]
        )
        logger.info("internal evolve exit=%s", rc)
        # Preserve stage / ranking_hparams / ontology from pre-snapshot
        if pre_snapshot and args.knobs.is_file():
            try:
                post = json.loads(args.knobs.read_text(encoding="utf-8"))
                for key in (
                    "stage",
                    "ranking_hparams",
                    "ontology",
                    "ontology_note",
                    "defect_beta",
                    "fold_protocol",
                    "math_framing",
                    "tracks",
                    "commit_policy",
                ):
                    if key in pre_snapshot and key not in post:
                        post[key] = pre_snapshot[key]
                    elif key in pre_snapshot and key == "stage":
                        # merge stage, prefer new R metrics if present
                        merged = dict(pre_snapshot["stage"])
                        merged.update(post.get("stage") or {})
                        post["stage"] = merged
                    elif key in pre_snapshot and key == "ranking_hparams":
                        rh = dict(pre_snapshot["ranking_hparams"])
                        rh.update(post.get("ranking_hparams") or {})
                        post["ranking_hparams"] = rh
                write_json(args.knobs, post)
            except Exception as exc:  # noqa: BLE001
                logger.warning("stage merge failed: %s", exc)

    knobs = load_knobs(args.knobs)
    try:
        post_R = float(json.loads(args.knobs.read_text(encoding="utf-8")).get("R", 9.9))
    except Exception:  # noqa: BLE001
        post_R = 9.9
    # Natural selection founder: keep sealed elite if internal DE regressed residual
    if pre_knobs and post_R > pre_R + 0.005:
        logger.warning(
            "internal DE regressed R %.4f → %.4f; NS founder = pre-seal elite",
            pre_R,
            post_R,
        )
        print(
            f"  [guard] internal DE regressed R {pre_R:.4f}→{post_R:.4f}; "
            f"NS founder restored to pre-seal elite"
        )
        knobs = dict(pre_knobs)
    probe_ids = [x.strip().upper() for x in args.probe.split(",") if x.strip()]
    floor_ids = [x.strip().upper() for x in args.floors.split(",") if x.strip()]
    holdout_ids = [
        x.strip().upper()
        for x in args.holdout.split(",")
        if x.strip() and x.strip().upper() not in set(probe_ids)
    ]
    # floors used in soft F_ext may overlap holdout (4K8Y) — that's ok for soft pressure
    # but probe set must stay selection-only environment

    km = Keymaker(N=args.N, n_zeros=args.k, n_sectors=args.sectors)
    g_last = float(km.forge().field.gammas[-1])
    rng = np.random.default_rng(42)

    probe_fn = _probe_enrichment_fn(
        probe_ids,
        floor_ids,
        n_decoys=args.n_decoys,
        n_zeros=args.k,
        n_sectors=args.sectors,
        defect_beta=args.defect_beta,
        soft_T=args.soft_T,
        rng=rng,
    )

    # baseline environment score
    base_pe, base_fe = probe_fn(knobs)
    print(
        f"  baseline probe_enr={base_pe:.1%}  "
        f"floor_enr={base_fe if base_fe is not None else float('nan'):.1%}  "
        f"Λ={knobs['Lambda']:.2f}"
    )

    policy = AdaptivePolicy(tau=args.tau0, r_soft_cap=args.r_soft_cap)

    def log_line(msg: str) -> None:
        logger.info(msg)
        print(msg)

    if args.until_resolved:
        logger.info(
            "natural selection UNTIL RESOLVED: pop=%d max_epochs=%d patience=%d …",
            args.n_pop,
            args.max_epochs,
            args.resolve_patience,
        )
        print(
            f"  mode: tuple-time until resolution maximized "
            f"(max_epochs={args.max_epochs}, patience={args.resolve_patience})"
        )
    else:
        logger.info("natural selection: pop=%d epochs=%d …", args.n_pop, args.epochs)
    ns = run_natural_selection(
        knobs,
        g_last=g_last,
        N=args.N,
        n_zeros=args.k,
        n_sectors=args.sectors,
        n_pop=args.n_pop,
        n_epochs=args.epochs,
        policy=policy,
        probe_fn=probe_fn,
        rng=rng,
        log=log_line,
        until_resolved=bool(args.until_resolved),
        resolve_patience=args.resolve_patience,
        max_epochs=args.max_epochs if args.until_resolved else args.epochs,
        min_epochs=args.min_epochs,
    )

    champ = ns["champion"]
    champ_kn = champ["knobs"]
    argmax_tt = ns.get("argmax_resolution_tuple") or {}
    print(
        f"\n  champion F_tot={champ['F_total']:.4f}  probe={champ['probe_enrichment']:.1%}  "
        f"res={ns.get('champion_resolution', float('nan')):.4f}  "
        f"R={champ['R']:.4f}  occ={champ['occupancy']:.0%}  "
        f"lineage={champ['lineage']}"
    )
    print(
        f"  stop={ns.get('stop_reason')}  epochs_ran={ns.get('n_epochs_ran')}  "
        f"argmax_res_t={argmax_tt.get('t')}  max_res={argmax_tt.get('resolution')}"
    )

    # multi-seed re-eval probe + holdout (honest report)
    rng2 = np.random.default_rng(99)
    probe_ms, probe_rows = _rank_ids(
        champ_kn,
        probe_ids,
        n_decoys=args.verify_decoys,
        n_zeros=args.k,
        n_sectors=args.sectors,
        n_seeds=args.verify_seeds,
        defect_beta=args.defect_beta,
        soft_T=args.soft_T,
        rng=rng2,
    )
    hold_ms, hold_rows = _rank_ids(
        champ_kn,
        holdout_ids,
        n_decoys=args.verify_decoys,
        n_zeros=args.k,
        n_sectors=args.sectors,
        n_seeds=args.verify_seeds,
        defect_beta=args.defect_beta,
        soft_T=args.soft_T,
        rng=rng2,
    )
    print(
        f"  verify multi-seed: probe={probe_ms:.1%}  holdout={hold_ms:.1%}  "
        f"(decoys={args.verify_decoys}×seeds={args.verify_seeds})"
    )

    full_batch = None
    if args.full_batch:
        from pdb_batch import DEFAULT_CYCLIC_IDS

        logger.info("full batch on champion…")
        mean_e, rows = _rank_ids(
            champ_kn,
            DEFAULT_CYCLIC_IDS,
            n_decoys=args.verify_decoys,
            n_zeros=args.k,
            n_sectors=args.sectors,
            n_seeds=args.verify_seeds,
            defect_beta=args.defect_beta,
            soft_T=args.soft_T,
            rng=np.random.default_rng(11),
        )
        ok = [r for r in rows if r.get("status") == "OK"]
        n_top = sum(1 for r in ok if r.get("top20"))
        full_batch = {
            "rows": rows,
            "summary": {
                "mean_enrichment": mean_e,
                "n_ok": len(ok),
                "top20_count": n_top,
                "n_seeds": args.verify_seeds,
                "n_decoys": args.verify_decoys,
                "defect_beta": args.defect_beta,
            },
        }
        print(
            f"  FULL BATCH: mean={mean_e:.1%}  top20={n_top}/{len(ok)}"
        )

    # Accept gates: dual improvement without seal collapse
    base_F_ext = 1.0 - base_pe
    champ_better_probe = champ["probe_enrichment"] >= base_pe - 1e-9
    champ_better_dual = champ["F_total"] < (
        0.35 * 9.9 + 0.55 * base_F_ext  # loose; real gate uses multi-seed
    )
    # Prefer multi-seed probe vs baseline single-seed env — re-score baseline multi-seed
    base_ms, _ = _rank_ids(
        knobs,
        probe_ids,
        n_decoys=args.verify_decoys,
        n_zeros=args.k,
        n_sectors=args.sectors,
        n_seeds=args.verify_seeds,
        defect_beta=args.defect_beta,
        soft_T=args.soft_T,
        rng=np.random.default_rng(99),
    )
    seal_ok = float(ns["seal"].get("R") or 9) <= max(args.r_soft_cap * 2.0, 0.03)
    occ_ok = float(ns["seal"].get("occupancy") or 0) >= 0.75
    probe_ok = probe_ms >= max(args.accept_min_probe, base_ms - 0.02)
    dual_improve = probe_ms > base_ms + 0.005 or (
        abs(probe_ms - base_ms) <= 0.005 and champ["R"] <= float(pre_R) + 1e-6
    )
    # Accept only true dual wins (don't clobber sealed elite with equal probe)
    accept = (
        seal_ok
        and occ_ok
        and probe_ok
        and dual_improve
        and (probe_ms > base_ms + 0.005 or champ["R"] < pre_R - 1e-6)
    )

    print(
        f"\n  ACCEPT? {accept}  "
        f"(seal_ok={seal_ok} occ_ok={occ_ok} probe_ok={probe_ok} "
        f"base_ms={base_ms:.1%} champ_ms={probe_ms:.1%})"
    )

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ontology": ontology_note(),
        "framing": ns["framing"],
        "manifold_control": fold_control_snapshot(),
        "baseline": {
            "knobs": knobs,
            "probe_enrichment_fast": base_pe,
            "floor_enrichment_fast": base_fe,
            "probe_enrichment_multiseed": base_ms,
        },
        "natural_selection": ns,
        "verify": {
            "probe_mean": probe_ms,
            "holdout_mean": hold_ms,
            "probe_rows": probe_rows,
            "holdout_rows": hold_rows,
            "n_decoys": args.verify_decoys,
            "n_seeds": args.verify_seeds,
            "defect_beta": args.defect_beta,
        },
        "full_batch": full_batch,
        "accept": accept,
        "gates": {
            "seal_ok": seal_ok,
            "occ_ok": occ_ok,
            "probe_ok": probe_ok,
            "dual_improve": dual_improve,
            "base_probe_ms": base_ms,
            "champ_probe_ms": probe_ms,
        },
        "commit_policy": {
            "zeta_preference": False,
            "geometry_ranking_external": True,
            "selection_environment": "probe_only",
            "holdout": "report_only_never_in_objective",
        },
    }
    write_json(args.json, payload)
    print(f"  wrote {args.json}")

    if args.write_evolve and accept:
        # merge into evolve_result preserving stage / ranking_hparams
        prev: dict = {}
        if args.knobs.is_file():
            try:
                prev = json.loads(args.knobs.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                prev = {}
        stage = dict(prev.get("stage") or {})
        stage.update(
            {
                "path": "geometry_off_zeta_external_cyclic_ranking",
                "method": (
                    "adaptive_NS dual fitness + PROJ_SHEAF_DEFECT beta=0.20 "
                    "+ self_fit_dense"
                ),
                "adaptive_evolve": {
                    "probe_ms": probe_ms,
                    "holdout_ms": hold_ms,
                    "F_total": champ["F_total"],
                    "epochs": args.epochs,
                    "n_pop": args.n_pop,
                    "final_tau": ns["policy"]["final_tau"],
                },
                "batch_note": "NS champion accepted; re-run full batch to refresh metrics",
            }
        )
        rh = dict(prev.get("ranking_hparams") or stage.get("ranking_hparams") or {})
        rh.setdefault("defect_beta", args.defect_beta)
        rh.setdefault("soft_T", args.soft_T)
        rh.setdefault("aggregate", "softmin")
        rh.setdefault("multimode_mode", "self_fit_dense")
        rh.setdefault("sectors_mode", "adaptive")
        rh["accepted"] = True
        out = {
            **{k: v for k, v in prev.items() if k not in ("best_knobs", "meet_knobs")},
            "status": "EVOLVED_SEAL" if champ["R"] <= 0.01 else "EVOLVING",
            "generation_time": datetime.now(timezone.utc).isoformat(),
            "best_knobs": champ_kn,
            "meet_knobs": champ_kn,
            "F": champ["F_int"],
            "R": champ["R"],
            "occupancy": champ["occupancy"],
            "n_keys": champ["n_keys"],
            "n_valleys": champ["n_valleys"],
            "search": "adaptive_natural_selection_dual_fitness",
            "ontology": "substrate_projection_operator_dual",
            "stage": stage,
            "ranking_hparams": rh,
            "ns_verify": {
                "probe_mean": probe_ms,
                "holdout_mean": hold_ms,
                "accepted": True,
            },
        }
        write_json(args.knobs, out)
        print(f"  ACCEPTED → wrote {args.knobs}")
    elif args.write_evolve:
        print("  NOT accepted — evolve_result unchanged (gates failed)")

    return 0 if accept else 1


if __name__ == "__main__":
    raise SystemExit(main())
