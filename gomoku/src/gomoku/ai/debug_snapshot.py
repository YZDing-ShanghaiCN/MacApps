"""Portable AI position snapshots for reproducible issue reports."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

from gomoku import config
from gomoku.ai.normal_ai import NormalAI
from gomoku.core.enums import Player
from gomoku.core.game import GomokuGame


def build_debug_snapshot(
    game: GomokuGame,
    *,
    mode: str,
    ai_player: Player | None,
    ai_difficulty: str,
    ai,
) -> dict:
    """Build a JSON-safe snapshot shared by Web and Pygame."""

    normal_ai = ai if isinstance(ai, NormalAI) else None
    return {
        "schema_version": 1,
        "app_version": config.APP_VERSION,
        "notes": "",
        "expected_move": None,
        "position": {
            "size": game.board.size,
            "board": game.board.to_list(),
            "current_player": int(game.current_player),
            "move_count": len(game.move_history),
            "last_move": (
                {
                    "row": game.move_history[-1][0],
                    "col": game.move_history[-1][1],
                    "player": int(game.move_history[-1][2]),
                }
                if game.move_history
                else None
            ),
            "move_history": [
                {"row": row, "col": col, "player": int(player)}
                for row, col, player in game.move_history
            ],
        },
        "game": {
            "mode": mode,
            "ai_player": int(ai_player) if ai_player is not None else None,
            "ai_difficulty": ai_difficulty,
            "game_over": game.game_over,
            "winner": int(game.winner) if game.winner is not None else None,
        },
        "normal_ai": {
            "config": asdict(normal_ai.config) if normal_ai is not None else None,
            "search_stats": (
                asdict(normal_ai.last_search_stats)
                if normal_ai is not None
                else None
            ),
        },
    }


def write_debug_snapshot(snapshot: dict, directory: Path) -> Path:
    """Write a snapshot with a collision-resistant local timestamp."""

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = directory / f"gomoku-position-{timestamp}.json"
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
