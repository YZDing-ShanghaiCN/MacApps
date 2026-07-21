"""Deterministic head-to-head diagnostics for NormalAI configurations."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
from pathlib import Path
from typing import Any, Mapping

from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.normal_ai_config import NormalAIConfig
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win


Move = tuple[int, int]
Opening = tuple[tuple[int, int, Player], ...]

DEFAULT_ARENA_OPENINGS: tuple[Opening, ...] = (
    (),
    (
        (7, 7, Player.BLACK),
        (7, 8, Player.WHITE),
    ),
    (
        (7, 7, Player.BLACK),
        (8, 8, Player.WHITE),
        (6, 8, Player.BLACK),
        (8, 6, Player.WHITE),
    ),
)


@dataclass(frozen=True)
class GameResult:
    winner_label: str | None
    winner: Player | None
    move_count: int
    nodes: Mapping[str, int]
    completed_depth_total: Mapping[str, int]
    searches: Mapping[str, int]


@dataclass(frozen=True)
class MatchSummary:
    wins: Mapping[str, int]
    draws: int
    games: int
    average_nodes: Mapping[str, float]
    average_completed_depth: Mapping[str, float]


def load_config(path: str | Path, base: NormalAIConfig) -> NormalAIConfig:
    """Load checked NormalAIConfig overrides from a JSON object."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("NormalAI config JSON must contain an object.")
    known = {field.name for field in fields(NormalAIConfig)}
    unknown = sorted(set(payload) - known)
    if unknown:
        raise ValueError(f"Unknown NormalAI config fields: {', '.join(unknown)}")
    overrides: dict[str, Any] = dict(payload)
    for score_field in ("pattern_scores", "defense_pattern_scores"):
        if score_field not in overrides:
            continue
        supplied = overrides[score_field]
        if not isinstance(supplied, dict):
            raise ValueError(f"{score_field} must be a JSON object.")
        merged = dict(getattr(base, score_field))
        unknown_scores = sorted(set(supplied) - set(merged))
        if unknown_scores:
            raise ValueError(
                f"Unknown {score_field} keys: {', '.join(unknown_scores)}"
            )
        merged.update(supplied)
        overrides[score_field] = merged
    return replace(base, **overrides)


def play_game(
    black_config: NormalAIConfig,
    white_config: NormalAIConfig,
    *,
    black_label: str,
    white_label: str,
    opening: Opening = (),
    node_budget: int = 2_000,
    max_moves: int = 100,
) -> GameResult:
    """Play one reproducible game using node budgets instead of tight clocks."""

    board = Board(black_config.board_size)
    for expected_index, (row, col, player) in enumerate(opening):
        expected_player = Player.BLACK if expected_index % 2 == 0 else Player.WHITE
        if player != expected_player:
            raise ValueError("Opening stones must alternate from black to white.")
        board.place(row, col, player)
    current = Player.BLACK if len(opening) % 2 == 0 else Player.WHITE
    configs = {
        Player.BLACK: _arena_config(black_config, node_budget),
        Player.WHITE: _arena_config(white_config, node_budget),
    }
    labels = {Player.BLACK: black_label, Player.WHITE: white_label}
    ais = {
        player: NormalAI(player, config=configs[player])
        for player in (Player.BLACK, Player.WHITE)
    }
    nodes = {black_label: 0, white_label: 0}
    depths = {black_label: 0, white_label: 0}
    searches = {black_label: 0, white_label: 0}
    move_count = len(opening)

    while move_count < min(max_moves, board.size * board.size):
        move = ais[current].choose_move(board, player=current)
        if move is None:
            break
        board.place(*move, current)
        move_count += 1
        label = labels[current]
        stats = ais[current].last_search_stats
        nodes[label] += stats.nodes + stats.vcf_nodes
        depths[label] += stats.completed_depth
        searches[label] += 1
        if check_win(board, move[0], move[1], current):
            return GameResult(
                label,
                current,
                move_count,
                nodes,
                depths,
                searches,
            )
        current = current.opponent

    return GameResult(None, None, move_count, nodes, depths, searches)


def compare_configs(
    config_a: NormalAIConfig,
    config_b: NormalAIConfig,
    *,
    node_budget: int = 2_000,
    max_moves: int = 100,
    openings: tuple[Opening, ...] = DEFAULT_ARENA_OPENINGS,
) -> MatchSummary:
    """Play both color assignments for every opening and aggregate results."""

    labels = ("A", "B")
    wins = {label: 0 for label in labels}
    nodes = {label: 0 for label in labels}
    depths = {label: 0 for label in labels}
    searches = {label: 0 for label in labels}
    draws = 0
    games = 0
    for opening in openings:
        for black_config, white_config, black_label, white_label in (
            (config_a, config_b, "A", "B"),
            (config_b, config_a, "B", "A"),
        ):
            result = play_game(
                black_config,
                white_config,
                black_label=black_label,
                white_label=white_label,
                opening=opening,
                node_budget=node_budget,
                max_moves=max_moves,
            )
            games += 1
            if result.winner_label is None:
                draws += 1
            else:
                wins[result.winner_label] += 1
            for label in labels:
                nodes[label] += result.nodes[label]
                depths[label] += result.completed_depth_total[label]
                searches[label] += result.searches[label]

    return MatchSummary(
        wins=wins,
        draws=draws,
        games=games,
        average_nodes={
            label: nodes[label] / max(1, searches[label]) for label in labels
        },
        average_completed_depth={
            label: depths[label] / max(1, searches[label]) for label in labels
        },
    )


def _arena_config(config: NormalAIConfig, node_budget: int) -> NormalAIConfig:
    return replace(
        config,
        time_limit_ms=60_000,
        time_safety_margin_ms=0,
        max_nodes=max(1, node_budget),
    )
