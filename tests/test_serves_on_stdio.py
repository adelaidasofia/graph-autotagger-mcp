"""The server serves MCP when started with no arguments.

The plugin and `claude mcp add` both start it as `python server.py`. It used
to run the self-test and exit there, so Claude Code saw the connection close.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_args_answers_mcp_handshake(tmp_path) -> None:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
    )
    # A server that stalls without closing stdout fails the test instead of hanging CI.
    watchdog = threading.Timer(60, proc.kill)
    watchdog.start()
    try:
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        proc.stdin.write(json.dumps(init) + "\n")
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
        proc.stdin.flush()
        replies = {}
        while len(replies) < 2:
            line = proc.stdout.readline()
            assert line, "server closed stdout before answering"
            msg = json.loads(line)
            if "id" in msg:
                replies[msg["id"]] = msg
        assert replies[1]["result"]["serverInfo"]["name"] == "graph-autotagger"
        tools = {t["name"] for t in replies[2]["result"]["tools"]}
        assert {"suggest_links", "check_god_nodes", "community_match"} <= tools
    finally:
        watchdog.cancel()
        proc.kill()
        proc.wait()
