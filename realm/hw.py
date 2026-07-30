"""Hardware-aware worker budget for ARM / low-RAM hosts.

Snapdragon-class boxes: 8 ARM cores, ~16 GB RAM, often 5–8 GB free.
DirectML may be present (ort DmlExecutionProvider) but the zeta forge path
is NumPy/SciPy CPU — parallelize across cores, keep BLAS single-threaded
inside workers to avoid oversubscription.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ComputeProfile:
    cpu_count: int
    ram_total_gb: float
    ram_avail_gb: float
    workers: int
    blas_threads: int
    notes: str


def _ram_gb() -> tuple[float, float]:
    try:
        import psutil

        m = psutil.virtual_memory()
        return m.total / 1e9, m.available / 1e9
    except Exception:
        return 16.0, 6.0


def recommend_workers(
    requested: int | None = None,
    *,
    max_workers: int = 6,
    mem_headroom_gb: float = 1.5,
    gb_per_worker: float = 0.9,
) -> ComputeProfile:
    """Pick process count that fits free RAM and leaves a core for the OS."""
    cpu = int(os.cpu_count() or 4)
    total_gb, avail_gb = _ram_gb()

    by_cpu = max(1, cpu - 1)  # leave 1 core free
    by_ram = max(1, int(max(0.0, avail_gb - mem_headroom_gb) / gb_per_worker))
    auto = max(1, min(max_workers, by_cpu, by_ram))

    if requested is None or requested < 0:
        workers = auto
    elif requested == 0:
        workers = 1
    else:
        workers = max(1, min(int(requested), max_workers, by_cpu))

    # When multi-process, pin BLAS to 1 thread/worker; serial can use 2
    blas = 1 if workers > 1 else min(2, cpu)
    notes = (
        f"cpu={cpu} avail_ram={avail_gb:.1f}GB → workers={workers} "
        f"(auto={auto}, by_cpu={by_cpu}, by_ram={by_ram})"
    )
    return ComputeProfile(
        cpu_count=cpu,
        ram_total_gb=total_gb,
        ram_avail_gb=avail_gb,
        workers=workers,
        blas_threads=blas,
        notes=notes,
    )


def apply_blas_thread_env(n_threads: int) -> None:
    """Call before importing heavy numeric stacks in workers if possible."""
    n = str(max(1, int(n_threads)))
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(key, n)
