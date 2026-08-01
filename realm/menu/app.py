"""Realm navigator menu: Job OS smoke/wizard, catalog, dynamical topology, docs.

Pure builders (menu_items, build_job_smoke_argv, build_job_wizard_kwargs) are
unit-tested without interactive input. main() is the interactive loop.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

from realm.dynamical_topology.engine import run_dynamical_topology
from realm.dynamical_topology.stages_job import build_stages_from_job_run
from realm.job_os.catalog import write_job_os_catalog
from realm.job_os.loop import run_job_coherence_loop
from realm.job_os.rotation import run_job_rotation
from realm.job_os.types import FreeParams, JobThresholds

# Repo root (…/123abc-grok) — menu lives at realm/menu/app.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LAS = _REPO_ROOT / "tests" / "fixtures" / "mini_edr.las"
_DEFAULT_JOB_OS_ROOT = Path("out/job_os")
_DEFAULT_ROTATION_MANIFEST = (
    _REPO_ROOT / "docs" / "examples" / "job_rotation_jtod1.manifest.json"
)
_DOCS_JOB_OS = Path("docs/JOB_OS.md")
_DOCS_DESIGN = Path(
    "docs/superpowers/specs/2026-07-31-dynamical-topology-dual-spine-design.md"
)
_DOCS_BRIDGE = Path(
    "docs/superpowers/specs/2026-07-31-dual-stalk-ops-bridge-design.md"
)


def menu_items() -> list[dict[str, str]]:
    """Top-level navigator entries: id + label (order is display order)."""
    return [
        {"id": "job_smoke", "label": "Job OS — fixture quick smoke"},
        {"id": "job_wizard", "label": "Job OS — custom paths (wizard)"},
        {"id": "catalog", "label": "Catalog runs (INDEX)"},
        {"id": "rotation", "label": "Multi-well rotation (manifest)"},
        {"id": "topology", "label": "Dynamical topology report"},
        {"id": "handoff", "label": "Handoff coherence (protein)"},
        {"id": "docs", "label": "Open docs / LATEST paths"},
        {"id": "exit", "label": "Exit"},
    ]


def build_rotation_argv(
    manifest: str | Path,
    out_dir: str | Path = "out/rotation",
    *,
    dry_run: bool = False,
) -> list[str]:
    """Subprocess argv for multi-well rotation (firewall-certified branch)."""
    argv = [
        sys.executable,
        "job_coherence.py",
        "--rotation",
        str(manifest),
        "--out-dir",
        str(out_dir),
    ]
    if dry_run:
        argv.append("--rotation-dry-run")
    return argv


def build_job_smoke_argv(out_dir: str) -> list[str]:
    """Subprocess argv for Job OS fixture smoke (Windows-friendly full command).

    Equivalent to the smoke path run_job_smoke uses in-process.
    """
    las = "tests/fixtures/mini_edr.las"
    return [
        sys.executable,
        "job_coherence.py",
        "--os",
        "--las",
        las,
        "--channel-pack",
        "surface_min",
        "--regime-mode",
        "persist_h0",
        "--with-regime",
        "--with-dynamical-topology",
        "--out-dir",
        str(out_dir),
        "--run-id",
        "menu_smoke",
        "--stability-k",
        "1",
        "--max-rounds",
        "3",
    ]


def build_job_wizard_kwargs(
    *,
    las_path: str | Path | None,
    micropulse_path: str | Path | None = None,
    survey_path: str | Path | None = None,
    out_root: str | Path = "out/job_os",
    run_id: str | None = None,
    max_rounds: int = 6,
    stability_k: int = 1,
    channel_pack: str = "surface_min",
    regime_mode: str = "persist_h0",
    with_regime: bool = True,
    with_science: bool = False,
    with_dynamical_topology: bool = True,
    topo_stability: bool = False,
    eow_package: str | Path | None = None,
    force_ship: bool = False,
    chunk_rows: int | None = None,
    max_chunks: int = 32,
    max_rows: int | None = None,
    max_depth_mono_violations: int = 0,
) -> dict[str, Any]:
    """Pure kwargs for run_job_coherence_loop from wizard answers.

    Pin is never editable: thresholds only carry config defaults (not free knobs).
    """
    thr = JobThresholds(
        min_export_ok_fraction=1.0,
        max_physics_fail=0,
        min_align_score=0.5,
        require_verify_ok=True,
        require_pin=True,
        max_depth_mono_violations=int(max_depth_mono_violations),
    )
    return {
        "las_path": las_path,
        "micropulse_path": micropulse_path,
        "survey_path": survey_path,
        "out_root": out_root,
        "initial": FreeParams(
            channel_pack=str(channel_pack or "surface_min"),
            regime_mode=str(regime_mode or "off"),
        ),
        "thresholds": thr,
        "max_rounds": int(max_rounds),
        "stability_k": int(stability_k),
        "os_mode": True,
        "run_id": run_id,
        "with_regime": bool(with_regime),
        "with_science": bool(with_science),
        "with_dynamical_topology": bool(with_dynamical_topology),
        "topo_stability": bool(topo_stability),
        "eow_package": eow_package,
        "force_ship": bool(force_ship),
        "chunk_rows": chunk_rows,
        "max_chunks": int(max_chunks),
        "max_rows": max_rows,
    }


def wizard_kwargs_to_cli(kwargs: dict[str, Any]) -> str:
    """Human-readable equivalent CLI one-liner (for confirm screen)."""
    parts: list[str] = [
        "python",
        "job_coherence.py",
        "--os",
    ]
    las = kwargs.get("las_path")
    if las is not None:
        parts.extend(["--las", str(las)])
    mp = kwargs.get("micropulse_path")
    if mp is not None:
        parts.extend(["--micropulse", str(mp)])
    survey = kwargs.get("survey_path")
    if survey is not None:
        parts.extend(["--survey", str(survey)])
    out_root = kwargs.get("out_root") or "out/job_os"
    parts.extend(["--out-dir", str(out_root)])
    run_id = kwargs.get("run_id")
    if run_id:
        parts.extend(["--run-id", str(run_id)])
    parts.extend(["--max-rounds", str(int(kwargs.get("max_rounds") or 6))])
    parts.extend(["--stability-k", str(int(kwargs.get("stability_k") or 1))])
    initial = kwargs.get("initial")
    if isinstance(initial, FreeParams):
        parts.extend(["--channel-pack", str(initial.channel_pack)])
        parts.extend(["--regime-mode", str(initial.regime_mode)])
    if kwargs.get("with_regime"):
        parts.append("--with-regime")
    if kwargs.get("with_science"):
        parts.append("--with-science")
    if kwargs.get("with_dynamical_topology"):
        parts.append("--with-dynamical-topology")
    if kwargs.get("topo_stability"):
        parts.append("--topo-stability")
    eow = kwargs.get("eow_package")
    if eow is not None:
        parts.extend(["--eow-package", str(eow)])
    if kwargs.get("force_ship"):
        parts.append("--force-ship")
    chunk = kwargs.get("chunk_rows")
    if chunk is not None:
        parts.extend(["--chunk-rows", str(int(chunk))])
        parts.extend(["--max-chunks", str(int(kwargs.get("max_chunks") or 32))])
    max_rows = kwargs.get("max_rows")
    if max_rows is not None:
        parts.extend(["--max-rows", str(int(max_rows))])
    thr = kwargs.get("thresholds")
    if isinstance(thr, JobThresholds) and int(thr.max_depth_mono_violations) != 0:
        parts.extend(
            [
                "--max-depth-mono-violations",
                str(int(thr.max_depth_mono_violations)),
            ]
        )
    # Quote for display on Windows / shells
    try:
        return " ".join(shlex.quote(p) for p in parts)
    except Exception:
        return " ".join(parts)


def run_job_smoke(
    out_dir: str | Path = "out/job_os",
    *,
    las_path: str | Path | None = None,
) -> dict[str, Any]:
    """In-process Job OS fixture smoke (prefer over subprocess)."""
    las = Path(las_path) if las_path is not None else _DEFAULT_LAS
    if not las.is_file():
        # Fall back to cwd-relative fixture path
        las = Path("tests/fixtures/mini_edr.las")
    kwargs = build_job_wizard_kwargs(
        las_path=las,
        out_root=out_dir,
        run_id="menu_smoke",
        max_rounds=3,
        stability_k=1,
        channel_pack="surface_min",
        regime_mode="persist_h0",
        with_regime=True,
        with_dynamical_topology=True,
        topo_stability=False,
    )
    return run_job_coherence_loop(**kwargs)


def _print_run_summary(result: dict[str, Any], stream: TextIO = sys.stdout) -> None:
    out = result.get("out_root") or result.get("run_dir") or ""
    print(
        json.dumps(
            {
                "solved": result.get("solved"),
                "stop_reason": result.get("stop_reason"),
                "out": str(out),
                "run_id": result.get("run_id"),
                "n_rounds": result.get("n_rounds"),
                "dynamical_topology": (
                    {
                        "n_stages": (result.get("dynamical_topology") or {}).get(
                            "n_stages"
                        ),
                        "n_long": (result.get("dynamical_topology") or {}).get(
                            "n_long"
                        ),
                    }
                    if result.get("dynamical_topology") is not None
                    else None
                ),
                "note": "menu path — pin never retuned; not ACCEPTANCE",
            },
            indent=2,
        ),
        file=stream,
    )


def resolve_job_os_latest(job_os_root: Path | str = _DEFAULT_JOB_OS_ROOT) -> Path | None:
    """Resolve out/job_os/LATEST → run directory if present.

    LATEST is JSON ``{"run_id", "path", ...}`` written by Job OS; also accepts
    a plain run_id or absolute path string for resilience.
    """
    root = Path(job_os_root)
    latest = root / "LATEST"
    if not latest.is_file():
        return None
    text = latest.read_text(encoding="utf-8").strip()
    if not text:
        return None
    path_s: str | None = None
    run_id: str | None = None
    try:
        body = json.loads(text)
        if isinstance(body, dict):
            path_s = body.get("path")
            run_id = body.get("run_id")
        elif isinstance(body, str):
            path_s = body
    except json.JSONDecodeError:
        path_s = text
    candidates: list[Path] = []
    if path_s:
        candidates.append(Path(str(path_s)))
    if run_id:
        candidates.append(root / str(run_id))
    if path_s and not Path(str(path_s)).is_absolute():
        candidates.append(root / str(path_s))
    for cand in candidates:
        if cand.is_dir():
            return cand
    return None


def run_topology_report(
    run_dir: Path | str,
    *,
    write_path: Path | str | None = None,
) -> dict[str, Any]:
    """build_stages_from_job_run + run_dynamical_topology; optionally write JSON."""
    root = Path(run_dir)
    stages = build_stages_from_job_run(root)
    report = run_dynamical_topology(stages)
    out = write_path
    if out is None:
        out = root / "DYNAMICAL_TOPOLOGY.json"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report = dict(report)
    report["_path"] = str(out)
    return report


def _prompt(msg: str, default: str = "", *, inp: Callable[[str], str] | None = None) -> str:
    read = inp or input
    suffix = f" [{default}]" if default else ""
    raw = read(f"{msg}{suffix}: ").strip()
    return raw if raw else default


def _prompt_yn(
    msg: str,
    default: bool = False,
    *,
    inp: Callable[[str], str] | None = None,
) -> bool:
    d = "Y" if default else "N"
    raw = _prompt(f"{msg} (Y/N)", d, inp=inp).strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "true")


def _prompt_int(
    msg: str,
    default: int,
    *,
    inp: Callable[[str], str] | None = None,
) -> int:
    raw = _prompt(msg, str(default), inp=inp)
    try:
        return int(raw)
    except ValueError:
        return int(default)


def _optional_path(
    msg: str,
    *,
    inp: Callable[[str], str] | None = None,
) -> Path | None:
    raw = _prompt(msg + " (Enter=skip)", "", inp=inp)
    if not raw:
        return None
    return Path(raw)


def _print_menu(stream: TextIO = sys.stdout) -> None:
    print("", file=stream)
    print("=== REALM navigator (Job OS + dynamical topology) ===", file=stream)
    print("Pin is read-only. Measure/control never rewrite soft_T / mono ε.", file=stream)
    print("", file=stream)
    # Numbered display: 1..7 then 0 exit
    display = [
        ("1", "job_smoke"),
        ("2", "job_wizard"),
        ("3", "catalog"),
        ("4", "rotation"),
        ("5", "topology"),
        ("6", "handoff"),
        ("7", "docs"),
        ("0", "exit"),
    ]
    by_id = {x["id"]: x["label"] for x in menu_items()}
    for num, mid in display:
        print(f"  {num}) {by_id[mid]}", file=stream)
    print("", file=stream)


def _choice_to_id(choice: str) -> str | None:
    c = choice.strip().lower()
    mapping = {
        "1": "job_smoke",
        "2": "job_wizard",
        "3": "catalog",
        "4": "rotation",
        "5": "topology",
        "6": "handoff",
        "7": "docs",
        "0": "exit",
        "q": "exit",
        "exit": "exit",
        "job_smoke": "job_smoke",
        "job_wizard": "job_wizard",
        "catalog": "catalog",
        "rotation": "rotation",
        "topology": "topology",
        "handoff": "handoff",
        "docs": "docs",
    }
    return mapping.get(c)


def _action_smoke(
    *,
    inp: Callable[[str], str] | None = None,
    stream: TextIO = sys.stdout,
) -> None:
    out_dir = _prompt("Out dir", "out/job_os", inp=inp)
    print("Running Job OS fixture smoke (in-process)…", file=stream)
    print("CLI equivalent:", file=stream)
    print(" ", " ".join(build_job_smoke_argv(out_dir)), file=stream)
    try:
        result = run_job_smoke(out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001 — menu must not crash shell
        print(f"Smoke failed: {exc}", file=stream)
        return
    _print_run_summary(result, stream=stream)


def _action_wizard(
    *,
    inp: Callable[[str], str] | None = None,
    stream: TextIO = sys.stdout,
) -> None:
    print(
        "Job OS wizard — pin thresholds are NOT editable (read-only).",
        file=stream,
    )
    las = _optional_path("LAS path", inp=inp)
    if las is None:
        print("LAS required for negotiate; aborting wizard.", file=stream)
        return
    if not las.is_file():
        print(f"LAS not found: {las}", file=stream)
        return
    mp = _optional_path("MicroPulse path (dir or CSV)", inp=inp)
    survey = _optional_path("Survey CSV", inp=inp)
    eow = _optional_path("EOW package dir", inp=inp)
    out_root = _prompt("Out dir", "out/job_os", inp=inp)
    run_id_raw = _prompt("run_id (Enter=auto UTC)", "", inp=inp)
    run_id = run_id_raw or None
    max_rounds = _prompt_int("max_rounds", 6, inp=inp)
    stability_k = _prompt_int("stability_k", 1, inp=inp)
    channel_pack = _prompt(
        "channel_pack (surface_min|surface_full|mwd_full|job_union)",
        "surface_min",
        inp=inp,
    )
    regime_mode = _prompt(
        "regime_mode (off|persist_h0|dual_gate_windows)",
        "persist_h0",
        inp=inp,
    )
    with_regime = _prompt_yn("with-regime", True, inp=inp)
    with_science = _prompt_yn("with-science", False, inp=inp)
    with_topo = _prompt_yn("with-dynamical-topology", True, inp=inp)
    topo_stab = _prompt_yn("topo-stability (control gate)", False, inp=inp)
    use_chunk = _prompt_yn("chunk inspect", False, inp=inp)
    chunk_rows: int | None = None
    max_chunks = 32
    if use_chunk:
        chunk_rows = _prompt_int("chunk_rows", 5000, inp=inp)
        max_chunks = _prompt_int("max_chunks", 32, inp=inp)
    max_rows_raw = _prompt("max_rows (Enter=none)", "", inp=inp)
    max_rows: int | None = None
    if max_rows_raw.strip():
        try:
            max_rows = int(max_rows_raw)
        except ValueError:
            max_rows = None
    mono_v = _prompt_int(
        "max_depth_mono_violations (pin config display; default 0)",
        0,
        inp=inp,
    )
    force_ship = False
    if eow is not None:
        force_ship = _prompt_yn("force-ship if not SOLVED", False, inp=inp)

    kwargs = build_job_wizard_kwargs(
        las_path=las,
        micropulse_path=mp,
        survey_path=survey,
        out_root=out_root,
        run_id=run_id,
        max_rounds=max_rounds,
        stability_k=stability_k,
        channel_pack=channel_pack,
        regime_mode=regime_mode,
        with_regime=with_regime,
        with_science=with_science,
        with_dynamical_topology=with_topo or topo_stab,
        topo_stability=topo_stab,
        eow_package=eow,
        force_ship=force_ship,
        chunk_rows=chunk_rows,
        max_chunks=max_chunks,
        max_rows=max_rows,
        max_depth_mono_violations=mono_v,
    )
    cli = wizard_kwargs_to_cli(kwargs)
    print("", file=stream)
    print("Equivalent CLI:", file=stream)
    print(" ", cli, file=stream)
    print(
        "Pin note: depth_mono_eps / soft_T not editable here.",
        file=stream,
    )
    if not _prompt_yn("Run now?", True, inp=inp):
        print("Cancelled.", file=stream)
        return
    try:
        result = run_job_coherence_loop(**kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"Wizard run failed: {exc}", file=stream)
        return
    _print_run_summary(result, stream=stream)


def _action_catalog(
    *,
    inp: Callable[[str], str] | None = None,
    stream: TextIO = sys.stdout,
) -> None:
    root = _prompt("Job OS root to catalog", "out/job_os", inp=inp)
    body = write_job_os_catalog(root)
    print(
        json.dumps(
            {
                "catalog": True,
                "n_runs": body.get("n_runs"),
                "n_solved": body.get("n_solved"),
                "root": body.get("root"),
                "index_md": str(Path(root) / "INDEX.md"),
                "index_json": str(Path(root) / "INDEX.json"),
                "note": "catalog not ACCEPTANCE",
            },
            indent=2,
        ),
        file=stream,
    )


def _action_rotation(
    *,
    inp: Callable[[str], str] | None = None,
    stream: TextIO = sys.stdout,
) -> None:
    """Multi-well rotation: same pin, ROTATION_* from firewall_certified."""
    print(
        "Multi-well rotation — pin thresholds identical across wells; "
        "branch from firewall_certified (not science score).",
        file=stream,
    )
    default_man = (
        str(_DEFAULT_ROTATION_MANIFEST)
        if _DEFAULT_ROTATION_MANIFEST.is_file()
        else "docs/examples/job_rotation_jtod1.manifest.json"
    )
    man_s = _prompt("Rotation manifest JSON", default_man, inp=inp)
    man = Path(man_s)
    if not man.is_file():
        print(f"Manifest not found: {man}", file=stream)
        return
    out_root = _prompt("Out dir", "out/rotation", inp=inp)
    dry = _prompt_yn("dry-run only", False, inp=inp)
    print("CLI equivalent:", file=stream)
    print(" ", " ".join(build_rotation_argv(man, out_root, dry_run=dry)), file=stream)
    if not _prompt_yn("Run now?", True, inp=inp):
        print("Cancelled.", file=stream)
        return
    try:
        report = run_job_rotation(man, out_root=out_root, dry_run=dry)
    except Exception as exc:  # noqa: BLE001
        print(f"Rotation failed: {exc}", file=stream)
        return
    print(
        json.dumps(
            {
                "rotation": True,
                "batch_id": report.get("batch_id"),
                "branch": report.get("branch"),
                "n_wells": (report.get("classification") or {}).get("n_wells"),
                "n_firewall_certified": (report.get("classification") or {}).get(
                    "n_firewall_certified"
                ),
                "pin_identical": report.get("pin_identical_across_wells"),
                "batch_dir": report.get("batch_dir"),
                "dry_run": report.get("dry_run"),
                "note": "ROTATION from firewall_certified; pin never retuned",
            },
            indent=2,
        ),
        file=stream,
    )


def _action_topology(
    *,
    inp: Callable[[str], str] | None = None,
    stream: TextIO = sys.stdout,
) -> None:
    default_run = resolve_job_os_latest(_DEFAULT_JOB_OS_ROOT)
    default_s = str(default_run) if default_run is not None else ""
    if default_s:
        print(f"LATEST run: {default_s}", file=stream)
    run_dir_s = _prompt(
        "Job OS run_dir (cycle_* parent)",
        default_s,
        inp=inp,
    )
    if not run_dir_s:
        print("No run_dir; aborting.", file=stream)
        return
    run_dir = Path(run_dir_s)
    if not run_dir.is_dir():
        print(f"Not a directory: {run_dir}", file=stream)
        return
    try:
        report = run_topology_report(run_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"Topology report failed: {exc}", file=stream)
        return
    path = report.get("_path")
    print(
        json.dumps(
            {
                "path": path,
                "n_stages": report.get("n_stages"),
                "n_long": report.get("n_long"),
                "n_short": report.get("n_short"),
                "not_acceptance": report.get("not_acceptance"),
                "pin_writable": report.get("pin_writable"),
                "acceptance_writable": report.get("acceptance_writable"),
                "dominant_phase": (report.get("phases") or {}).get("dominant_phase"),
            },
            indent=2,
        ),
        file=stream,
    )
    print(f"Wrote: {path}", file=stream)


def _action_handoff(
    *,
    inp: Callable[[str], str] | None = None,
    stream: TextIO = sys.stdout,
) -> None:
    knobs_path = Path("evolve_result.json")
    pdb = _prompt("pdb-ids", "1CSA", inp=inp)
    out_dir = _prompt("out-dir", "out/coherence", inp=inp)
    max_rounds = _prompt_int("max-rounds", 5, inp=inp)
    with_topo = _prompt_yn("with-dynamical-topology (if supported)", False, inp=inp)
    parts = [
        "python",
        "handoff_coherence.py",
        "--os",
        "--pdb-ids",
        pdb,
        "--knobs",
        str(knobs_path),
        "--out-dir",
        out_dir,
        "--max-rounds",
        str(max_rounds),
        "--stability-k",
        "1",
    ]
    # Detect optional flag on CLI if present (in-process API always supports it)
    hc = _REPO_ROOT / "handoff_coherence.py"
    supports_topo_cli = False
    if hc.is_file():
        text = hc.read_text(encoding="utf-8", errors="replace")
        supports_topo_cli = "with-dynamical-topology" in text
    if with_topo and supports_topo_cli:
        parts.append("--with-dynamical-topology")
    cli = " ".join(parts)
    print("Suggested handoff coherence CLI:", file=stream)
    print(" ", cli, file=stream)
    if with_topo and not supports_topo_cli:
        print(
            "  (CLI flag may be absent; in-process run still passes "
            "with_dynamical_topology=True)",
            file=stream,
        )
    print(f"Knobs path exists: {knobs_path.is_file()} ({knobs_path})", file=stream)
    if not knobs_path.is_file():
        print("Knobs missing — print-only (no run).", file=stream)
        return
    if not _prompt_yn("Run handoff_coherence in-process?", False, inp=inp):
        print("Skipped run (CLI printed above).", file=stream)
        return
    try:
        from realm.handoff.coherence import FreeParams as HFree
        from realm.handoff.coherence import run_coherence_loop
        from realm.handoff.pipeline import resolve_pdb_id_list
        from realm.validate.report import load_knobs
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot import handoff coherence: {exc}", file=stream)
        return
    try:
        knobs = load_knobs(knobs_path)
        if isinstance(knobs, dict) and "best_knobs" in knobs:
            knobs = knobs["best_knobs"]
        ids = resolve_pdb_id_list(pdb)
        kwargs: dict[str, Any] = {
            "pdb_ids": list(ids),
            "knobs": knobs,
            "out_root": out_dir,
            "max_rounds": max_rounds,
            "os_mode": True,
            "stability_k": 1,
            "initial": HFree(),
            "with_dynamical_topology": bool(with_topo),
        }
        result = run_coherence_loop(**kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"Handoff run failed: {exc}", file=stream)
        return
    print(
        json.dumps(
            {
                "solved": result.get("solved") if isinstance(result, dict) else None,
                "stop_reason": (
                    result.get("stop_reason") if isinstance(result, dict) else None
                ),
                "out": str(
                    (result.get("out_root") if isinstance(result, dict) else None)
                    or out_dir
                ),
                "note": "handoff pin locked; not ACCEPTANCE",
            },
            indent=2,
        ),
        file=stream,
    )


def _action_docs(
    *,
    stream: TextIO = sys.stdout,
) -> None:
    job_os = (_REPO_ROOT / _DOCS_JOB_OS).resolve()
    design = (_REPO_ROOT / _DOCS_DESIGN).resolve()
    latest = resolve_job_os_latest(_DEFAULT_JOB_OS_ROOT)
    latest_file = Path(_DEFAULT_JOB_OS_ROOT) / "LATEST"
    bridge = (_REPO_ROOT / _DOCS_BRIDGE).resolve()
    print("Docs / paths:", file=stream)
    print(f"  JOB_OS.md:     {job_os}  (exists={job_os.is_file()})", file=stream)
    print(f"  Design spec:   {design}  (exists={design.is_file()})", file=stream)
    print(f"  Dual-stalk:    {bridge}  (exists={bridge.is_file()})", file=stream)
    print(
        f"  Job OS LATEST: {latest_file.resolve()}  (exists={latest_file.is_file()})",
        file=stream,
    )
    if latest is not None:
        print(f"  LATEST →      {latest}", file=stream)
    else:
        print("  LATEST →      (none yet — run smoke first)", file=stream)
    print(
        f"  Fixture LAS:   {_DEFAULT_LAS}  (exists={_DEFAULT_LAS.is_file()})",
        file=stream,
    )
    print(
        f"  Rotation man:  {_DEFAULT_ROTATION_MANIFEST}  "
        f"(exists={_DEFAULT_ROTATION_MANIFEST.is_file()})",
        file=stream,
    )
    print("  Entry:         python realm_menu.py", file=stream)
    print("  CLI smoke:     " + " ".join(build_job_smoke_argv("out/job_os")), file=stream)
    print(
        "  CLI rotation:  "
        + " ".join(
            build_rotation_argv(
                "docs/examples/job_rotation_jtod1.manifest.json",
                "out/rotation_jtod1",
            )
        ),
        file=stream,
    )


def main(
    argv: list[str] | None = None,
    *,
    inp: Callable[[str], str] | None = None,
    stream: TextIO | None = None,
) -> int:
    """Interactive menu loop. Tests inject inp= for non-interactive coverage."""
    _ = argv  # reserved for future non-interactive flags
    out = stream or sys.stdout
    read = inp or input
    while True:
        _print_menu(stream=out)
        try:
            choice = read("Choice: ")
        except EOFError:
            print("", file=out)
            return 0
        mid = _choice_to_id(choice)
        if mid is None:
            print(f"Unknown choice: {choice!r}", file=out)
            continue
        if mid == "exit":
            print("Bye.", file=out)
            return 0
        if mid == "job_smoke":
            _action_smoke(inp=read, stream=out)
        elif mid == "job_wizard":
            _action_wizard(inp=read, stream=out)
        elif mid == "catalog":
            _action_catalog(inp=read, stream=out)
        elif mid == "rotation":
            _action_rotation(inp=read, stream=out)
        elif mid == "topology":
            _action_topology(inp=read, stream=out)
        elif mid == "handoff":
            _action_handoff(inp=read, stream=out)
        elif mid == "docs":
            _action_docs(stream=out)
        else:
            print(f"Unhandled: {mid}", file=out)


if __name__ == "__main__":
    raise SystemExit(main())
