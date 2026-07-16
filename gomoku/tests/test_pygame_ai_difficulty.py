from pathlib import Path
import sys


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
