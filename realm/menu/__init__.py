"""Navigator menu for Job OS and dynamical topology (non-CLI path).

Prefer stdlib input loops; Windows-friendly. Never retunes pin.
"""

from __future__ import annotations

from realm.menu.app import (
    build_job_smoke_argv,
    build_job_wizard_kwargs,
    main,
    menu_items,
)

__all__ = [
    "build_job_smoke_argv",
    "build_job_wizard_kwargs",
    "main",
    "menu_items",
]
