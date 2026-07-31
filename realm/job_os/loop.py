"""Job Coherence OS loop: observe → multi-section propose → merge → re-execute.

OS mode: RUN.json, ledger.jsonl, stability-K fixed-point, PARTNER_RECIPE on SOLVED,
optional resume.

Fixed-point: is_solved ∧ empty free-param board for K consecutive cycles.
Pin re-checked every round and never written/adapted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from realm.job_os.ingest_las import apply_null_policy, parse_las, select_channel_pack
from realm.job_os.observe import coherence_score, is_solved, observe_job
from realm.job_os.pin import verify_job_pin
from realm.job_os.propose import collect_section_proposals, negotiate
from realm.job_os.types import FreeParams, JobThresholds

logger = logging.getLogger(__name__)


def _utc_run_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_partner_recipe(
    path: Path | str,
    *,
    pin: dict[str, Any],
    free_params: FreeParams,
    run_id: str,
    las_path: str | None,
    solved: bool,
) -> Path:
    """Machine-readable free-param recipe for partner re-run (not ACCEPTANCE)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "kind": "partner_recipe",
        "ontology": "job_partner_recipe_not_rop_score",
        "run_id": run_id,
        "solved": solved,
        "pin": {
            "ok": pin.get("ok"),
            "depth_mono_ok": pin.get("depth_mono_ok"),
            "unit_sanity_ok": pin.get("unit_sanity_ok"),
            "required_channels": pin.get("required_channels"),
            "missing_channels": pin.get("missing_channels"),
            "reasons": pin.get("reasons"),
            "note": "QC pin locked; not negotiated by job coherence OS",
        },
        "free_params": free_params.to_dict(),
        "las_path": las_path,
        "re_run_cli": (
            f"python job_coherence.py --os --las {las_path or '<LAS>'} "
            f"--align-mode {free_params.align_mode} "
            f"--window-scale {free_params.window_scale} "
            f"--channel-pack {free_params.channel_pack} "
            f"--null-policy {free_params.null_policy}"
        ),
        "disclaimers": [
            "PARTNER_RECIPE is free-param + pin stamp for re-run fidelity.",
            "Not ACCEPTANCE / not SHIP success / not ROP prediction.",
            "Commercial success remains gluing sources + QC pin.",
            "Never retune SOP pin for score. Never ζ→ROP claim.",
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
    parent.mkdir(parents=True, exist_ok=True)
    body = {
        "run_id": run_dir.name,
        "path": str(run_dir.resolve()),
        "ontology": "job_coherence_os_v1_latest_not_rop",
    }
    (parent / "LATEST").write_text(
        json.dumps(body, indent=2) + "\n", encoding="utf-8"
    )


def _write_coherence_md(result: dict[str, Any], path: Path) -> Path:
    lines = [
        "# Job Coherence OS ledger",
        "",
        f"- **solved:** {result.get('solved')}",
        f"- **stop:** `{result.get('stop_reason')}`",
        f"- **run_id:** `{result.get('run_id')}`",
        f"- **os_mode:** `{result.get('os_mode')}`",
        f"- **stability_k:** {result.get('stability_k')}",
        f"- **n_rounds:** {result.get('n_rounds')}",
        f"- **final_params:** `{json.dumps(result.get('final_params') or {})}`",
        f"- **partner_recipe:** `{result.get('partner_recipe')}`",
        "",
        "## Ontology",
        "",
        "- Substrate: raw multi-channel series",
        "- Pin: QC locked (depth mono, required channels, unit sanity)",
        "- Free: align_mode, window_scale, channel_pack, null_policy",
        "- Fixed-point: is_solved ∧ empty board × K",
        "- Never retune pin for score. Never ζ→ROP.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def execute_job_cycle(
    *,
    las_path: Path | str,
    params: FreeParams,
    thr: JobThresholds,
    cycle_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Ingest LAS → null policy → pack select → pin → observe."""
    cycle_dir.mkdir(parents=True, exist_ok=True)
    p = params.clamp()
    raw = parse_las(las_path)
    series = apply_null_policy(raw, p.null_policy)
    series = select_channel_pack(series, p.channel_pack)

    pin = verify_job_pin(
        series,
        pack=p.channel_pack,
        depth_mono_eps=float(thr.depth_mono_eps),
    )
    (cycle_dir / "pin.json").write_text(
        json.dumps(pin, indent=2) + "\n", encoding="utf-8"
    )
    # Store lightweight series summary (not full arrays in json for large files)
    summary = {
        "n_rows": series.get("n_rows"),
        "curve_names": series.get("curve_names"),
        "channel_pack": p.channel_pack,
        "null_policy": p.null_policy,
        "align_mode": p.align_mode,
        "source_path": series.get("source_path"),
        "units": series.get("units"),
        "n_channels": len(series.get("channels") or {}),
        "pack_required": series.get("pack_required"),
    }
    (cycle_dir / "sources_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    obs = observe_job(
        series=series,
        params=p,
        thr=thr,
        out_dir=cycle_dir,
        pin=pin,
    )
    (cycle_dir / "observations.json").write_text(
        json.dumps(obs.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return pin, summary, obs


def run_job_coherence_loop(
    *,
    las_path: Path | str | None = None,
    out_root: Path | str = "out/job_os",
    initial: FreeParams | None = None,
    thresholds: JobThresholds | None = None,
    max_rounds: int = 6,
    stability_k: int = 1,
    os_mode: bool = False,
    resume_dir: Path | str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute cyclic observe→multi-section propose→merge→ingest until coherent.

    QC pin is re-checked every round and never written/adapted.

    OS mode (os_mode=True): RUN.json, ledger.jsonl, stability-K fixed-point,
    PARTNER_RECIPE on SOLVED, optional resume.

    Fixed-point: is_solved ∧ empty free-param board for K consecutive cycles.
    """
    thr = thresholds or JobThresholds()
    params = (initial or FreeParams()).clamp()
    out_root = Path(out_root)
    stability_k = max(1, int(stability_k))
    parent_for_latest: Path | None = None

    resume_ledger: list[dict[str, Any]] = []
    start_round = 1
    tried: set[str] = set()
    stability_streak = 0
    run_doc: dict[str, Any] | None = None
    las_str: str | None = str(las_path) if las_path is not None else None

    if resume_dir is not None:
        state = load_resume_state(Path(resume_dir))
        run_meta = state["run"]
        resume_ledger = list(state["ledger"])
        run_dir = Path(state["run_dir"])
        run_id = str(run_meta.get("run_id") or run_dir.name)
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
        cycle_entries = [e for e in resume_ledger if isinstance(e.get("round"), int)]
        start_round = len(cycle_entries) + 1
        max_rounds = int(run_meta.get("max_rounds") or max_rounds)
        os_mode = True
        out_root = run_dir
        parent_for_latest = out_root.parent
        thr = JobThresholds(**(run_meta.get("thresholds") or thr.to_dict()))
        stability_k = max(1, int(run_meta.get("stability_k") or stability_k))
        if run_meta.get("las_path"):
            las_str = str(run_meta["las_path"])
            las_path = las_str
        run_doc = dict(run_meta)
        run_doc["status"] = "resuming"
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

    if las_path is None and las_str is None:
        raise ValueError("las_path required (or resume RUN.json with las_path)")
    las_path = Path(las_str or las_path)  # type: ignore[arg-type]
    if not las_path.is_file():
        raise FileNotFoundError(f"LAS not found: {las_path}")
    las_str = str(las_path.resolve())

    ledger: list[dict[str, Any]] = list(resume_ledger)
    solved = False
    stop_reason = "max_rounds"
    partner_recipe_path: str | None = None
    pin0: dict[str, Any] = {"ok": None}

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
            "ontology": "job_coherence_os_p1_not_rop_score",
            "las_path": las_str,
            "thresholds": thr.to_dict(),
            "stability_k": stability_k,
            "max_rounds": int(max_rounds),
            "initial_params": params.to_dict(),
            "final_params": params.to_dict(),
            "pin_locked": {
                "depth_mono": True,
                "required_channels_for_pack": True,
                "unit_sanity": True,
                "note": "QC pin never negotiated",
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
            logger.info(
                "job cycle %s/%s align=%s pack=%s null=%s window=%s streak=%s/%s os=%s",
                rnd,
                max_rounds,
                params.align_mode,
                params.channel_pack,
                params.null_policy,
                params.window_scale,
                stability_streak,
                stability_k,
                os_mode,
            )

            pin, summary, obs = execute_job_cycle(
                las_path=las_path,
                params=params,
                thr=thr,
                cycle_dir=cycle_dir,
            )
            pin0 = pin

            if thr.require_pin and not pin.get("ok"):
                # Pin fail: abort negotiate; may still try free moves only if
                # pin can recover via pack/null? Spec: pin locked fail cannot
                # negotiate when require_pin — but pack choice affects pin
                # (required channels). That is free-param channel_pack, not pin
                # threshold retune. allow negotiate when missing_channels only.
                missing_only = (
                    not pin.get("depth_mono_ok")
                    or not pin.get("unit_sanity_ok")
                )
                # Hard pin fails (mono / unit) cannot negotiate
                if missing_only and (
                    not pin.get("depth_mono_ok") or not pin.get("unit_sanity_ok")
                ):
                    # If depth/unit hard fail → abort
                    stop_reason = "pin_fail"
                    _commit_entry(
                        {
                            "round": rnd,
                            "params": params.to_dict(),
                            "pin": {
                                "ok": pin.get("ok"),
                                "reasons": pin.get("reasons"),
                                "depth_mono_ok": pin.get("depth_mono_ok"),
                                "unit_sanity_ok": pin.get("unit_sanity_ok"),
                            },
                            "observations": obs.to_dict(),
                            "solved": False,
                            "is_solved_slice": False,
                            "stability_streak": 0,
                            "action": "abort",
                            "reason": "job_qc_pin_failed_locked",
                            "proposals": [],
                        },
                        cycle_dir,
                    )
                    break

            score = coherence_score(obs, thr, params)
            solved_slice = is_solved(obs, thr, params)
            tried.add(json.dumps(params.to_dict(), sort_keys=True))
            board_props = collect_section_proposals(obs, params, thr, tried=tried)
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
                    "reasons": pin.get("reasons"),
                    "depth_mono_ok": pin.get("depth_mono_ok"),
                    "unit_sanity_ok": pin.get("unit_sanity_ok"),
                    "missing_channels": pin.get("missing_channels"),
                },
                "export_ok_fraction": obs.export_ok_fraction,
                "n_rows": obs.n_rows,
                "cycle_dir": str(cycle_dir.resolve()),
                "proposals": [pr.to_dict() for pr in board_props],
                "sources": summary,
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
                    "job SOLVED at round %s score=%.3f streak=%s/%s",
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

            # Pin hard fail (depth/unit) already aborted; missing channels can negotiate
            if thr.require_pin and not pin.get("ok"):
                if not pin.get("depth_mono_ok") or not pin.get("unit_sanity_ok"):
                    stop_reason = "pin_fail"
                    entry["action"] = "abort"
                    entry["reason"] = "job_qc_pin_failed_locked"
                    entry["proposals"] = []
                    _commit_entry(entry, cycle_dir)
                    break

            nxt, reason, board = negotiate(obs, params, thr, tried=tried)
            # negotiate returns pin_locked when pin not ok — but for missing channels
            # only, pin.ok is False; we still want pack negotiation.
            if (
                nxt is None
                and reason == "pin_locked_fail_cannot_negotiate"
                and pin.get("missing_channels")
                and pin.get("depth_mono_ok")
                and pin.get("unit_sanity_ok")
            ):
                # Temporarily allow proposals despite pin.ok False (pack incompleteness)
                proposals = collect_section_proposals(obs, params, thr, tried=tried)
                from realm.job_os.propose import merge_proposals

                nxt, reason, board = merge_proposals(proposals, params)
                if nxt is not None:
                    tried.add(json.dumps(nxt.to_dict(), sort_keys=True))

            entry["action"] = "negotiate" if nxt is not None else "stuck"
            entry["reason"] = reason
            entry["proposals"] = board
            entry["next_params"] = nxt.to_dict() if nxt is not None else None
            _commit_entry(entry, cycle_dir)

            if nxt is None:
                stop_reason = reason
                logger.info("job coherence stuck: %s", reason)
                break
            logger.info(
                "negotiate → %s (%s) board=%s",
                nxt.to_dict(),
                reason,
                [b.get("section") for b in board],
            )
            params = nxt

    # PARTNER_RECIPE on commercial fixed-point
    if solved:
        # Re-verify pin at final params
        pin_final, _, _ = execute_job_cycle(
            las_path=las_path,
            params=params,
            thr=thr,
            cycle_dir=out_root / "cycle_final_pin",
        )
        recipe_path = out_root / "PARTNER_RECIPE.json"
        write_partner_recipe(
            recipe_path,
            pin=pin_final,
            free_params=params,
            run_id=str(run_id),
            las_path=las_str,
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
            "job_coherence_os_p1_not_rop_score"
            if os_mode
            else "job_coherence_protocol_not_rop_score"
        ),
        "run_id": run_id,
        "os_mode": bool(os_mode),
        "stability_k": stability_k,
        "stability_streak": stability_streak,
        "solved": solved,
        "stop_reason": stop_reason,
        "n_rounds": len([e for e in ledger if isinstance(e.get("round"), int)]),
        "max_rounds": int(max_rounds),
        "thresholds": thr.to_dict(),
        "final_params": params.to_dict(),
        "partner_recipe": partner_recipe_path,
        "pin_locked": {
            "depth_mono": True,
            "required_channels_for_pack": True,
            "unit_sanity": True,
            "last_ok": pin0.get("ok"),
            "note": "QC pin never negotiated by this protocol",
        },
        "ledger": ledger,
        "out_root": str(out_root.resolve()),
        "las_path": las_str,
        "note": (
            "Cyclic observe→multi-section propose→merge→ingest. "
            "Fixed-point: is_solved ∧ empty board × K. "
            "Free params: align_mode/window_scale/channel_pack/null_policy. "
            "QC pin locked. Not ROP score-chase. Never ζ→ROP."
        ),
    }
    (out_root / "COHERENCE.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _write_coherence_md(result, out_root / "COHERENCE.md")
    return result
