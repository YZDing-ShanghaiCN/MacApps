from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.adapters.web_adapter import serialize_game_state
from gomoku.core.enums import Player
from gomoku.core.game import GomokuGame


def test_serialize_game_state_returns_dict() -> None:
    game = GomokuGame()

    state = serialize_game_state(game)

    assert isinstance(state, dict)
    assert "board" in state


def test_initial_state_serializes_black_turn() -> None:
    game = GomokuGame()

    state = serialize_game_state(game)

    assert state["current_player"] == int(Player.BLACK)
    assert state["current_player_name"] == "Black"
    assert state["game_over"] is False
    assert state["last_move"] is None


def test_move_count_changes_after_move() -> None:
    game = GomokuGame()
    game.make_move(7, 7)

    state = serialize_game_state(game)

    assert state["move_count"] == 1
    assert state["last_move"] == {"row": 7, "col": 7, "player": int(Player.BLACK)}


def test_win_state_serializes_winner_and_game_over() -> None:
    game = GomokuGame()
    moves = [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (0, 4),
    ]

    for row, col in moves:
        game.make_move(row, col)

    state = serialize_game_state(game)

    assert state["game_over"] is True
    assert state["winner"] == int(Player.BLACK)
    assert state["winner_name"] == "Black"
    assert state["move_count"] == 9
