"""Start the local game server behind a temporary Cloudflare Quick Tunnel.

The script waits for Cloudflare to allocate a public HTTPS address, then starts
the game server with that address configured as the canonical room-link base.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "run_server.py"
TUNNEL_STARTUP_TIMEOUT_SECONDS = 30
SERVER_STARTUP_TIMEOUT_SECONDS = 10
QUICK_TUNNEL_URL_PATTERN = re.compile(
    r"https://[a-z0-9-]+\.trycloudflare\.com(?=[\s\"']|$)",
    re.IGNORECASE,
)


def quick_tunnel_command(cloudflared: str, port: int) -> list[str]:
    return [
        cloudflared,
        "tunnel",
        "--no-autoupdate",
        "--url",
        f"http://127.0.0.1:{port}",
    ]


def local_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError("GOMOKU_PORT 必须是 1 到 65535 之间的整数。") from error
    if not 1 <= port <= 65535:
        raise ValueError("GOMOKU_PORT 必须是 1 到 65535 之间的整数。")
    return port


def port_is_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def quick_tunnel_environment(environment: dict[str, str]) -> dict[str, str]:
    """Remove Named Tunnel credentials that Quick Tunnel never needs."""

    sanitized = environment.copy()
    for name in tuple(sanitized):
        if name.upper().endswith("TUNNEL_TOKEN"):
            sanitized.pop(name)
    return sanitized


def wait_for_server(server: subprocess.Popen[object], port: int) -> None:
    health_url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + SERVER_STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("本机五子棋服务启动失败。")
        try:
            with urlopen(health_url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.2)
    raise RuntimeError("等待本机五子棋服务启动超时。")


def stop_process(process: subprocess.Popen[object] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def quick_tunnel_url(line: str) -> str | None:
    match = QUICK_TUNNEL_URL_PATTERN.search(line)
    return match.group(0).rstrip("/") if match else None


def relay_tunnel_output(
    tunnel: subprocess.Popen[str],
    public_url: list[str],
    public_url_ready: threading.Event,
) -> None:
    if tunnel.stdout is None:
        return

    for line in tunnel.stdout:
        print(line, end="", flush=True)
        url = quick_tunnel_url(line)
        if url and not public_url_ready.is_set():
            public_url.append(url)
            public_url_ready.set()


def main() -> int:
    try:
        port = local_port(os.environ.get("GOMOKU_PORT", "8000"))
    except ValueError as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2

    if port_is_in_use(port):
        print(
            (
                f"启动失败：本机端口 {port} 已被占用。请先在旧服务终端按 Ctrl+C，"
                "或使用其他端口，例如：GOMOKU_PORT=8001 "
                "python gomoku/scripts/run_quick_tunnel.py"
            ),
            file=sys.stderr,
        )
        return 1

    cloudflared = shutil.which("cloudflared")
    if cloudflared is None:
        print("找不到 cloudflared。请先执行：brew install cloudflared", file=sys.stderr)
        return 2

    tunnel: subprocess.Popen[str] | None = None
    server: subprocess.Popen[object] | None = None
    try:
        tunnel = subprocess.Popen(
            quick_tunnel_command(cloudflared, port),
            cwd=PROJECT_ROOT,
            env=quick_tunnel_environment(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        public_url: list[str] = []
        public_url_ready = threading.Event()
        output_thread = threading.Thread(
            target=relay_tunnel_output,
            args=(tunnel, public_url, public_url_ready),
            daemon=True,
        )
        output_thread.start()

        if not public_url_ready.wait(TUNNEL_STARTUP_TIMEOUT_SECONDS):
            if tunnel.poll() is not None:
                raise RuntimeError("Cloudflare Quick Tunnel 启动失败。")
            raise RuntimeError("等待 Cloudflare 分配公网地址超时。")

        environment = quick_tunnel_environment(os.environ)
        environment["GOMOKU_HOST"] = "127.0.0.1"
        environment["GOMOKU_PORT"] = str(port)
        environment["GOMOKU_PUBLIC_BASE_URL"] = public_url[0]
        server = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT)],
            cwd=PROJECT_ROOT,
            env=environment,
        )
        wait_for_server(server, port)
        print(
            f"\n公网对战已就绪。请在 Mac 和手机打开：{public_url[0]}",
            flush=True,
        )
        print("请从这个 HTTPS 地址创建房间；二维码和邀请链接会自动使用公网地址。", flush=True)
        return server.wait()
    except RuntimeError as error:
        print(f"启动失败：{error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n正在停止公网对战服务…", flush=True)
        return 0
    finally:
        stop_process(server)
        stop_process(tunnel)


if __name__ == "__main__":
    raise SystemExit(main())
