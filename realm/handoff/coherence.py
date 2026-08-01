"""Cyclic coherence protocol for dual-gate handoff routines.

Loop: observe → multi-section proposals → merge → re-execute → until solved.

LOCKED (never adapted):
  dual-gate LengthPolicy pin soft_T(n=12)=0.036, seq_mix=0, face_weight=0.08

NEGOTIABLE (bounded free parameters only):
  decorate mode, physics mode, top_k

Sections (sheaf-style local proposals):
  export | decorate | physics | science | verify
  Merge ranks by priority; never proposes pin retune.

Ontology: Crit projection molds; never λ=γ.
Commercial accept remains openable PDBs + pin — not enrichment score-chase.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from realm.handoff.verify import verify_dual_gate_pin, verify_handoff_tree

logger = logging.getLogger(__name__)

# Free-parameter domains (closed sets — no open-ended retune of dual-gate pin)
DECORATE_ORDER = ("sequence", "polyala", "null")
PHYSICS_ORDER = ("geometry", "none")
TOP_K_BOUNDS = (1, 8)

# Merge priority: lower number wins when proposals conflict
SECTION_PRIORITY = {
    "pin": 0,  # only abort; never param
    "export": 1,
    "verify": 2,
    "physics": 3,
    "decorate": 4,
    "science": 5,  # informational — free-param only, never pin
}


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
    # Optional science channel (informational; never accept gate)
    science_soft_enrichment: float | None = None
    science_n_ok: int = 0
    science_n_attempted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SectionProposal:
    """One section's proposed free-param move (never pin)."""

    section: str
    params: FreeParams
    reason: str
    priority: int = 99

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "params": self.params.to_dict(),
            "reason": self.reason,
            "priority": self.priority,
        }


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


def _fresh(cand: FreeParams, tried: set[str]) -> FreeParams | None:
    c = cand.clamp()
    ck = json.dumps(c.to_dict(), sort_keys=True)
    if ck in tried:
        return None
    return c


def collect_section_proposals(
    obs: Observations,
    params: FreeParams,
    thr: CoherenceThresholds,
    *,
    tried: set[str],
) -> list[SectionProposal]:
    """Each section proposes at most one free-param move (never pin)."""
    p = params.clamp()
    props: list[SectionProposal] = []

    # --- export ---
    if obs.n_ids and obs.n_export_ok < obs.n_ids and p.top_k < TOP_K_BOUNDS[1]:
        cand = _fresh(
            FreeParams(
                decorate=p.decorate,
                physics=p.physics,
                top_k=min(TOP_K_BOUNDS[1], p.top_k + 2),
            ),
            tried,
        )
        if cand:
            props.append(
                SectionProposal(
                    "export",
                    cand,
                    "increase_top_k_export_incomplete",
                    SECTION_PRIORITY["export"],
                )
            )

    # --- verify ---
    if obs.verify_ok is False and obs.n_export_ok > 0 and p.decorate == "null":
        cand = _fresh(
            FreeParams(decorate="sequence", physics=p.physics, top_k=p.top_k),
            tried,
        )
        if cand:
            props.append(
                SectionProposal(
                    "verify",
                    cand,
                    "sequence_after_verify_fail",
                    SECTION_PRIORITY["verify"],
                )
            )

    # --- physics ---
    if obs.physics_n_fail > thr.max_physics_fail:
        if p.top_k < TOP_K_BOUNDS[1]:
            cand = _fresh(
                FreeParams(decorate=p.decorate, physics=p.physics, top_k=p.top_k + 1),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "physics",
                        cand,
                        "increase_top_k_after_physics_fail",
                        SECTION_PRIORITY["physics"],
                    )
                )
        if p.physics != "none":
            cand = _fresh(
                FreeParams(decorate=p.decorate, physics="none", top_k=p.top_k),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "physics",
                        cand,
                        "disable_physics_after_fail",
                        SECTION_PRIORITY["physics"] + 1,  # prefer top_k first
                    )
                )

    # --- decorate ---
    if p.decorate == "null" and (
        thr.require_decorate
        or obs.decorate_n_paths == 0
        or "decorate_zero" in obs.notes
    ):
        cand = _fresh(
            FreeParams(decorate="sequence", physics=p.physics, top_k=p.top_k),
            tried,
        )
        if cand:
            props.append(
                SectionProposal(
                    "decorate",
                    cand,
                    "enable_sequence_decorate",
                    SECTION_PRIORITY["decorate"],
                )
            )

    if p.decorate == "sequence" and obs.decorate_n_molds > 0:
        dfrac = obs.decorate_n_ok / max(obs.decorate_n_molds, 1)
        if dfrac + 1e-12 < thr.min_decorate_ok_fraction:
            cand = _fresh(
                FreeParams(decorate="polyala", physics=p.physics, top_k=p.top_k),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "decorate",
                        cand,
                        "fallback_polyala_decorate",
                        SECTION_PRIORITY["decorate"],
                    )
                )

    if p.decorate == "polyala" and obs.decorate_n_molds > 0:
        dfrac = obs.decorate_n_ok / max(obs.decorate_n_molds, 1)
        if dfrac + 1e-12 < thr.min_decorate_ok_fraction:
            cand = _fresh(
                FreeParams(decorate="sequence", physics=p.physics, top_k=p.top_k),
                tried,
            )
            if cand:
                props.append(
                    SectionProposal(
                        "decorate",
                        cand,
                        "retry_sequence_decorate",
                        SECTION_PRIORITY["decorate"],
                    )
                )

    # --- science (informational only: nudge top_k if soft enrichment weak; never pin) ---
    if (
        obs.science_soft_enrichment is not None
        and obs.science_n_ok > 0
        and float(obs.science_soft_enrichment) < 0.5
        and p.top_k < TOP_K_BOUNDS[1]
    ):
        cand = _fresh(
            FreeParams(
                decorate=p.decorate if p.decorate != "null" else "sequence",
                physics=p.physics,
                top_k=min(TOP_K_BOUNDS[1], p.top_k + 1),
            ),
            tried,
        )
        if cand:
            props.append(
                SectionProposal(
                    "science",
                    cand,
                    "nudge_top_k_weak_science_enrichment_info_only",
                    SECTION_PRIORITY["science"],
                )
            )

    return props


