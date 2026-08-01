"""ToeStub FastMCP server: tool name list + create_server smoke."""

from toestub.mcp_server import TOOL_NAMES, create_server


def test_five_tool_names():
    assert set(TOOL_NAMES) == {
        "toestub_job_run",
        "toestub_job_catalog",
        "toestub_job_rotation",
        "toestub_job_audit",
        "toestub_firewall_read",
    }
    assert len(TOOL_NAMES) == 5


def test_create_server():
    s = create_server()
    assert s is not None
