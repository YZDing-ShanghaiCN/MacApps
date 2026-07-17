from pathlib import Path
import sys
import queue
import threading


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku import config
from gomoku.adapters.pygame_app import PygameGomokuApp
from gomoku.ai.normal_ai import NormalAI
from gomoku.core.enums import Player
from gomoku.core.game import GomokuGame


def lightweight_app() -> PygameGomokuApp:
    app = PygameGomokuApp.__new__(PygameGomokuApp)
    app.game = GomokuGame()
    app.mode = config.MODE_VS_AI
    app.ai_player = Player.WHITE
    app.ai_difficulty = config.AI_DIFFICULTY_SIMPLE
    app.message = ""
    app.ai_thinking = False
    app._ai_generation = 0
    app._ai_results = queue.Queue()
    app._ai_cancel_event = None
    return app


def test_pygame_selects_normal_and_restart_preserves_it() -> None:
    app = lightweight_app()
    app.set_difficulty(config.AI_DIFFICULTY_NORMAL)
    assert app.ai_difficulty == config.AI_DIFFICULTY_NORMAL
    assert isinstance(app.ai, NormalAI)

    app.reset_game()
    assert app.ai_difficulty == config.AI_DIFFICULTY_NORMAL


def test_pygame_keeps_hard_in_development() -> None:
    app = lightweight_app()
    app.set_difficulty(config.AI_DIFFICULTY_HARD)
    assert app.ai_difficulty == config.AI_DIFFICULTY_SIMPLE
    assert "coming soon" in app.message


def test_pygame_ai_search_runs_in_background_and_stale_result_is_cancelled() -> None:
    release = threading.Event()

    class SlowAI:
        def choose_move(self, board, **_kwargs):
            release.wait(1)
            return (7, 8)

    app = lightweight_app()
    app.ai = SlowAI()
    app.game.start_timer()
    app.game.make_move(7, 7)
    app.play_ai_move((7, 7))
    assert app.ai_thinking is True

    app.reset_game()
    release.set()
    assert app.ai_thinking is False
    assert app.game.move_history == []


def test_pygame_stale_result_cannot_hide_current_ai_result() -> None:
    app = lightweight_app()
    app.game.start_timer()
    app.game.make_move(7, 7)
    app.ai_thinking = True
    app._ai_generation = 2
    app._ai_results.put((2, (7, 8), None))
    app._ai_results.put((1, (0, 0), None))

    app.poll_ai_result()

    assert app.game.board.grid[7][8] == Player.WHITE
    assert app.game.board.grid[0][0] == Player.EMPTY
    assert app.ai_thinking is False
