# Gomoku

一个 Python 五子棋项目。当前版本包含本地 pygame 双人对战和基于 FastAPI + 原生 HTML/CSS/JavaScript 的 Web 双人本地对战。核心规则层与 pygame、FastAPI、前端、数据库等外部框架解耦，方便后续扩展 AI、人机对战、HTTP API 和联机对战。

## 当前功能

- 15x15 五子棋棋盘。
- 黑棋先手。
- 本地双人轮流落子。
- 横向、纵向、主对角线、副对角线五连或更多即胜利。
- 非法落子检查。
- 胜负和平局状态。
- 悔棋、重开。
- pygame 本地图形界面。
- FastAPI Web 服务。
- 原生网页棋盘，可点击落子、悔棋、重开、显示胜负。
- 随机合法落子的简单 AI 占位。
- pytest 核心规则和 Web 状态适配测试。

## 项目结构

```text
apps/
├── .gitignore
└── gomoku/
    ├── README.md
    ├── requirements.txt
    ├── frontend/
    │   ├── index.html
    │   ├── style.css
    │   └── main.js
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
    │           ├── app.py
    │           └── routes.py
    ├── scripts/
    │   ├── run_pygame.py
    │   └── run_server.py
    └── tests/
        ├── test_board.py
        ├── test_rules.py
        ├── test_game.py
        └── test_web_adapter.py
```

## 安装依赖

所有命令默认在 `apps/` 目录下执行。

建议使用 Python 3.10 到 3.13。若使用更新版本的 Python 且 pygame 没有对应 wheel，可能需要先安装本机 SDL 开发依赖，或切换到有 pygame wheel 的 Python 版本。

```bash
pip install -r gomoku/requirements.txt
```

## 运行本地 pygame 版本

在 `apps/` 目录下执行：

```bash
python gomoku/scripts/run_pygame.py
```

操作：

- 鼠标点击棋盘落子。
- 按 `R` 重开。
- 按 `U` 悔棋。

## 运行 FastAPI Web 版本

在 `apps/` 目录下执行：

```bash
python gomoku/scripts/run_server.py
```

服务启动后访问：

- Web 页面：http://127.0.0.1:8000
- 健康检查：http://127.0.0.1:8000/health
- 当前状态：http://127.0.0.1:8000/api/state

Web API：

- `GET /api/state` 获取当前游戏状态。
- `POST /api/move` 落子，请求体示例：`{"row": 7, "col": 7}`。
- `POST /api/reset` 重开。
- `POST /api/undo` 悔棋一步。

## 运行测试

在 `apps/` 目录下执行：

```bash
python -m pytest gomoku/tests
```

## 当前限制

- 当前 Web 版是单局本地网页对战。
- 还不是在线多人联机。
- 没有账号系统。
- 没有数据库。

## 后续计划

- 多局游戏管理。
- WebSocket 联机对战。
- AI 对战。
- 前端优化。
- 战绩保存。
