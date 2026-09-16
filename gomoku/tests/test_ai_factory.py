from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku import config
from gomoku.ai.factory import create_ai
from gomoku.ai.hard_ai import HardAI
from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.simple_ai import SimpleAI


def test_factory_maps_enabled_difficulties() -> None:
    assert isinstance(create_ai(config.AI_DIFFICULTY_SIMPLE), SimpleAI)
    assert isinstance(create_ai(config.AI_DIFFICULTY_NORMAL), NormalAI)
    assert isinstance(create_ai(config.AI_DIFFICULTY_HARD), HardAI)
