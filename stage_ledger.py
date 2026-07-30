#!/usr/bin/env python3
"""Stage ledger — AXiomZ resolve/verify before claim (12.2, 12.3).

Runs Configurational Term Series + loads dual/batch/transfer artifacts if
present. Emits a ledger that separates:

  RESOLVED  — instrument ran, numbers recorded
  COMMITTED — only claims allowed by verification guards

Never auto-commits ζ preference. Legacy seating PASS is recorded as artifact.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realm.axiomz import activation_signature, load_mapping, run_term_series
from realm.validate.report import load_knobs, write_json

logger = logging.getLogger("stage_ledger")


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="AXiomZ stage ledger (resolve/verify)")
    p.add_argument("--knobs", type=Path, default=Path("evolve_result.json"))
    p.add_argument("-N", type=int, default=13)
    p.add_argument("-k", type=int, default=14)
    p.add_argument("--sectors", type=int, default=6)
    p.add_argument("--batch-json", type=Path, default=Path("pdb_batch_result.json"))
    p.add_argument("--transfer-json", type=Path, default=Path("transfer_result.json"))
    p.add_argument("--dual-json", type=Path, default=Path("dual_probe_result.json"))
    p.add_argument("--null-json", type=Path, default=Path("null_battery_result.json"))
    p.add_argument("--json", type=Path, default=Path("stage_ledger.json"))
    p.add_argument(
        "--mode",
        choices=("resolve", "report"),
        default="resolve",
        help="resolve runs CTS; report only aggregates existing artifacts",
    )
    p.add_argument("-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    mapping = load_mapping()
    knobs = load_knobs(args.knobs) if args.knobs.is_file() else {}

    cts = None
    if args.mode == "resolve":
        logger.info("CTS resolve (Axiom 5.2)…")
        cts = run_term_series(
            knobs, N=args.N, n_zeros=args.k, n_sectors=args.sectors
        )

    batch = _load_json(args.batch_json)
    transfer = _load_json(args.transfer_json)
    dual = _load_json(args.dual_json)
    null = _load_json(args.null_json)

    # --- Verification criteria (6.1, 12.2) ---
    checks = []

    def add(name: str, ok: bool, detail: str, axioms: list[str]):
        checks.append(
            {"name": name, "ok": ok, "detail": detail, "axioms": axioms}
        )

    if null:
        claim = null.get("zeta_preference_claim", "UNKNOWN")
        add(
            "zeta_preference_not_claimed",
            claim == "RETRACTED" or claim is False,
            f"null_battery claim={claim}",
            ["6.1", "6.2", "G1"],
        )
        seating = (null.get("seating_check") or {}).get("passed")
        add(
            "seating_recorded_as_artifact",
            True,
            f"legacy seating_pass={seating} (not ζ evidence)",
            ["6.2", "12.3"],
        )
    else:
        add("null_battery_present", False, "missing null_battery_result.json", ["12.2"])

    if transfer:
        hold = transfer.get("zeta_preference_on_holdout", None)
        add(
            "transfer_holdout_no_false_preference",
            hold is False or hold is None,
            f"zeta_preference_on_holdout={hold}",
            ["6.1", "12.2"],
        )
        rows = transfer.get("rows") or []
        if len(rows) >= 2:
            adv = rows[1].get("advantage_legacy", 1.0)
            add(
                "holdout_legacy_advantage_collapsed",
                adv < 1.2,
                f"hold_g15_28 adv_legacy={adv:.2f}×",
                ["6.1"],
            )
    else:
        add("transfer_present", False, "missing transfer_result.json", ["12.2"])

    if batch:
        s = batch.get("summary") or {}
        mean_e = float(s.get("mean_enrichment", 0.0))
        add(
            "external_ranking_signal",
            mean_e > 0.55,
            f"batch mean_enrichment={mean_e:.1%} (projection path)",
            ["2.4", "5.2", "5.3"],
        )
        add(
            "multi_seed_stability",
            int(s.get("n_seeds", 0)) >= 2,
            f"n_seeds={s.get('n_seeds')}",
            ["4.3"],
        )
    else:
        add("batch_present", False, "missing pdb_batch_result.json", ["12.2"])

    if cts:
        quale = cts["cts"][4]
        add(
            "informative_residual_not_confused_with_legacy",
            float(quale["R_informative"]) > float(quale["R_legacy_seating"]),
            f"R_info={quale['R_informative']:.4f} > R_leg={quale['R_legacy_seating']:.4f}",
            ["6.2"],
        )
        add(
            "crit_basins_persist",
            int(quale["n_persistent_crit_basins"]) >= 1,
            f"n_persistent={quale['n_persistent_crit_basins']}",
            ["4.3"],
        )

    # Commit policy (12.3): only projection ranking + instrument honesty
    allowed_commits = {
        "zeta_preference": False,
        "reason_blocked": (
            "RETRACTED — ζ is substrate seed only, not preference claim "
            "(see realm/ontology.py)"
        ),
        "geometry_projection_ranking": bool(
            batch and float((batch.get("summary") or {}).get("mean_enrichment", 0)) > 0.55
        ),
        # alias for older readers
        "geometry_ranking_external": bool(
            batch and float((batch.get("summary") or {}).get("mean_enrichment", 0)) > 0.55
        ),
        "maxop_dual_diagnostic": dual is not None or cts is not None,
        "dual_instrument_ready": dual is not None or cts is not None,
        "cts_resolved": cts is not None,
        "ontology": "substrate_projection_operator_dual",
    }

    n_ok = sum(1 for c in checks if c["ok"])
    n_fail = sum(1 for c in checks if not c["ok"])

    print("\n=== STAGE LEDGER (AXiomZ resolve/verify) ===")
    print(f"  mapping activations: {len(mapping.get('activations', []))}")
    if cts:
        for st in cts["cts"]:
            print(f"  CTS [{st['stage']:10s}]  axioms={st.get('axioms')}")
        q = cts["cts"][4]
        print(
            f"  quale: R_info={q['R_informative']:.4f}  R_leg={q['R_legacy_seating']:.4f}  "
            f"persist_basins={q['n_persistent_crit_basins']}"
        )
    print(f"\n  verification: {n_ok} ok / {n_fail} fail")
    for c in checks:
        mark = "OK  " if c["ok"] else "FAIL"
        print(f"    [{mark}] {c['name']}: {c['detail']}")
    print("\n  COMMIT POLICY:")
    print(f"    zeta_preference: {allowed_commits['zeta_preference']}  ({allowed_commits['reason_blocked']})")
    print(f"    geometry_ranking_external: {allowed_commits['geometry_ranking_external']}")
    print(f"    dual_instrument_ready: {allowed_commits['dual_instrument_ready']}")
    print(f"    cts_resolved: {allowed_commits['cts_resolved']}")

    payload = {
        "mode": args.mode,
        "signature": activation_signature(
            "stage_ledger",
            ["5.2", "6.1", "6.2", "12.2", "12.3", "18.2", "G1"],
        ),
        "mapping_path": "01-DEVELOPMENT-AXiomZ/ACTIVE_MAPPING.json",
        "cts": cts,
        "artifacts": {
            "batch": (batch or {}).get("summary"),
            "transfer_holdout_preference": (transfer or {}).get(
                "zeta_preference_on_holdout"
            ),
            "null_claim": (null or {}).get("zeta_preference_claim"),
            "dual_summary": (dual or {}).get("summary"),
        },
        "verification": checks,
        "n_ok": n_ok,
        "n_fail": n_fail,
        "commit_policy": allowed_commits,
        "ontology": "axiomz_stage_ledger_not_lambda_eq_gamma",
    }
    write_json(args.json, payload)
    print(f"\nwrote {args.json}", file=sys.stderr)
    # exit 0 if critical guards hold (ζ not falsely claimed)
    critical_fail = any(
        (not c["ok"]) and c["name"] in (
            "zeta_preference_not_claimed",
            "transfer_holdout_no_false_preference",
        )
        for c in checks
    )
    return 2 if critical_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
