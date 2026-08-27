"""Shared AI construction for Pygame and Web adapters."""

from __future__ import annotations

from gomoku import config
from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.simple_ai import SimpleAI
from gomoku.ai.simple_ai_config import DEFAULT_SIMPLE_AI_CONFIG, SimpleAIConfig
from gomoku.core.enums import Player


def create_ai(
    difficulty: str,
    player: Player | int = Player.WHITE,
    *,
    simple_config: SimpleAIConfig = DEFAULT_SIMPLE_AI_CONFIG,
):
    if difficulty == config.AI_DIFFICULTY_SIMPLE:
        return SimpleAI(player, config=simple_config)
    if difficulty == config.AI_DIFFICULTY_NORMAL:
        return NormalAI(player)
    raise ValueError(f"AI difficulty is not available: {difficulty}.")
