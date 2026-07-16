from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku import config
from gomoku.core.enums import Player
from gomoku.server import routes


def setup_function() -> None:
    routes.set_current_mode(config.MODE_LOCAL_2P)
    routes.set_current_difficulty(config.AI_DIFFICULTY_SIMPLE)
    routes.ai_thinking = False
    routes.game.reset()


def test_vs_ai_move_triggers_ai_response() -> None:
    routes.set_current_mode(config.MODE_VS_AI)

    state = routes.make_move({"row": 7, "col": 7})

    assert state["mode"] == config.MODE_VS_AI
    assert state["ai_player"] == int(Player.WHITE)
    assert state["move_count"] == 2
    assert state["board"][7][7] == int(Player.BLACK)
    assert state["last_move"]["player"] == int(Player.WHITE)
    assert state["current_player"] == int(Player.BLACK)


def test_vs_ai_move_count_increases_by_two_unless_game_ends() -> None:
    routes.set_current_mode(config.MODE_VS_AI)

    state = routes.make_move({"row": 7, "col": 7})

    if state["winner"] is None:
        assert state["move_count"] >= 2


def test_vs_ai_undo_reverts_player_and_ai_moves() -> None:
    routes.set_current_mode(config.MODE_VS_AI)
    routes.make_move({"row": 7, "col": 7})

    state = routes.undo_move()

    assert state["move_count"] == 0
    assert state["current_player"] == int(Player.BLACK)
    assert state["last_move"] is None


def test_local_2p_undo_reverts_one_move() -> None:
    routes.make_move({"row": 7, "col": 7})
    routes.make_move({"row": 7, "col": 8})

    state = routes.undo_move()

    assert state["mode"] == config.MODE_LOCAL_2P
    assert state["move_count"] == 1
    assert state["current_player"] == int(Player.WHITE)


def test_switching_mode_resets_game() -> None:
    routes.make_move({"row": 7, "col": 7})

    state = routes.change_mode({"mode": config.MODE_VS_AI})

    assert state["mode"] == config.MODE_VS_AI
    assert state["move_count"] == 0
    assert state["current_player"] == int(Player.BLACK)