def merge_proposals(
    proposals: list[SectionProposal],
    current: FreeParams,
) -> tuple[FreeParams | None, str, list[dict[str, Any]]]:
    """Sheaf-style merge: highest-priority (lowest number) proposal wins.

    On field conflicts between equal-priority sections, earlier in sorted list wins.
    """
    if not proposals:
        return None, "stuck_no_free_param_move", []
    ranked = sorted(proposals, key=lambda x: (x.priority, x.section, x.reason))
    winner = ranked[0]
    # Field-wise: allow higher-priority sections to own their primary field
    # Start from winner full params (clean single-move protocol)
    return (
        winner.params.clamp(),
        f"merge[{winner.section}]:{winner.reason}",
        [pr.to_dict() for pr in ranked],
    )


def negotiate(
    obs: Observations,
    params: FreeParams,
    thr: CoherenceThresholds,
    *,
    tried: set[str],
) -> tuple[FreeParams | None, str, list[dict[str, Any]]]:
    """Multi-section propose + merge. Never proposes dual-gate pin changes.

    Returns (next_params|None, reason, proposal_board).
    """
    p = params.clamp()
    key = json.dumps(p.to_dict(), sort_keys=True)
    tried.add(key)

    if thr.require_pin and not obs.pin_ok:
        return None, "pin_locked_fail_cannot_negotiate", []

    if is_solved(obs, thr, p):
        return None, "already_coherent", []

    proposals = collect_section_proposals(obs, p, thr, tried=tried)
    nxt, reason, board = merge_proposals(proposals, p)
    if nxt is not None:
        tried.add(json.dumps(nxt.to_dict(), sort_keys=True))
    return nxt, reason, board


def _science_soft_probe(
    pdb_ids: list[str],
    knobs: dict[str, Any],
    *,
    n_zeros: int = 14,
    n_decoys: int = 12,
    max_ids: int = 2,
) -> dict[str, Any]:
    """Lightweight soft enrichment stamp (info only; never gates accept/pin)."""
    from realm.handoff.pipeline import enrichment_stamp

    rows = []
    for pid in list(pdb_ids)[: max(1, int(max_ids))]:
        try:
            row = enrichment_stamp(
                str(pid),
                knobs,
                n_zeros=int(n_zeros),
                n_decoys=int(n_decoys),
                n_seeds=1,
            )
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            rows.append({"pdb": pid, "status": "ERROR", "error": str(exc)})
    ok = [r for r in rows if r.get("status") == "OK" and "enrichment" in r]
    mean = None
    if ok:
        mean = float(sum(float(r["enrichment"]) for r in ok) / len(ok))
    return {
        "n_attempted": len(rows),
        "n_ok": len(ok),
        "mean_enrichment": mean,
        "rows": [
            {
                "pdb": r.get("pdb"),
                "status": r.get("status"),
                "enrichment": r.get("enrichment"),
            }
            for r in rows
        ],
        "note": "science channel informational only; never pin retune",
    }


