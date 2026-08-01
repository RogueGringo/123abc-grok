"""ToeStub FastMCP stdio server — Job OS cognitive governor tools.

Run:
  PYTHONPATH=. python -m toestub.mcp_server
  toestub-mcp   # after pip install -e .
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

TOOL_NAMES: tuple[str, ...] = (
    "toestub_job_run",
    "toestub_job_catalog",
    "toestub_job_rotation",
    "toestub_job_audit",
    "toestub_firewall_read",
)

_INSTRUCTIONS = (
    "Job OS cognitive governor. Pin sealed. Explore never certifies."
)


def _ensure_repo_root_on_path() -> None:
    """Put monorepo root on sys.path so realm/ and toestub/ resolve without install."""
    repo_root = Path(__file__).resolve().parent.parent
    root_s = str(repo_root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def create_server() -> FastMCP:
    """Build FastMCP instance with the five Job OS tools registered."""
    _ensure_repo_root_on_path()

    from toestub.tools_job import (
        tool_firewall_read,
        tool_job_audit,
        tool_job_catalog,
        tool_job_rotation,
        tool_job_run,
    )

    mcp = FastMCP("toestub", instructions=_INSTRUCTIONS)

    @mcp.tool(name="toestub_job_run")
    def toestub_job_run(
        las_path: str,
        micropulse_path: str | None = None,
        survey_path: str | None = None,
        out_root: str | None = None,
        max_rounds: int = 6,
        stability_k: int = 1,
        free_params: dict[str, Any] | None = None,
        pin_config: dict[str, Any] | None = None,
        with_regime: bool = False,
        with_science: bool = False,
        with_dynamical_topology: bool = False,
        max_rows: int | None = None,
        eow_package: str | None = None,
        include_explore: bool = False,
    ) -> str:
        """Run Job OS coherence loop (os_mode). Returns JSON envelope string."""
        return json.dumps(
            tool_job_run(
                las_path=las_path,
                micropulse_path=micropulse_path,
                survey_path=survey_path,
                out_root=out_root,
                max_rounds=max_rounds,
                stability_k=stability_k,
                free_params=free_params,
                pin_config=pin_config,
                with_regime=with_regime,
                with_science=with_science,
                with_dynamical_topology=with_dynamical_topology,
                max_rows=max_rows,
                eow_package=eow_package,
                include_explore=include_explore,
            )
        )

    @mcp.tool(name="toestub_job_catalog")
    def toestub_job_catalog(out_dir: str) -> str:
        """Write Job OS INDEX.json/INDEX.md under out_dir. certified always null."""
        return json.dumps(tool_job_catalog(out_dir))

    @mcp.tool(name="toestub_job_rotation")
    def toestub_job_rotation(
        manifest_path: str | None = None,
        manifest: dict[str, Any] | None = None,
        out_root: str | None = None,
        dry_run: bool = False,
        max_rows: int | None = None,
        include_explore: bool = False,
    ) -> str:
        """Multi-well Job OS rotation. Exactly one of manifest_path or manifest."""
        return json.dumps(
            tool_job_rotation(
                manifest_path=manifest_path,
                manifest=manifest,
                out_root=out_root,
                dry_run=dry_run,
                max_rows=max_rows,
                include_explore=include_explore,
            )
        )

    @mcp.tool(name="toestub_job_audit")
    def toestub_job_audit(path: str, write_report: bool = False) -> str:
        """Audit a Job OS run_dir or rotation batch_dir; optional AUDIT.json."""
        return json.dumps(tool_job_audit(path, write_report=write_report))

    @mcp.tool(name="toestub_firewall_read")
    def toestub_firewall_read(
        run_dir: str,
        include_explore: bool = False,
    ) -> str:
        """Load FIREWALL.json or rebuild from COHERENCE.json under run_dir."""
        return json.dumps(
            tool_firewall_read(run_dir, include_explore=include_explore)
        )

    return mcp


def main() -> None:
    """Stdio entrypoint for MCP hosts (Cursor / Claude Desktop / etc.)."""
    _ensure_repo_root_on_path()
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
