"""Cyclic coherence protocol for dual-gate handoff routines.

Loop: observe → score → negotiate free parameters → re-execute → until solved.

LOCKED (never adapted):
  dual-gate LengthPolicy pin soft_T(n=12)=0.036, seq_mix=0, face_weight=0.08

NEGOTIABLE (bounded free parameters only):
  decorate mode, physics mode, top_k

Ontology: Crit projection molds; never λ=γ.
Commercial accept remains openable PDBs + pin — not enrichment score-chase.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from realm.handoff.verify import verify_dual_gate_pin, verify_handoff_tree

logger = logging.getLogger(__name__)

# Free-parameter domains (closed sets — no open-ended retune of dual-gate pin)
DECORATE_ORDER = ("sequence", "polyala", "null")
PHYSICS_ORDER = ("geometry", "none")
TOP_K_BOUNDS = (1, 8)


@dataclass
class FreeParams:
    """Negotiable routine knobs (not dual-gate LengthPolicy)."""

    decorate: str = "sequence"
    physics: str = "geometry"
    top_k: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def clamp(self) -> FreeParams:
        d = str(self.decorate or "sequence").lower().strip()
        if d not in DECORATE_ORDER and d != "auto":
            d = "sequence"
        if d == "auto":
            d = "sequence"
        p = str(self.physics or "geometry").lower().strip()
        if p not in PHYSICS_ORDER:
            p = "geometry"
        k = int(self.top_k)
        k = max(TOP_K_BOUNDS[0], min(TOP_K_BOUNDS[1], k))
        return FreeParams(decorate=d, physics=p, top_k=k)


@dataclass
class CoherenceThresholds:
    """What 'solved' means for the commercial routine (not enrichment)."""

    min_export_ok_fraction: float = 1.0
    max_physics_fail: int = 0
    min_decorate_ok_fraction: float = 0.5  # only if decorate != null
    require_verify_ok: bool = True
    require_pin: bool = True
    require_decorate: bool = False  # if True, null decorate is not coherent

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Observations:
    """What the cycle measured after one execution."""

    pin_ok: bool
    soft_T: float | None
    n_ids: int
    n_export_ok: int
    n_pdb_ontology: int
    verify_ok: bool | None
    decorate_n_ok: int
    decorate_n_molds: int
    decorate_n_paths: int
    physics_n_ok: int
    physics_n_warn: int
    physics_n_fail: int
    out_dir: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observe(
    *,
    pin: dict[str, Any],
    export_summary: dict[str, Any],
    verify_report: dict[str, Any] | None,
    out_dir: Path | str,
) -> Observations:
    """Extract observations from export + verify artifacts."""
    dec = export_summary.get("decorate_rollup") or {}
    # per-id rollups may nest under rows if batch didn't flatten
    if not dec.get("n_molds") and export_summary.get("rows"):
        n_ok = n_paths = n_molds = 0
        for r in export_summary.get("rows") or []:
            dr = r.get("decorate_rollup") or {}
            if not dr and r.get("status") == "OK":
                # single-id style inside batch rows is shallow — use fields
                pass
            n_ok += int(dr.get("n_ok") or 0)
            n_paths += int(dr.get("n_with_path") or 0)
            n_molds += int(dr.get("n_molds") or 0)
        if n_molds:
            dec = {
                "n_ok": n_ok,
                "n_with_path": n_paths,
                "n_molds": n_molds,
            }
    phys = export_summary.get("physics_rollup") or {}
    # batch may only have campaign rollup; single export has nested
    if phys.get("n_reports") is None and export_summary.get("rows"):
        n_ok = n_warn = n_fail = 0
        for r in export_summary.get("rows") or []:
            pr = r.get("physics_rollup") or {}
            n_ok += int(pr.get("n_ok") or 0)
            n_warn += int(pr.get("n_warn") or 0)
            n_fail += int(pr.get("n_fail") or 0)
        phys = {"n_ok": n_ok, "n_warn": n_warn, "n_fail": n_fail}

    n_ids = int(export_summary.get("n_ids") or len(export_summary.get("rows") or []) or 0)
    n_export_ok = int(export_summary.get("n_ok") or 0)
    ont = (verify_report or {}).get("ontology_remarks") or {}
    n_pdb = int(ont.get("n_pdb") or 0)
    verify_ok = (verify_report or {}).get("ok")
    notes: list[str] = []
    if not pin.get("ok"):
        notes.append("pin_fail")
    if n_ids and n_export_ok < n_ids:
        notes.append("export_incomplete")
    if int(phys.get("n_fail") or 0) > 0:
        notes.append("physics_fail")
    if int(dec.get("n_molds") or 0) and int(dec.get("n_ok") or 0) == 0:
        notes.append("decorate_zero")

    return Observations(
        pin_ok=bool(pin.get("ok")),
        soft_T=float(pin["soft_T"]) if pin.get("soft_T") is not None else None,
        n_ids=n_ids,
        n_export_ok=n_export_ok,
        n_pdb_ontology=n_pdb,
        verify_ok=verify_ok if verify_report is not None else None,
        decorate_n_ok=int(dec.get("n_ok") or 0),
        decorate_n_molds=int(dec.get("n_molds") or 0),
        decorate_n_paths=int(dec.get("n_with_path") or 0),
        physics_n_ok=int(phys.get("n_ok") or 0),
        physics_n_warn=int(phys.get("n_warn") or 0),
        physics_n_fail=int(phys.get("n_fail") or 0),
        out_dir=str(out_dir),
        notes=notes,
    )


def is_solved(obs: Observations, thr: CoherenceThresholds, params: FreeParams) -> bool:
    """Coherence gate: commercial openability + free-routine health."""
    if thr.require_pin and not obs.pin_ok:
        return False
    if obs.n_ids <= 0:
        return False
    frac = obs.n_export_ok / max(obs.n_ids, 1)
    if frac + 1e-12 < thr.min_export_ok_fraction:
        return False
    if thr.require_verify_ok and obs.verify_ok is False:
        return False
    if obs.physics_n_fail > thr.max_physics_fail:
        return False
    if thr.require_decorate and params.decorate == "null":
        return False
    if params.decorate != "null" and obs.decorate_n_molds > 0:
        dfrac = obs.decorate_n_ok / max(obs.decorate_n_molds, 1)
        if dfrac + 1e-12 < thr.min_decorate_ok_fraction:
            return False
    if thr.require_verify_ok and obs.n_pdb_ontology < 1 and obs.verify_ok is not True:
        # need at least openable molds when verify ran
        if obs.verify_ok is None and obs.n_export_ok > 0:
            pass  # verify skipped
        elif obs.n_export_ok > 0 and obs.n_pdb_ontology < 1 and obs.verify_ok is False:
            return False
    return True


def coherence_score(obs: Observations, thr: CoherenceThresholds, params: FreeParams) -> float:
    """Scalar 0..1 for trajectory logging (not commercial accept)."""
    parts: list[float] = []
    parts.append(1.0 if obs.pin_ok else 0.0)
    parts.append(obs.n_export_ok / max(obs.n_ids, 1))
    if obs.verify_ok is True:
        parts.append(1.0)
    elif obs.verify_ok is False:
        parts.append(0.0)
    else:
        parts.append(0.5)
    n_phys = obs.physics_n_ok + obs.physics_n_warn + obs.physics_n_fail
    if n_phys > 0:
        parts.append(1.0 - obs.physics_n_fail / n_phys)
    else:
        parts.append(1.0 if params.physics == "none" else 0.5)
    if params.decorate != "null" and obs.decorate_n_molds > 0:
        parts.append(obs.decorate_n_ok / max(obs.decorate_n_molds, 1))
    else:
        parts.append(1.0 if params.decorate == "null" else 0.5)
    return float(sum(parts) / len(parts))


def negotiate(
    obs: Observations,
    params: FreeParams,
    thr: CoherenceThresholds,
    *,
    tried: set[str],
) -> tuple[FreeParams | None, str]:
    """Propose next free params from observations. None = stuck / coherent.

    Never proposes dual-gate pin changes.
    """
    p = params.clamp()
    key = json.dumps(p.to_dict(), sort_keys=True)
    tried.add(key)

    if thr.require_pin and not obs.pin_ok:
        return None, "pin_locked_fail_cannot_negotiate"

    if is_solved(obs, thr, p):
        return None, "already_coherent"

    # 1) decorate path: null → sequence → polyala
    if p.decorate == "null" and (
        thr.require_decorate
        or obs.decorate_n_paths == 0
        or "decorate_zero" in obs.notes
    ):
        cand = FreeParams(decorate="sequence", physics=p.physics, top_k=p.top_k).clamp()
        ck = json.dumps(cand.to_dict(), sort_keys=True)
        if ck not in tried:
            return cand, "enable_sequence_decorate"

    if p.decorate == "sequence" and obs.decorate_n_molds > 0:
        dfrac = obs.decorate_n_ok / max(obs.decorate_n_molds, 1)
        if dfrac + 1e-12 < thr.min_decorate_ok_fraction:
            cand = FreeParams(decorate="polyala", physics=p.physics, top_k=p.top_k).clamp()
            ck = json.dumps(cand.to_dict(), sort_keys=True)
            if ck not in tried:
                return cand, "fallback_polyala_decorate"

    if p.decorate == "polyala" and obs.decorate_n_molds > 0:
        dfrac = obs.decorate_n_ok / max(obs.decorate_n_molds, 1)
        if dfrac + 1e-12 < thr.min_decorate_ok_fraction:
            cand = FreeParams(decorate="sequence", physics=p.physics, top_k=p.top_k).clamp()
            ck = json.dumps(cand.to_dict(), sort_keys=True)
            if ck not in tried:
                return cand, "retry_sequence_decorate"

    # 2) physics fail: cannot retune pin; try slightly more molds then disable physics filter
    if obs.physics_n_fail > thr.max_physics_fail:
        if p.top_k < TOP_K_BOUNDS[1]:
            cand = FreeParams(
                decorate=p.decorate, physics=p.physics, top_k=p.top_k + 1
            ).clamp()
            ck = json.dumps(cand.to_dict(), sort_keys=True)
            if ck not in tried:
                return cand, "increase_top_k_after_physics_fail"
        if p.physics != "none":
            cand = FreeParams(decorate=p.decorate, physics="none", top_k=p.top_k).clamp()
            ck = json.dumps(cand.to_dict(), sort_keys=True)
            if ck not in tried:
                return cand, "disable_physics_after_fail"

    # 3) export incomplete: try larger top_k once
    if obs.n_ids and obs.n_export_ok < obs.n_ids:
        if p.top_k < TOP_K_BOUNDS[1]:
            cand = FreeParams(
                decorate=p.decorate, physics=p.physics, top_k=min(TOP_K_BOUNDS[1], p.top_k + 2)
            ).clamp()
            ck = json.dumps(cand.to_dict(), sort_keys=True)
            if ck not in tried:
                return cand, "increase_top_k_export_incomplete"

    # 4) verify failed but export ok: often decorate remark issues — already stamped;
    #    try sequence decorate if null
    if obs.verify_ok is False and obs.n_export_ok > 0:
        if p.decorate == "null":
            cand = FreeParams(decorate="sequence", physics=p.physics, top_k=p.top_k).clamp()
            ck = json.dumps(cand.to_dict(), sort_keys=True)
            if ck not in tried:
                return cand, "sequence_after_verify_fail"

    return None, "stuck_no_free_param_move"


def run_coherence_loop(
    *,
    pdb_ids: list[str],
    knobs: dict[str, Any],
    out_root: Path | str,
    initial: FreeParams | None = None,
    thresholds: CoherenceThresholds | None = None,
    max_rounds: int = 6,
    verify: bool = True,
    n_zeros: int = 14,
) -> dict[str, Any]:
    """Execute cyclic observe→negotiate→export until coherent or budget ends.

    Dual-gate pin is re-checked every round and never written/adapted.
    """
    from realm.handoff.pipeline import export_structure_batch

    thr = thresholds or CoherenceThresholds()
    params = (initial or FreeParams()).clamp()
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    pin0 = verify_dual_gate_pin()
    ledger: list[dict[str, Any]] = []
    tried: set[str] = set()
    solved = False
    stop_reason = "max_rounds"

    for rnd in range(1, max(1, int(max_rounds)) + 1):
        cycle_dir = out_root / f"cycle_{rnd:02d}"
        pin = verify_dual_gate_pin()
        logger.info(
            "coherence cycle %s/%s decorate=%s physics=%s top_k=%s pin_ok=%s soft_T=%s",
            rnd,
            max_rounds,
            params.decorate,
            params.physics,
            params.top_k,
            pin.get("ok"),
            pin.get("soft_T"),
        )
        if thr.require_pin and not pin.get("ok"):
            stop_reason = "pin_fail"
            ledger.append(
                {
                    "round": rnd,
                    "params": params.to_dict(),
                    "pin": pin,
                    "solved": False,
                    "action": "abort",
                    "reason": "dual_gate_pin_failed_locked",
                }
            )
            break

        summary = export_structure_batch(
            list(pdb_ids),
            knobs,
            out_root=cycle_dir,
            top_k=int(params.top_k),
            n_zeros=int(n_zeros),
            include_coutsias=False,
            decorate=params.decorate,
            physics=params.physics,
            with_enrichment=False,
            with_biopython_check=True,
            resume=False,
        )
        vreport = None
        if verify:
            vreport = verify_handoff_tree(
                cycle_dir,
                require_sha256=False,
                check_biopython=False,
            )
            (cycle_dir / "verify_report.json").write_text(
                json.dumps(vreport, indent=2) + "\n", encoding="utf-8"
            )

        # Prefer campaign rollups on cycle root; fall back to first OK child index
        if not summary.get("decorate_rollup") or not (
            summary.get("decorate_rollup") or {}
        ).get("n_molds"):
            # aggregate from child index.json
            n_ok = n_paths = n_molds = 0
            by_st: dict[str, int] = {}
            for child in cycle_dir.iterdir() if cycle_dir.is_dir() else []:
                idx = child / "index.json"
                if not idx.is_file():
                    continue
                try:
                    data = json.loads(idx.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                dr = data.get("decorate_rollup") or {}
                n_ok += int(dr.get("n_ok") or 0)
                n_paths += int(dr.get("n_with_path") or 0)
                n_molds += int(dr.get("n_molds") or 0)
                for st, c in (dr.get("by_status") or {}).items():
                    by_st[st] = by_st.get(st, 0) + int(c)
            if n_molds:
                summary["decorate_rollup"] = {
                    "n_ok": n_ok,
                    "n_with_path": n_paths,
                    "n_molds": n_molds,
                    "by_status": by_st,
                }
            # physics from children
            p_ok = p_w = p_f = 0
            for child in cycle_dir.iterdir() if cycle_dir.is_dir() else []:
                idx = child / "index.json"
                if not idx.is_file():
                    continue
                try:
                    data = json.loads(idx.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                pr = data.get("physics_rollup") or {}
                p_ok += int(pr.get("n_ok") or 0)
                p_w += int(pr.get("n_warn") or 0)
                p_f += int(pr.get("n_fail") or 0)
            if p_ok + p_w + p_f:
                summary["physics_rollup"] = {
                    "n_ok": p_ok,
                    "n_warn": p_w,
                    "n_fail": p_f,
                }

        obs = observe(
            pin=pin,
            export_summary=summary,
            verify_report=vreport,
            out_dir=cycle_dir,
        )
        score = coherence_score(obs, thr, params)
        solved = is_solved(obs, thr, params)
        entry = {
            "round": rnd,
            "params": params.to_dict(),
            "observations": obs.to_dict(),
            "coherence_score": score,
            "solved": solved,
            "pin": {
                "ok": pin.get("ok"),
                "soft_T": pin.get("soft_T"),
                "seq_mix": pin.get("seq_mix"),
                "face_weight": pin.get("face_weight"),
            },
            "export_n_ok": summary.get("n_ok"),
            "export_n_ids": summary.get("n_ids"),
            "cycle_dir": str(cycle_dir.resolve()),
        }

        if solved:
            entry["action"] = "halt"
            entry["reason"] = "coherent"
            ledger.append(entry)
            stop_reason = "coherent"
            logger.info("coherence SOLVED at round %s score=%.3f", rnd, score)
            break

        nxt, reason = negotiate(obs, params, thr, tried=tried)
        entry["action"] = "negotiate" if nxt is not None else "stuck"
        entry["reason"] = reason
        entry["next_params"] = nxt.to_dict() if nxt is not None else None
        ledger.append(entry)
        (cycle_dir / "coherence_round.json").write_text(
            json.dumps(entry, indent=2) + "\n", encoding="utf-8"
        )

        if nxt is None:
            stop_reason = reason
            logger.info("coherence stuck: %s", reason)
            break
        logger.info("negotiate → %s (%s)", nxt.to_dict(), reason)
        params = nxt

    result = {
        "ontology": "handoff_coherence_protocol_not_lambda_eq_gamma",
        "solved": solved,
        "stop_reason": stop_reason,
        "n_rounds": len(ledger),
        "max_rounds": int(max_rounds),
        "thresholds": thr.to_dict(),
        "final_params": params.to_dict(),
        "pin_locked": {
            "soft_T_n12": 0.036,
            "seq_mix": 0.0,
            "face_weight": 0.08,
            "verified": pin0.get("ok"),
            "note": "LengthPolicy pin never negotiated by this protocol",
        },
        "ledger": ledger,
        "out_root": str(out_root.resolve()),
        "pdb_ids": list(pdb_ids),
        "note": (
            "Cyclic observe→negotiate→export loop. Free params only: decorate/physics/top_k. "
            "Dual-gate pin locked. Not enrichment score-chase. Never lambda=gamma."
        ),
    }
    (out_root / "COHERENCE.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _write_coherence_md(result, out_root / "COHERENCE.md")
    return result


def _write_coherence_md(result: dict[str, Any], path: Path) -> Path:
    lines = [
        "# Coherence protocol ledger",
        "",
        f"- **solved:** {result.get('solved')}",
        f"- **stop:** `{result.get('stop_reason')}`",
        f"- **rounds:** {result.get('n_rounds')} / {result.get('max_rounds')}",
        f"- **final free params:** `{result.get('final_params')}`",
        f"- **pin locked:** soft_T(n=12)=**0.036** (never adapted)",
        "",
        "Commercial accept remains openable PDBs + dual-gate pin — not this loop's score.",
        "Never lambda=gamma.",
        "",
        "| round | decorate | physics | top_k | score | solved | action | reason |",
        "|------:|----------|---------|------:|------:|:------:|--------|--------|",
    ]
    for e in result.get("ledger") or []:
        p = e.get("params") or {}
        lines.append(
            f"| {e.get('round')} | {p.get('decorate')} | {p.get('physics')} | "
            f"{p.get('top_k')} | {e.get('coherence_score')} | {e.get('solved')} | "
            f"{e.get('action')} | {e.get('reason')} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
