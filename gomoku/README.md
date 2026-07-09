# Gomoku

一个 Python 五子棋项目。第一阶段实现本地双人对战，核心规则层与 pygame、FastAPI、WebSocket、数据库等外部框架解耦，方便后续扩展 AI、人机对战、HTTP API 和联机对战。

## 当前功能

- 15x15 五子棋棋盘。
- 黑棋先手。
- 本地双人轮流落子。
- 横向、纵向、主对角线、副对角线五连或更多即胜利。
- 非法落子检查。
- 胜负和平局状态。
- 悔棋、重开。
- pygame 本地图形界面。
- FastAPI 占位服务。
- 随机合法落子的简单 AI 占位。
- pytest 核心规则测试。

## 项目结构

```text
app/
├── .gitignore
└── gomoku/
    ├── README.md
    ├── requirements.txt
    ├── src/
    │   └── gomoku/
    │       ├── __init__.py
    │       ├── config.py
    │       ├── core/
    │       │   ├── __init__.py
    │       │   ├── board.py
    │       │   ├── game.py
    │       │   ├── rules.py
    │       │   ├── enums.py
    │       │   └── exceptions.py
    │       ├── ai/
    │       │   ├── __init__.py
    │       │   └── simple_ai.py
    │       ├── adapters/
    │       │   ├── __init__.py
    │       │   ├── pygame_app.py
    │       │   └── web_adapter.py
    │       └── server/
    │           ├── __init__.py
    │           └── app.py
    ├── scripts/
    │   ├── run_pygame.py
    │   └── run_server.py
    └── tests/
        ├── test_board.py
        ├── test_rules.py
        └── test_game.py
```

## 创建虚拟环境

所有命令默认在 `app/gomoku/` 目录下执行。

建议使用 Python 3.10 到 3.13。若使用更新版本的 Python 且 pygame 没有对应 wheel，可能需要先安装本机 SDL 开发依赖，或切换到有 pygame wheel 的 Python 版本。

```bash
python -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行本地 pygame 版本

```bash
python scripts/run_pygame.py
```

操作：

- 鼠标点击棋盘落子。
- 按 `R` 重开。
- 按 `U` 悔棋。

## 运行测试

```bash
pytest
```

## 运行 server 占位服务

```bash
python scripts/run_server.py
```

服务启动后可访问：

- `GET /`
- `GET /health`

## 后续计划

- 简单 AI 对战入口。
- FastAPI HTTP API。
- WebSocket 联机对战。
- 前端页面。
- 数据库存储战绩。
