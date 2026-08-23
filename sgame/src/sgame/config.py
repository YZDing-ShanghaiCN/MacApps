"""Shared configuration for the sgame portal."""

import os

APP_NAME = "sgame"
APP_VERSION = "0.1.0"

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

GAMES = (
    {
        "id": GAME_SCHULTE,
        "title": "舒尔特方格",
        "description": "按 1 到 25 的顺序尽快点击数字，训练专注力与视觉搜索。",
    },
    {
        "id": GAME_MINESWEEPER,
        "title": "扫雷",
        "description": "避开地雷翻开所有安全格，支持初级、中级、高级三种难度。",
    },
    {
        "id": GAME_PACMAN,
        "title": "吃豆人",
        "description": "吃掉迷宫里所有的豆子，小心幽灵；能量豆可以让你反击。",
    },
)

VALID_GAME_IDS = tuple(game["id"] for game in GAMES)
