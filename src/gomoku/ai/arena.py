"""Deterministic head-to-head diagnostics for NormalAI configurations."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
import math
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
    (
        (7, 7, Player.BLACK),
        (6, 7, Player.WHITE),
        (8, 8, Player.BLACK),
        (6, 8, Player.WHITE),
    ),
    (
        (7, 7, Player.BLACK),
        (8, 7, Player.WHITE),
        (6, 6, Player.BLACK),
        (8, 6, Player.WHITE),
    ),
)


@dataclass(frozen=True)
class RecordedMove:
    row: int
    col: int
    player: Player
    label: str
    completed_depth: int = 0
    nodes: int = 0
    vcf_nodes: int = 0
    budget_stopped: bool = False
    vcf_hit: bool = False


@dataclass(frozen=True)
class GameResult:
    winner_label: str | None
    winner: Player | None
    move_count: int
    nodes: Mapping[str, int]
    completed_depth_total: Mapping[str, int]
    searches: Mapping[str, int]
    budget_stops: Mapping[str, int]
    vcf_hits: Mapping[str, int]
    moves: tuple[RecordedMove, ...]


@dataclass(frozen=True)
class MatchSummary:
    wins: Mapping[str, int]
    wins_by_color: Mapping[str, Mapping[str, int]]
    draws: int
    games: int
    average_nodes: Mapping[str, float]
    average_completed_depth: Mapping[str, float]
    budget_stop_rate: Mapping[str, float]
    vcf_hit_rate: Mapping[str, float]
    score_rate: Mapping[str, float]
    score_confidence_95: Mapping[str, tuple[float, float]]
    elo_difference: Mapping[str, float]
    recommended_label: str | None
    game_records: tuple[GameResult, ...]


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

    if black_config.board_size != white_config.board_size:
        raise ValueError("Arena configurations must use the same board size.")
    if black_label == white_label:
        raise ValueError("Arena labels must be distinct.")
    board = Board(black_config.board_size)
    recorded_moves: list[RecordedMove] = []
    for expected_index, (row, col, player) in enumerate(opening):
        expected_player = Player.BLACK if expected_index % 2 == 0 else Player.WHITE
        if player != expected_player:
            raise ValueError("Opening stones must alternate from black to white.")
        board.place(row, col, player)
        recorded_moves.append(RecordedMove(row, col, player, "opening"))
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
    budget_stops = {black_label: 0, white_label: 0}
    vcf_hits = {black_label: 0, white_label: 0}
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
        budget_stops[label] += int(stats.timed_out)
        vcf_hit = stats.vcf_found or stats.defensive_vcf_detected
        vcf_hits[label] += int(vcf_hit)
        recorded_moves.append(
            RecordedMove(
                row=move[0],
                col=move[1],
                player=current,
                label=label,
                completed_depth=stats.completed_depth,
                nodes=stats.nodes,
                vcf_nodes=stats.vcf_nodes,
                budget_stopped=stats.timed_out,
                vcf_hit=vcf_hit,
            )
        )
        if check_win(board, move[0], move[1], current):
            return GameResult(
                label,
                current,
                move_count,
                nodes,
                depths,
                searches,
                budget_stops,
                vcf_hits,
                tuple(recorded_moves),
            )
        current = current.opponent

    return GameResult(
        None,
        None,
        move_count,
        nodes,
        depths,
        searches,
        budget_stops,
        vcf_hits,
        tuple(recorded_moves),
    )


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
    wins_by_color = {
        label: {"black": 0, "white": 0} for label in labels
    }
    nodes = {label: 0 for label in labels}
    depths = {label: 0 for label in labels}
    searches = {label: 0 for label in labels}
    budget_stops = {label: 0 for label in labels}
    vcf_hits = {label: 0 for label in labels}
    records: list[GameResult] = []
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
            records.append(result)
            if result.winner_label is None:
                draws += 1
            else:
                wins[result.winner_label] += 1
                color = "black" if result.winner == Player.BLACK else "white"
                wins_by_color[result.winner_label][color] += 1
            for label in labels:
                nodes[label] += result.nodes[label]
                depths[label] += result.completed_depth_total[label]
                searches[label] += result.searches[label]
                budget_stops[label] += result.budget_stops[label]
                vcf_hits[label] += result.vcf_hits[label]

    score_a = (wins["A"] + draws * 0.5) / max(1, games)
    score_rates = {"A": score_a, "B": 1.0 - score_a}
    confidence_a = _wilson_interval(wins["A"] + draws * 0.5, games)
    confidences = {
        "A": confidence_a,
        "B": (1.0 - confidence_a[1], 1.0 - confidence_a[0]),
    }
    elo_a = _elo_from_score(score_a)
    if confidence_a[0] > 0.5:
        recommended = "A"
    elif confidence_a[1] < 0.5:
        recommended = "B"
    else:
        recommended = None

    return MatchSummary(
        wins=wins,
        wins_by_color=wins_by_color,
        draws=draws,
        games=games,
        average_nodes={
            label: nodes[label] / max(1, searches[label]) for label in labels
        },
        average_completed_depth={
            label: depths[label] / max(1, searches[label]) for label in labels
        },
        budget_stop_rate={
            label: budget_stops[label] / max(1, searches[label])
            for label in labels
        },
        vcf_hit_rate={
            label: vcf_hits[label] / max(1, searches[label]) for label in labels
        },
        score_rate=score_rates,
        score_confidence_95=confidences,
        elo_difference={"A": elo_a, "B": -elo_a},
        recommended_label=recommended,
        game_records=tuple(records),
    )


def _wilson_interval(
    equivalent_wins: float,
    games: int,
    z_score: float = 1.96,
) -> tuple[float, float]:
    if games <= 0:
        return 0.0, 1.0
    proportion = equivalent_wins / games
    denominator = 1 + z_score**2 / games
    center = (proportion + z_score**2 / (2 * games)) / denominator
    margin = (
        z_score
        * math.sqrt(
            proportion * (1 - proportion) / games
            + z_score**2 / (4 * games**2)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _elo_from_score(score: float) -> float:
    bounded = max(0.001, min(0.999, score))
    return 400 * math.log10(bounded / (1 - bounded))


def _arena_config(config: NormalAIConfig, node_budget: int) -> NormalAIConfig:
    return replace(
        config,
        time_limit_ms=60_000,
        time_safety_margin_ms=0,
        max_nodes=max(1, node_budget),
    )
