"""Shared AI construction for Pygame and Web adapters."""

from __future__ import annotations

from gomoku import config
from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.simple_ai import SimpleAI
from gomoku.core.enums import Player


def create_ai(difficulty: str, player: Player | int = Player.WHITE):
    if difficulty == config.AI_DIFFICULTY_SIMPLE:
        return SimpleAI(player)
    if difficulty == config.AI_DIFFICULTY_NORMAL:
        return NormalAI(player)
    raise ValueError(f"AI difficulty is not available: {difficulty}.")
