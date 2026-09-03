from pathlib import Path
import sys
import time


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku import config
from gomoku.core.enums import Player
from gomoku.server import routes


def setup_function() -> None:
    routes.set_current_mode(config.MODE_LOCAL_2P)
    routes.set_current_difficulty(config.AI_DIFFICULTY_SIMPLE)
    routes.cancel_pending_ai()
    routes.game.reset()


def wait_for_ai() -> dict:
    deadline = time.monotonic() + 2
    while routes.default_session.ai_thinking and time.monotonic() < deadline:
        time.sleep(0.005)
    return routes.state_response()


def test_vs_ai_move_triggers_ai_response() -> None:
    routes.set_current_mode(config.MODE_VS_AI)

    routes.make_move({"row": 7, "col": 7})
    state = wait_for_ai()

    assert state["mode"] == config.MODE_VS_AI
    assert state["ai_player"] == int(Player.WHITE)
    assert state["move_count"] == 2
    assert state["board"][7][7] == int(Player.BLACK)
    assert state["last_move"]["player"] == int(Player.WHITE)
    assert state["current_player"] == int(Player.BLACK)


def test_vs_ai_move_count_increases_by_two_unless_game_ends() -> None:
    routes.set_current_mode(config.MODE_VS_AI)

    routes.make_move({"row": 7, "col": 7})
    state = wait_for_ai()

    if state["winner"] is None:
        assert state["move_count"] >= 2


def test_vs_ai_hard_difficulty_responds_with_mcts_stats() -> None:
    routes.set_current_mode(config.MODE_VS_AI)
    routes.set_current_difficulty(config.AI_DIFFICULTY_HARD)

    routes.make_move({"row": 7, "col": 7})
    state = wait_for_ai()

    assert state["ai_difficulty"] == config.AI_DIFFICULTY_HARD
    assert state["move_count"] == 2
    assert state["last_move"]["player"] == int(Player.WHITE)
    assert state["ai_decision"]["reason"] == "mcts_fallback"
    # Tactical stages always run now: on this near-empty board they
    # complete with not_found instead of being skipped by a precheck.
    assert state["ai_search_stats"]["vcf_status"] == "not_found"
    assert state["ai_search_stats"]["vct_status"] == "not_found"
    assert state["ai_search_stats"]["mcts_simulations"] > 0


def test_vs_ai_undo_reverts_player_and_ai_moves() -> None:
    routes.set_current_mode(config.MODE_VS_AI)
    routes.make_move({"row": 7, "col": 7})
    wait_for_ai()

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
