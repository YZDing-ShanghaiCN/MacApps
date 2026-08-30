"""Shared configuration for the sgame portal."""

import os

APP_NAME = "sgame"
APP_VERSION = "0.1.4"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001

ENABLE_API_DOCS = os.getenv("SGAME_ENABLE_API_DOCS", "").lower() in {
    "1",
    "true",
    "yes",
}

GAME_SCHULTE = "schulte"
GAME_MINESWEEPER = "minesweeper"
GAME_PACMAN = "pacman"
GAME_2048 = "2048"
GAME_TETRIS = "tetris"

GAMES = (
    {
        "id": GAME_SCHULTE,
        "title": "舒尔特方格",
        "description": "3×3、4×4、5×5 三种模式，按顺序尽快点击数字，训练专注力与视觉搜索。",
    },
    {
        "id": GAME_MINESWEEPER,
        "title": "扫雷",
        "description": "主菜单 + 三级难度 + 本地排行榜，避开地雷翻开所有安全格，挑战最快纪录。",
    },
    {
        "id": GAME_PACMAN,
        "title": "吃豆人",
        "description": "吃掉迷宫里所有的豆子，小心幽灵；能量豆可以让你反击。",
    },
    {
        "id": GAME_2048,
        "title": "2048",
        "description": "滑动合并相同数字，合成 2048，支持键盘与触屏滑动。",
    },
    {
        "id": GAME_TETRIS,
        "title": "俄罗斯方块",
        "description": "经典落下式拼块游戏，消除整行得分，支持键盘与触屏按钮操作。",
    },
)

VALID_GAME_IDS = tuple(game["id"] for game in GAMES)