def run_genotype_phase(
    founder_knobs: dict[str, Any],
    *,
    probe_ids: list[str],
    n_zeros: int = 14,
    n_pop: int = 4,
    n_epochs: int = 2,
    n_decoys: int = 12,
    soft_T: float = 0.04,
    defect_beta: float = 0.20,
    seed: int = 42,
) -> dict[str, Any]:
    """Optional NS micro-search on spectral knobs (never dual-gate pin).

    Sister to free-param negotiate: adapts genotype (Λ, ω, …) under probe
    enrichment dual fitness. Does not write LengthPolicy or soft_T pin.
    """
    import numpy as np

    from realm.adaptive_evolve import AdaptivePolicy, run_natural_selection
    from realm.lock_key import Keymaker

    # Prefer small probe set for speed
    probes = [str(p).upper() for p in probe_ids[:4]] or ["1CSA"]
    km = Keymaker(N=max(11, 7), n_zeros=int(n_zeros), n_sectors=6)
    g_last = float(km.forge().field.gammas[-1])
    rng = np.random.default_rng(int(seed))

    # Local import of probe builder from evolve_ns when available
    try:
        from evolve_ns import _probe_enrichment_fn

        probe_fn = _probe_enrichment_fn(
            probes,
            [],
            n_decoys=int(n_decoys),
            n_zeros=int(n_zeros),
            n_sectors=6,
            defect_beta=float(defect_beta),
            soft_T=float(soft_T),
            rng=rng,
        )
    except Exception:  # noqa: BLE001
        # Fallback: constant probe (no-op genotype)
        def probe_fn(_kn: dict) -> tuple[float, float | None]:
            return 0.0, None

    base_pe, _ = probe_fn(founder_knobs)
    policy = AdaptivePolicy(tau=0.08, r_soft_cap=0.015)
    ns = run_natural_selection(
        dict(founder_knobs),
        g_last=g_last,
        N=max(11, 7),
        n_zeros=int(n_zeros),
        n_sectors=6,
        n_pop=int(n_pop),
        n_epochs=int(n_epochs),
        policy=policy,
        probe_fn=probe_fn,
        rng=rng,
        log=lambda m: logger.info("genotype %s", m),
        until_resolved=False,
        max_epochs=int(n_epochs),
        min_epochs=1,
    )
    champ = ns.get("champion") or {}
    champ_kn = champ.get("knobs") or founder_knobs
    champ_pe = float(champ.get("probe_enrichment") or 0.0)
    improved = champ_pe > float(base_pe) + 1e-9
    return {
        "ontology": "coherence_genotype_phase_not_lambda_eq_gamma",
        "ran": True,
        "probe_ids": probes,
        "baseline_probe_enrichment": float(base_pe),
        "champion_probe_enrichment": champ_pe,
        "improved": improved,
        "champion_knobs": champ_kn if improved else dict(founder_knobs),
        "champion_F_total": champ.get("F_total"),
        "champion_R": champ.get("R"),
        "n_epochs_ran": ns.get("n_epochs_ran"),
        "stop_reason": ns.get("stop_reason"),
        "note": (
            "Genotype knobs only; dual-gate LengthPolicy pin never written. "
            "Champion accepted for re-export only if probe improved."
        ),
    }


