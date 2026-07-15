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


def test_quick_tunnel_environment_removes_named_tunnel_tokens() -> None:
    environment = {
        "PATH": "/usr/bin",
        "GOMOKU_CLOUDFLARE_TUNNEL_TOKEN": "secret",
        "TUNNEL_TOKEN": "another-secret",
        "UNCHANGED": "value",
    }

    sanitized = run_quick_tunnel.quick_tunnel_environment(environment)

    assert sanitized == {"PATH": "/usr/bin", "UNCHANGED": "value"}
    assert environment["GOMOKU_CLOUDFLARE_TUNNEL_TOKEN"] == "secret"


class FakeSocket:
    def __init__(self, result: int) -> None:
        self.result = result
        self.timeout: float | None = None
        self.address: tuple[str, int] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect_ex(self, address: tuple[str, int]) -> int:
        self.address = address
        return self.result


def test_port_is_in_use_detects_a_listening_local_service(monkeypatch) -> None:
    probe = FakeSocket(0)
    monkeypatch.setattr(
        run_quick_tunnel.socket,
        "socket",
        lambda *_args: probe,
    )

    assert run_quick_tunnel.port_is_in_use(8000) is True
    assert probe.timeout == 0.2
    assert probe.address == ("127.0.0.1", 8000)


def test_port_is_in_use_allows_an_available_port(monkeypatch) -> None:
    probe = FakeSocket(61)
    monkeypatch.setattr(
        run_quick_tunnel.socket,
        "socket",
        lambda *_args: probe,
    )

    assert run_quick_tunnel.port_is_in_use(8000) is False
