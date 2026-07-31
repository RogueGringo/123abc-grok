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
) -> dict[str, Any]:
    """Execute cyclic observe→multi-section propose→merge→export until coherent.

    Dual-gate pin is re-checked every round and never written/adapted.
    Optional genotype phase runs after free-param loop if with_genotype and
    (not solved OR science soft enrichment below threshold).
    """
    from realm.handoff.pipeline import export_structure_batch

    thr = thresholds or CoherenceThresholds()
    params = (initial or FreeParams()).clamp()
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    active_knobs = dict(knobs)

    pin0 = verify_dual_gate_pin()
    ledger: list[dict[str, Any]] = []
    tried: set[str] = set()
    solved = False
    stop_reason = "max_rounds"
    last_science_enr: float | None = None

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
        science_pack = None
        if with_science:
            try:
                science_pack = _science_soft_probe(
                    list(pdb_ids), active_knobs, n_zeros=n_zeros
                )
                obs.science_soft_enrichment = science_pack.get("mean_enrichment")
                obs.science_n_ok = int(science_pack.get("n_ok") or 0)
                obs.science_n_attempted = int(science_pack.get("n_attempted") or 0)
                last_science_enr = obs.science_soft_enrichment
                (cycle_dir / "science_probe.json").write_text(
                    json.dumps(science_pack, indent=2) + "\n", encoding="utf-8"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("science probe skipped: %s", exc)

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
            "science_probe": science_pack,
        }

        if solved:
            entry["action"] = "halt"
            entry["reason"] = "coherent"
            entry["proposals"] = []
            ledger.append(entry)
            stop_reason = "coherent"
            logger.info("coherence SOLVED at round %s score=%.3f", rnd, score)
            break

        nxt, reason, board = negotiate(obs, params, thr, tried=tried)
        entry["action"] = "negotiate" if nxt is not None else "stuck"
        entry["reason"] = reason
        entry["proposals"] = board
        entry["next_params"] = nxt.to_dict() if nxt is not None else None
        ledger.append(entry)
        (cycle_dir / "coherence_round.json").write_text(
            json.dumps(entry, indent=2) + "\n", encoding="utf-8"
        )

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
                # Re-export one validation cycle with free params + new genotype
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
                ledger.append(
                    {
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
                )
                if solved_g:
                    solved = True
                    stop_reason = "coherent_after_genotype"
                elif solved:
                    stop_reason = stop_reason  # keep prior
                else:
                    stop_reason = "genotype_did_not_solve"
            else:
                ledger.append(
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
            ledger.append(
                {
                    "round": "genotype",
                    "action": "genotype_error",
                    "reason": str(exc),
                    "solved": solved,
                }
            )

    result = {
        "ontology": "handoff_coherence_protocol_not_lambda_eq_gamma",
        "solved": solved,
        "stop_reason": stop_reason,
        "n_rounds": len(ledger),
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
            "Cyclic observe→multi-section propose→merge→export "
            "(+ optional genotype NS micro-search). "
            "Free params: decorate/physics/top_k. "
            "Genotype: spectral knobs only. "
            "Dual-gate pin locked. Science informational. "
            "Not enrichment score-chase. Never lambda=gamma."
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
        f"- **knobs source:** `{result.get('final_knobs_source')}`",
        f"- **pin locked:** soft_T(n=12)=**0.036** (never adapted)",
        f"- **genotype:** `{bool(result.get('with_genotype'))}` "
        f"improved=`{(result.get('genotype') or {}).get('improved')}`",
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
