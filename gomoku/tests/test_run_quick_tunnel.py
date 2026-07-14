from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_quick_tunnel.py"
SPEC = importlib.util.spec_from_file_location("run_quick_tunnel", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
run_quick_tunnel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_quick_tunnel)


def test_quick_tunnel_url_extracts_cloudflare_address() -> None:
    line = "INF Your quick Tunnel has been created! Visit it at https://jade-tree.trycloudflare.com\n"

    assert run_quick_tunnel.quick_tunnel_url(line) == "https://jade-tree.trycloudflare.com"


def test_quick_tunnel_url_ignores_non_public_log_lines() -> None:
    assert run_quick_tunnel.quick_tunnel_url("INF Registered tunnel connection\n") is None


def test_quick_tunnel_command_targets_local_server() -> None:
    assert run_quick_tunnel.quick_tunnel_command("cloudflared", 8000) == [
        "cloudflared",
        "tunnel",
        "--no-autoupdate",
        "--url",
        "http://127.0.0.1:8000",
    ]
