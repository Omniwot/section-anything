from section_anything.mcp_server import main as server_main

import section_anything_mcp


def test_runs_the_libraries_server():
    assert section_anything_mcp.main is server_main
