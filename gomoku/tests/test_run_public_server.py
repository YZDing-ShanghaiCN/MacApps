from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_public_server.py"
SPEC = importlib.util.spec_from_file_location("run_public_server", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
run_public_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_public_server)


def test_public_base_url_accepts_https_root_url() -> None:
    assert run_public_server.public_base_url(" https://gomoku.example.com/ ") == "https://gomoku.example.com"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://gomoku.example.com",
        "https://gomoku.example.com/room/abc",
        "https://gomoku.example.com?token=secret",
    ],
)
def test_public_base_url_rejects_noncanonical_url(value: str) -> None:
    with pytest.raises(ValueError):
        run_public_server.public_base_url(value)


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port"])
def test_local_port_rejects_invalid_port(value: str) -> None:
    with pytest.raises(ValueError):
        run_public_server.local_port(value)


def test_tunnel_command_uses_cloudflare_token_mode() -> None:
    assert run_public_server.tunnel_command("/opt/homebrew/bin/cloudflared", "token-value") == [
        "/opt/homebrew/bin/cloudflared",
        "tunnel",
        "--no-autoupdate",
        "run",
        "--token",
        "token-value",
    ]
