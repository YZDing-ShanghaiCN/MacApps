"""Run the local game server behind a Cloudflare Tunnel public hostname."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = PROJECT_ROOT / "scripts" / "run_server.py"
STARTUP_TIMEOUT_SECONDS = 10


def public_base_url(value: str) -> str:
    """Validate the canonical public address used in every room invitation."""
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("GOMOKU_PUBLIC_BASE_URL 必须是根路径 HTTPS 地址，例如 https://gomoku.example.com")
    return value.strip().rstrip("/")


def local_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError("GOMOKU_PORT 必须是 1 到 65535 之间的整数。") from error
    if not 1 <= port <= 65535:
        raise ValueError("GOMOKU_PORT 必须是 1 到 65535 之间的整数。")
    return port


def tunnel_command(cloudflared: str, token: str) -> list[str]:
    return [cloudflared, "tunnel", "--no-autoupdate", "run", "--token", token]


def wait_for_server(server: subprocess.Popen[object], port: int) -> None:
    health_url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
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


def main() -> int:
    try:
        base_url = public_base_url(os.environ.get("GOMOKU_PUBLIC_BASE_URL", ""))
        port = local_port(os.environ.get("GOMOKU_PORT", "8000"))
    except ValueError as error:
        print(f"配置错误：{error}", file=sys.stderr)
        return 2

    token = os.environ.get("GOMOKU_CLOUDFLARE_TUNNEL_TOKEN", "").strip()
    if not token:
        print("配置错误：请设置 GOMOKU_CLOUDFLARE_TUNNEL_TOKEN。", file=sys.stderr)
        return 2

    cloudflared = shutil.which("cloudflared")
    if cloudflared is None:
        print("找不到 cloudflared。请先执行：brew install cloudflared", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["GOMOKU_HOST"] = "127.0.0.1"
    environment["GOMOKU_PORT"] = str(port)
    environment["GOMOKU_PUBLIC_BASE_URL"] = base_url

    server: subprocess.Popen[object] | None = None
    tunnel: subprocess.Popen[object] | None = None
    try:
        server = subprocess.Popen([sys.executable, str(SERVER_SCRIPT)], cwd=PROJECT_ROOT, env=environment)
        wait_for_server(server, port)
        print(f"本机服务已就绪。请在两台设备上访问：{base_url}", flush=True)
        tunnel = subprocess.Popen(tunnel_command(cloudflared, token), cwd=PROJECT_ROOT)
        return tunnel.wait()
    except RuntimeError as error:
        print(f"启动失败：{error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n正在停止公网对战服务…", flush=True)
        return 0
    finally:
        stop_process(tunnel)
        stop_process(server)


if __name__ == "__main__":
    raise SystemExit(main())
