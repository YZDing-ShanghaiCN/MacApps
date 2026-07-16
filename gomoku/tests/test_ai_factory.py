from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku import config
from gomoku.ai.factory import create_ai
from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.simple_ai import SimpleAI


def test_factory_maps_enabled_difficulties() -> None:
    assert isinstance(create_ai(config.AI_DIFFICULTY_SIMPLE), SimpleAI)
    assert isinstance(create_ai(config.AI_DIFFICULTY_NORMAL), NormalAI)


def test_factory_keeps_hard_unavailable() -> None:
    with pytest.raises(ValueError):
        create_ai(config.AI_DIFFICULTY_HARD)