def _utc_run_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_partner_recipe(
    path: Path | str,
    *,
    pin: dict[str, Any],
    free_params: FreeParams,
    run_id: str,
    pdb_ids: list[str],
    solved: bool,
) -> Path:
    """Machine-readable free-param recipe for partner re-run (not ACCEPTANCE)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "kind": "partner_recipe",
        "ontology": "partner_recipe_not_lambda_eq_gamma",
        "run_id": run_id,
        "solved": solved,
        "pin": {
            "ok": pin.get("ok"),
            "soft_T": pin.get("soft_T", 0.036),
            "expected_soft_T": 0.036,
            "seq_mix": pin.get("seq_mix", 0.0),
            "face_weight": pin.get("face_weight", 0.08),
            "note": "dual-gate pin locked; not negotiated by coherence OS",
        },
        "free_params": free_params.to_dict(),
        "pdb_ids": list(pdb_ids),
        "re_run_cli": (
            f"python handoff_campaign.py --pdb-ids {','.join(pdb_ids)} "
            f"--decorate {free_params.decorate} --physics {free_params.physics} "
            f"--top-k {free_params.top_k}"
        ),
        "disclaimers": [
            "PARTNER_RECIPE is free-param + pin stamp for re-run fidelity.",
            "Not ACCEPTANCE / not SHIP success.",
            "Commercial success remains openable PDBs + dual-gate pin.",
            "Never lambda=gamma.",
        ],
    }
    dest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return dest


def append_ledger(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def load_resume_state(run_dir: Path) -> dict[str, Any]:
    """Load RUN.json + ledger to resume OS batch."""
    run_path = run_dir / "RUN.json"
    if not run_path.is_file():
        raise FileNotFoundError(f"no RUN.json under {run_dir}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    ledger_path = run_dir / "ledger.jsonl"
    entries: list[dict[str, Any]] = []
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return {"run": run, "ledger": entries, "run_dir": run_dir}


def _write_run_json(out_root: Path, doc: dict[str, Any]) -> None:
    (out_root / "RUN.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )


def _write_latest_run_pointer(parent: Path, run_dir: Path) -> None:
    """Pointer file at OS parent: LATEST → run_id path."""
    parent.mkdir(parents=True, exist_ok=True)
    body = {
        "run_id": run_dir.name,
        "path": str(run_dir.resolve()),
        "ontology": "coherence_os_v2_latest_not_lambda_eq_gamma",
    }
    (parent / "LATEST").write_text(
        json.dumps(body, indent=2) + "\n", encoding="utf-8"
    )


def _aggregate_cycle_rollups(summary: dict[str, Any], cycle_dir: Path) -> None:
    """Fill decorate/physics rollups from child index.json if missing on batch."""
    if not summary.get("decorate_rollup") or not (
        summary.get("decorate_rollup") or {}
    ).get("n_molds"):
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
    with_science: bool = False,
    with_genotype: bool = False,
    genotype_epochs: int = 2,
    genotype_pop: int = 4,
    science_weak_threshold: float = 0.55,
    stability_k: int = 1,
    os_mode: bool = False,
    resume_dir: Path | str | None = None,
    run_id: str | None = None,
    with_dynamical_topology: bool = False,
) -> dict[str, Any]:
    """Execute cyclic observe→multi-section propose→merge→export until coherent.

    Dual-gate pin is re-checked every round and never written/adapted.
    Optional genotype phase runs after free-param loop if with_genotype and
    (not solved OR science soft enrichment below threshold).

    OS mode (os_mode=True): RUN.json, ledger.jsonl, stability-K fixed-point,
    PARTNER_RECIPE on SOLVED, optional resume.

    When ``with_dynamical_topology``: write out_root/DYNAMICAL_TOPOLOGY.json from
    ledger free-param stages (measure only; never pin / never ACCEPTANCE).

    Fixed-point (commercial routine): is_solved ∧ empty free-param board for
    K consecutive cycles (stability_k). Default K=1 matches legacy one-shot halt.
    """
    from realm.handoff.pipeline import export_structure_batch

    thr = thresholds or CoherenceThresholds()
    params = (initial or FreeParams()).clamp()
    out_root = Path(out_root)
    active_knobs = dict(knobs)
    stability_k = max(1, int(stability_k))
    parent_for_latest: Path | None = None

    # --- run directory (OS) ---
    resume_ledger: list[dict[str, Any]] = []
    start_round = 1
    tried: set[str] = set()
    stability_streak = 0
    run_doc: dict[str, Any] | None = None

    if resume_dir is not None:
        state = load_resume_state(Path(resume_dir))
        run_meta = state["run"]
        resume_ledger = list(state["ledger"])
        run_dir = Path(state["run_dir"])
        run_id = str(run_meta.get("run_id") or run_dir.name)
        # Prefer last next_params, else last params, else RUN.final_params
        params = FreeParams(
            **(run_meta.get("final_params") or params.to_dict())
        ).clamp()
        for e in reversed(resume_ledger):
            if e.get("next_params"):
                params = FreeParams(**e["next_params"]).clamp()
                break
            if e.get("params"):
                params = FreeParams(**e["params"]).clamp()
                break
        for e in resume_ledger:
            if e.get("params"):
                tried.add(json.dumps(e["params"], sort_keys=True))
            if e.get("next_params"):
                tried.add(json.dumps(e["next_params"], sort_keys=True))
            if e.get("stability_streak") is not None:
                stability_streak = int(e["stability_streak"])
        cycle_entries = [
            e for e in resume_ledger if isinstance(e.get("round"), int)
        ]
        start_round = len(cycle_entries) + 1
        max_rounds = int(run_meta.get("max_rounds") or max_rounds)
        os_mode = True
        out_root = run_dir
        parent_for_latest = out_root.parent
        thr = CoherenceThresholds(**(run_meta.get("thresholds") or thr.to_dict()))
        stability_k = max(1, int(run_meta.get("stability_k") or stability_k))
        with_science = bool(run_meta.get("with_science", with_science))
        with_genotype = bool(run_meta.get("with_genotype", with_genotype))
        if run_meta.get("pdb_ids"):
            pdb_ids = list(run_meta["pdb_ids"])
        run_doc = dict(run_meta)
        run_doc["status"] = "resuming"
        if run_meta.get("status") == "solved":
            logger.info(
                "resume already solved run_id=%s — re-emitting artifacts", run_id
            )
        logger.info(
            "resume run_id=%s start_round=%s budget=%s streak=%s",
            run_id,
            start_round,
            max_rounds,
            stability_streak,
        )
    else:
        if os_mode:
            rid = run_id or _utc_run_id()
            parent_for_latest = Path(out_root)
            out_root = Path(out_root) / rid
            run_id = rid
        else:
            run_id = run_id or "legacy"
        out_root.mkdir(parents=True, exist_ok=True)

    pin0 = verify_dual_gate_pin()
    ledger: list[dict[str, Any]] = list(resume_ledger)
    solved = False
    stop_reason = "max_rounds"
    last_science_enr: float | None = None
    partner_recipe_path: str | None = None

    # Early exit if resume of already-solved run
    if resume_dir is not None and any(
        e.get("action") == "halt" and e.get("solved") for e in resume_ledger
    ):
        solved = True
        stop_reason = "coherent"
        for e in reversed(resume_ledger):
            if e.get("params"):
                params = FreeParams(**e["params"]).clamp()
                break

    if os_mode and resume_dir is None:
        run_doc = {
            "run_id": run_id,
            "ontology": "coherence_os_v2_not_lambda_eq_gamma",
            "pdb_ids": list(pdb_ids),
            "thresholds": thr.to_dict(),
            "stability_k": stability_k,
            "max_rounds": int(max_rounds),
            "initial_params": params.to_dict(),
            "final_params": params.to_dict(),
            "with_science": bool(with_science),
            "with_genotype": bool(with_genotype),
            "pin_locked": {
                "soft_T_n12": 0.036,
                "seq_mix": 0.0,
                "face_weight": 0.08,
                "verified": pin0.get("ok"),
            },
            "n_rounds": 0,
            "status": "running",
            "stability_streak": 0,
        }
        _write_run_json(out_root, run_doc)
        (out_root / "ledger.jsonl").write_text("", encoding="utf-8")
        if parent_for_latest is not None:
            _write_latest_run_pointer(parent_for_latest, out_root)

    ledger_path = out_root / "ledger.jsonl"

    def _commit_entry(entry: dict[str, Any], cycle_dir: Path | None = None) -> None:
        ledger.append(entry)
        if os_mode:
            append_ledger(ledger_path, entry)
            if run_doc is not None:
                run_doc["n_rounds"] = len(
                    [e for e in ledger if isinstance(e.get("round"), int)]
                )
                run_doc["final_params"] = (
                    entry.get("next_params") or entry.get("params") or params.to_dict()
                )
                run_doc["stability_streak"] = int(entry.get("stability_streak") or 0)
                run_doc["status"] = (
                    "solved"
                    if entry.get("solved") and entry.get("action") == "halt"
                    else "running"
                )
                run_doc["last_round"] = entry.get("round")
                _write_run_json(out_root, run_doc)
        if cycle_dir is not None:
            cycle_dir.mkdir(parents=True, exist_ok=True)
            (cycle_dir / "coherence_round.json").write_text(
                json.dumps(entry, indent=2) + "\n", encoding="utf-8"
            )

    if not solved:
        for rnd in range(start_round, max(1, int(max_rounds)) + 1):
            cycle_dir = out_root / f"cycle_{rnd:02d}"
            pin = verify_dual_gate_pin()
            logger.info(
                "coherence cycle %s/%s decorate=%s physics=%s top_k=%s "
                "pin_ok=%s soft_T=%s streak=%s/%s os=%s",
                rnd,
                max_rounds,
                params.decorate,
                params.physics,
                params.top_k,
                pin.get("ok"),
                pin.get("soft_T"),
                stability_streak,
                stability_k,
                os_mode,
            )
            if thr.require_pin and not pin.get("ok"):
                stop_reason = "pin_fail"
                _commit_entry(
                    {
                        "round": rnd,
                        "params": params.to_dict(),
                        "pin": pin,
                        "solved": False,
                        "is_solved_slice": False,
                        "stability_streak": 0,
                        "action": "abort",
                        "reason": "dual_gate_pin_failed_locked",
                        "proposals": [],
                    },
                    cycle_dir,
                )
                break

            summary = export_structure_batch(
                list(pdb_ids),
                active_knobs,
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

            _aggregate_cycle_rollups(summary, cycle_dir)

            obs = observe(
                pin=pin,
                export_summary=summary,
                verify_report=vreport,
                out_dir=cycle_dir,
            )
            science_pack = None
            if with_science:
                try:
                    science_pack = _science_soft_probe(
                        list(pdb_ids), active_knobs, n_zeros=n_zeros
                    )
                    obs.science_soft_enrichment = science_pack.get("mean_enrichment")
                    obs.science_n_ok = int(science_pack.get("n_ok") or 0)
                    obs.science_n_attempted = int(
                        science_pack.get("n_attempted") or 0
                    )
                    last_science_enr = obs.science_soft_enrichment
                    (cycle_dir / "science_probe.json").write_text(
                        json.dumps(science_pack, indent=2) + "\n", encoding="utf-8"
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("science probe skipped: %s", exc)

            score = coherence_score(obs, thr, params)
            solved_slice = is_solved(obs, thr, params)
            # Mark current params tried; board for fixed-point uses untried moves
            tried.add(json.dumps(params.to_dict(), sort_keys=True))
            board_props = collect_section_proposals(
                obs, params, thr, tried=tried
            )
            # When already solved, free-param board is empty by negotiate contract
            if solved_slice:
                board_props = []
            empty_board = len(board_props) == 0

            if solved_slice and empty_board:
                stability_streak += 1
            else:
                stability_streak = 0

            entry: dict[str, Any] = {
                "round": rnd,
                "params": params.to_dict(),
                "observations": obs.to_dict(),
                "coherence_score": score,
                "is_solved_slice": solved_slice,
                "solved": False,
                "stability_streak": stability_streak,
                "stability_k": stability_k,
                "pin": {
                    "ok": pin.get("ok"),
                    "soft_T": pin.get("soft_T"),
                    "seq_mix": pin.get("seq_mix"),
                    "face_weight": pin.get("face_weight"),
                },
                "export_n_ok": summary.get("n_ok"),
                "export_n_ids": summary.get("n_ids"),
                "cycle_dir": str(cycle_dir.resolve()),
                "science_probe": science_pack,
                "proposals": [p.to_dict() for p in board_props],
            }

            # Fixed-point: is_solved ∧ empty board × K consecutive cycles
            if solved_slice and empty_board and stability_streak >= stability_k:
                entry["action"] = "halt"
                entry["reason"] = (
                    "fixed_point" if stability_k > 1 or os_mode else "coherent"
                )
                entry["solved"] = True
                entry["proposals"] = []
                _commit_entry(entry, cycle_dir)
                solved = True
                stop_reason = "coherent"
                logger.info(
                    "coherence SOLVED at round %s score=%.3f streak=%s/%s",
                    rnd,
                    score,
                    stability_streak,
                    stability_k,
                )
                break

            if solved_slice and empty_board and stability_streak < stability_k:
                entry["action"] = "stability_hold"
                entry["reason"] = f"streak_{stability_streak}_of_{stability_k}"
                entry["next_params"] = params.to_dict()
                _commit_entry(entry, cycle_dir)
                logger.info(
                    "stability hold round %s streak=%s/%s",
                    rnd,
                    stability_streak,
                    stability_k,
                )
                continue

            nxt, reason, board = negotiate(obs, params, thr, tried=tried)
            entry["action"] = "negotiate" if nxt is not None else "stuck"
            entry["reason"] = reason
            entry["proposals"] = board
            entry["next_params"] = nxt.to_dict() if nxt is not None else None
            _commit_entry(entry, cycle_dir)

            if nxt is None:
                stop_reason = reason
                logger.info("coherence stuck: %s", reason)
                break
            logger.info(
                "negotiate → %s (%s) board=%s",
                nxt.to_dict(),
                reason,
                [b.get("section") for b in board],
            )
            params = nxt

    # --- optional genotype phase (spectral knobs; never LengthPolicy pin) ---
    genotype_report: dict[str, Any] | None = None
    science_weak = (
        last_science_enr is not None
        and float(last_science_enr) < float(science_weak_threshold)
    )
    if with_genotype and (
        not solved
        or science_weak
        or (with_science and last_science_enr is None)
    ):
        logger.info(
            "genotype phase (NS micro-search) solved=%s science_enr=%s weak=%s",
            solved,
            last_science_enr,
            science_weak,
        )
        try:
            genotype_report = run_genotype_phase(
                active_knobs,
                probe_ids=list(pdb_ids),
                n_zeros=int(n_zeros),
                n_pop=int(genotype_pop),
                n_epochs=int(genotype_epochs),
            )
            (out_root / "GENOTYPE.json").write_text(
                json.dumps(genotype_report, indent=2) + "\n", encoding="utf-8"
            )
            if genotype_report.get("improved") and genotype_report.get(
                "champion_knobs"
            ):
                active_knobs = dict(genotype_report["champion_knobs"])
                val_dir = out_root / "cycle_genotype_validate"
                summary = export_structure_batch(
                    list(pdb_ids),
                    active_knobs,
                    out_root=val_dir,
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
                        val_dir,
                        require_sha256=False,
                        check_biopython=False,
                    )
                pin = verify_dual_gate_pin()
                obs = observe(
                    pin=pin,
                    export_summary=summary,
                    verify_report=vreport,
                    out_dir=val_dir,
                )
                solved_g = is_solved(obs, thr, params)
                g_entry = {
                    "round": "genotype",
                    "params": params.to_dict(),
                    "observations": obs.to_dict(),
                    "coherence_score": coherence_score(obs, thr, params),
                    "solved": solved_g,
                    "action": "genotype_validate",
                    "reason": (
                        "champion_knobs_applied"
                        if genotype_report.get("improved")
                        else "no_improvement"
                    ),
                    "genotype": {
                        "baseline": genotype_report.get(
                            "baseline_probe_enrichment"
                        ),
                        "champion": genotype_report.get(
                            "champion_probe_enrichment"
                        ),
                        "improved": genotype_report.get("improved"),
                    },
                    "pin": {
                        "ok": pin.get("ok"),
                        "soft_T": pin.get("soft_T"),
                    },
                    "cycle_dir": str(val_dir.resolve()),
                }
                _commit_entry(g_entry, val_dir)
                if solved_g:
                    solved = True
                    stop_reason = "coherent_after_genotype"
                elif not solved:
                    stop_reason = "genotype_did_not_solve"
            else:
                _commit_entry(
                    {
                        "round": "genotype",
                        "action": "genotype_no_improvement",
                        "reason": "champion_not_better_than_baseline",
                        "genotype": genotype_report,
                        "solved": solved,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("genotype phase failed")
            genotype_report = {"ran": True, "error": str(exc), "improved": False}
            _commit_entry(
                {
                    "round": "genotype",
                    "action": "genotype_error",
                    "reason": str(exc),
                    "solved": solved,
                }
            )

    # PARTNER_RECIPE on commercial fixed-point (OS mode or any solved)
    if solved:
        pin_final = verify_dual_gate_pin()
        recipe_path = out_root / "PARTNER_RECIPE.json"
        write_partner_recipe(
            recipe_path,
            pin=pin_final,
            free_params=params,
            run_id=str(run_id),
            pdb_ids=list(pdb_ids),
            solved=True,
        )
        partner_recipe_path = str(recipe_path.resolve())

    if os_mode and run_doc is not None:
        run_doc["status"] = "solved" if solved else stop_reason
        run_doc["stop_reason"] = stop_reason
        run_doc["final_params"] = params.to_dict()
        run_doc["n_rounds"] = len(
            [e for e in ledger if isinstance(e.get("round"), int)]
        )
        run_doc["stability_streak"] = stability_streak
        run_doc["partner_recipe"] = partner_recipe_path
        _write_run_json(out_root, run_doc)
        if parent_for_latest is not None:
            _write_latest_run_pointer(parent_for_latest, out_root)

    result = {
        "ontology": (
            "coherence_os_v2_not_lambda_eq_gamma"
            if os_mode
            else "handoff_coherence_protocol_not_lambda_eq_gamma"
        ),
        "run_id": run_id,
        "os_mode": bool(os_mode),
        "stability_k": stability_k,
        "stability_streak": stability_streak,
        "solved": solved,
        "stop_reason": stop_reason,
        "n_rounds": len([e for e in ledger if isinstance(e.get("round"), int)]),
        "max_rounds": int(max_rounds),
        "with_science": bool(with_science),
        "with_genotype": bool(with_genotype),
        "genotype": genotype_report,
        "thresholds": thr.to_dict(),
        "final_params": params.to_dict(),
        "final_knobs_source": (
            "genotype_champion"
            if genotype_report and genotype_report.get("improved")
            else "founder"
        ),
        "partner_recipe": partner_recipe_path,
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
        "with_dynamical_topology": bool(with_dynamical_topology),
        "dynamical_topology": None,
        "dynamical_topology_path": None,
        "note": (
            "Cyclic observe→multi-section propose→merge→export "
            "(+ optional genotype NS micro-search). "
            "Fixed-point: is_solved ∧ empty board × K. "
            "Free params: decorate/physics/top_k. "
            "Genotype: spectral knobs only. "
            "Dual-gate pin locked. Science informational. "
            "Not enrichment score-chase. Never lambda=gamma."
        ),
    }

    # Optional dynamical topology MEASURE (ledger free-param stages only)
    if with_dynamical_topology:
        try:
            from realm.dynamical_topology.stages_handoff import (
                build_stages_from_handoff_ledger,
            )
            from realm.dynamical_topology.engine import run_dynamical_topology

            stages = build_stages_from_handoff_ledger(ledger)
            rep = run_dynamical_topology(stages)
            dt_path = Path(out_root) / "DYNAMICAL_TOPOLOGY.json"
            dt_path.write_text(
                json.dumps(rep, indent=2) + "\n", encoding="utf-8"
            )
            result["dynamical_topology"] = rep
            result["dynamical_topology_path"] = str(dt_path.resolve())
            logger.info(
                "handoff dynamical topology n_stages=%s n_long=%s path=%s",
                rep.get("n_stages"),
                rep.get("n_long"),
                result["dynamical_topology_path"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("handoff dynamical topology measure skipped: %s", exc)
            result["dynamical_topology"] = {
                "kind": "dynamical_topology",
                "not_acceptance": True,
                "pin_writable": False,
                "acceptance_writable": False,
                "error": str(exc),
                "n_stages": 0,
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
        f"- **run_id:** `{result.get('run_id')}`",
        f"- **os_mode:** `{result.get('os_mode')}`",
        f"- **stability-K:** `{result.get('stability_k')}` "
        f"(streak={result.get('stability_streak')})",
        f"- **rounds:** {result.get('n_rounds')} / {result.get('max_rounds')}",
        f"- **final free params:** `{result.get('final_params')}`",
        f"- **knobs source:** `{result.get('final_knobs_source')}`",
        f"- **partner_recipe:** `{result.get('partner_recipe')}`",
        f"- **pin locked:** soft_T(n=12)=**0.036** (never adapted)",
        f"- **genotype:** `{bool(result.get('with_genotype'))}` "
        f"improved=`{(result.get('genotype') or {}).get('improved')}`",
        "",
        "Commercial accept remains openable PDBs + dual-gate pin — not this loop's score.",
        "Fixed-point = is_solved ∧ empty free-param board × K consecutive cycles.",
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
    lines.extend(["", "## Proposal boards (multi-section)", ""])
    for e in result.get("ledger") or []:
        board = e.get("proposals") or []
        if not board:
            continue
        lines.append(f"### Round {e.get('round')}")
        lines.append("")
        for pr in board:
            lines.append(
                f"- **{pr.get('section')}** (pri={pr.get('priority')}): "
                f"`{pr.get('reason')}` → `{pr.get('params')}`"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
