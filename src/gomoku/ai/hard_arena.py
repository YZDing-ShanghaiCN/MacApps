"""Deterministic head-to-head diagnostics for HardAI.

Mirrors :mod:`gomoku.ai.arena` (NormalAI) for HardAI-versus-HardAI config
comparisons and HardAI-versus-NormalAI cross-engine matches. Games are
reproducible: HardAI runs with a never-advancing injected clock (tactical
stages finish depth-bounded, MCTS exits cleanly at ``mcts_node_capacity``)
and NormalAI runs on node budgets, so no wall-clock timings leak in.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
import json
from pathlib import Path

from gomoku.ai.arena import (
    DEFAULT_ARENA_OPENINGS,
    Opening,
    elo_from_score,
    wilson_interval,
)
from gomoku.ai.hard_ai import HardAI, HardAISearchStats
from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG, HardAIConfig
from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG, NormalAIConfig
from gomoku.ai.opening_generator import validate_opening
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win

Move = tuple[int, int]

TACTIC_REASONS = ("vcf_forced_win", "vct_forced_win", "tactical_defense")

NORMAL_REASON = "normal_search"


@dataclass(frozen=True)
class RecordedHardMove:
    row: int
    col: int
    player: Player
    label: str
    reason: str = ""
    mcts_sims: int = 0
    timed_out: bool = False
    tactic_hit: bool = False


@dataclass(frozen=True)
class HardGameResult:
    winner_label: str | None
    winner: Player | None
    move_count: int
    searches: dict[str, int]
    timed_outs: dict[str, int]
    tactic_hits: dict[str, int]
    mcts_sims: dict[str, int]
    moves: tuple[RecordedHardMove, ...]
    opening: Opening = ()
    black_label: str = ""
    white_label: str = ""


@dataclass(frozen=True)
class HardMatchSummary:
    wins: dict[str, int]
    draws: int
    games: int
    score_rate: dict[str, float]
    score_confidence_95: dict[str, tuple[float, float]]
    elo_difference: dict[str, float]
    average_mcts_sims: dict[str, float]
    tactic_hit_rate: dict[str, float]
    timeout_rate: dict[str, float]
    recommended_label: str | None
    game_records: tuple[HardGameResult, ...]
    opening_mode: str = "fixed"
    opening_seed: int | None = None
    opening_count: int = 0
    opening_length_min: int | None = None
    opening_length_max: int | None = None
    openings: tuple[Opening, ...] = ()


def load_hard_config(path: str | Path, base: HardAIConfig) -> HardAIConfig:
    """Load checked HardAIConfig overrides from a JSON object."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HardAI config JSON must contain an object.")
    known = {field.name for field in fields(HardAIConfig)}
    unknown = sorted(set(payload) - known)
    if unknown:
        raise ValueError(f"Unknown HardAI config fields: {', '.join(unknown)}")
    return replace(base, **payload)


def _move_record(
    ai, move: Move, player: Player, label: str
) -> RecordedHardMove:
    stats = getattr(ai, "last_search_stats", None)
    if isinstance(stats, HardAISearchStats):
        return RecordedHardMove(
            row=move[0],
            col=move[1],
            player=player,
            label=label,
            reason=stats.decision_reason,
            mcts_sims=stats.mcts_simulations,
            timed_out=stats.timed_out,
            tactic_hit=stats.decision_reason in TACTIC_REASONS,
        )
    if stats is not None:
        return RecordedHardMove(
            row=move[0],
            col=move[1],
            player=player,
            label=label,
            reason=NORMAL_REASON,
            mcts_sims=0,
            timed_out=bool(getattr(stats, "timed_out", False)),
            tactic_hit=bool(
                getattr(stats, "vcf_found", False)
                or getattr(stats, "defensive_vcf_detected", False)
            ),
        )
    return RecordedHardMove(
        row=move[0], col=move[1], player=player, label=label
    )


def play_hard_game(
    black_ai,
    white_ai,
    *,
    black_label: str,
    white_label: str,
    opening: Opening = (),
    max_moves: int = 100,
) -> HardGameResult:
    """Play one game between two constructed AI instances.

    Either side may be a :class:`HardAI` or a :class:`NormalAI`; both must
    expose ``choose_move(board, player=...)`` and a stats attribute.
    """

    if black_label == white_label:
        raise ValueError("Arena labels must be distinct.")
    board = Board()
    if not validate_opening(opening, board.size):
        raise ValueError(
            f"Invalid opening: {opening!r} is terminal, illegal or "
            "not strictly alternating."
        )
    recorded: list[RecordedHardMove] = []
    for expected_index, (row, col, player) in enumerate(opening):
        expected_player = Player.BLACK if expected_index % 2 == 0 else Player.WHITE
        if player != expected_player:
            raise ValueError("Opening stones must alternate from black to white.")
        board.place(row, col, player)
        recorded.append(RecordedHardMove(row, col, player, "opening"))
    current = Player.BLACK if len(opening) % 2 == 0 else Player.WHITE
    ais = {Player.BLACK: black_ai, Player.WHITE: white_ai}
    labels = {Player.BLACK: black_label, Player.WHITE: white_label}
    searches = {black_label: 0, white_label: 0}
    timed_outs = {black_label: 0, white_label: 0}
    tactic_hits = {black_label: 0, white_label: 0}
    mcts_sims = {black_label: 0, white_label: 0}
    move_count = len(opening)

    while move_count < min(max_moves, board.size * board.size):
        move = ais[current].choose_move(board, player=current)
        if move is None:
            break
        board.place(*move, current)
        move_count += 1
        label = labels[current]
        searches[label] += 1
        record = _move_record(ais[current], move, current, label)
        timed_outs[label] += int(record.timed_out)
        tactic_hits[label] += int(record.tactic_hit)
        mcts_sims[label] += record.mcts_sims
        recorded.append(record)
        if check_win(board, move[0], move[1], current):
            return HardGameResult(
                label,
                current,
                move_count,
                searches,
                timed_outs,
                tactic_hits,
                mcts_sims,
                tuple(recorded),
                opening=opening,
                black_label=black_label,
                white_label=white_label,
            )
        current = current.opponent

    return HardGameResult(
        None,
        None,
        move_count,
        searches,
        timed_outs,
        tactic_hits,
        mcts_sims,
        tuple(recorded),
        opening=opening,
        black_label=black_label,
        white_label=white_label,
    )


def _hard_ai(config: HardAIConfig, player: Player, mcts_capacity: int) -> HardAI:
    return HardAI(
        player,
        config=replace(config, mcts_node_capacity=mcts_capacity),
        clock=lambda: 0.0,
    )


def _normal_ai(config: NormalAIConfig, player: Player, node_budget: int) -> NormalAI:
    return NormalAI(
        player,
        config=replace(
            config,
            time_limit_ms=60_000,
            time_safety_margin_ms=0,
            max_nodes=max(1, node_budget),
        ),
    )


def compare_hard_configs(
    config_a: HardAIConfig,
    config_b: HardAIConfig,
    *,
    mcts_capacity: int = 2_000,
    max_moves: int = 100,
    openings: tuple[Opening, ...] = DEFAULT_ARENA_OPENINGS,
    opening_mode: str = "fixed",
    opening_seed: int | None = None,
    opening_length_min: int | None = None,
    opening_length_max: int | None = None,
) -> HardMatchSummary:
    """Play both color assignments for every opening and aggregate."""

    labels = ("A", "B")
    wins = {label: 0 for label in labels}
    searches = {label: 0 for label in labels}
    timed_outs = {label: 0 for label in labels}
    tactic_hits = {label: 0 for label in labels}
    mcts_sims = {label: 0 for label in labels}
    records: list[HardGameResult] = []
    draws = 0
    games = 0
    for opening in openings:
        for black_config, white_config, black_label, white_label in (
            (config_a, config_b, "A", "B"),
            (config_b, config_a, "B", "A"),
        ):
            result = play_hard_game(
                _hard_ai(black_config, Player.BLACK, mcts_capacity),
                _hard_ai(white_config, Player.WHITE, mcts_capacity),
                black_label=black_label,
                white_label=white_label,
                opening=opening,
                max_moves=max_moves,
            )
            games += 1
            records.append(result)
            if result.winner_label is None:
                draws += 1
            else:
                wins[result.winner_label] += 1
            for label in labels:
                searches[label] += result.searches[label]
                timed_outs[label] += result.timed_outs[label]
                tactic_hits[label] += result.tactic_hits[label]
                mcts_sims[label] += result.mcts_sims[label]
    return _summarize(
        wins, draws, games, searches, timed_outs, tactic_hits, mcts_sims,
        records,
        openings=openings,
        opening_mode=opening_mode,
        opening_seed=opening_seed,
        opening_length_min=opening_length_min,
        opening_length_max=opening_length_max,
    )


def compare_hard_vs_normal(
    hard_config: HardAIConfig,
    normal_config: NormalAIConfig,
    *,
    mcts_capacity: int = 2_000,
    normal_node_budget: int = 2_000,
    max_moves: int = 100,
    openings: tuple[Opening, ...] = DEFAULT_ARENA_OPENINGS,
    opening_mode: str = "fixed",
    opening_seed: int | None = None,
    opening_length_min: int | None = None,
    opening_length_max: int | None = None,
) -> HardMatchSummary:
    """Cross-engine match: HardAI vs NormalAI, both color assignments."""

    labels = ("hard", "normal")
    wins = {label: 0 for label in labels}
    searches = {label: 0 for label in labels}
    timed_outs = {label: 0 for label in labels}
    tactic_hits = {label: 0 for label in labels}
    mcts_sims = {label: 0 for label in labels}
    records: list[HardGameResult] = []
    draws = 0
    games = 0
    for opening in openings:
        for black_config, white_config, black_label, white_label in (
            (hard_config, normal_config, "hard", "normal"),
            (normal_config, hard_config, "normal", "hard"),
        ):
            result = play_hard_game(
                _hard_ai(black_config, Player.BLACK, mcts_capacity)
                if black_label == "hard"
                else _normal_ai(black_config, Player.BLACK, normal_node_budget),
                _hard_ai(white_config, Player.WHITE, mcts_capacity)
                if white_label == "hard"
                else _normal_ai(white_config, Player.WHITE, normal_node_budget),
                black_label=black_label,
                white_label=white_label,
                opening=opening,
                max_moves=max_moves,
            )
            games += 1
            records.append(result)
            if result.winner_label is None:
                draws += 1
            else:
                wins[result.winner_label] += 1
            for label in labels:
                searches[label] += result.searches[label]
                timed_outs[label] += result.timed_outs[label]
                tactic_hits[label] += result.tactic_hits[label]
                mcts_sims[label] += result.mcts_sims[label]
    return _summarize(
        wins, draws, games, searches, timed_outs, tactic_hits, mcts_sims,
        records,
        openings=openings,
        opening_mode=opening_mode,
        opening_seed=opening_seed,
        opening_length_min=opening_length_min,
        opening_length_max=opening_length_max,
    )


def _summarize(
    wins: dict[str, int],
    draws: int,
    games: int,
    searches: dict[str, int],
    timed_outs: dict[str, int],
    tactic_hits: dict[str, int],
    mcts_sims: dict[str, int],
    records: list[HardGameResult],
    *,
    openings: tuple[Opening, ...] = (),
    opening_mode: str = "fixed",
    opening_seed: int | None = None,
    opening_length_min: int | None = None,
    opening_length_max: int | None = None,
) -> HardMatchSummary:
    labels = sorted(wins)
    score_rates = {
        label: (wins[label] + draws * 0.5) / max(1, games) for label in labels
    }
    first = labels[0]
    confidence = wilson_interval(wins[first] + draws * 0.5, games)
    confidences = {
        first: confidence,
        labels[1]: (1.0 - confidence[1], 1.0 - confidence[0]),
    }
    elo_first = elo_from_score(score_rates[first])
    if confidence[0] > 0.5:
        recommended = first
    elif confidence[1] < 0.5:
        recommended = labels[1]
    else:
        recommended = None
    return HardMatchSummary(
        wins=wins,
        draws=draws,
        games=games,
        score_rate=score_rates,
        score_confidence_95=confidences,
        elo_difference={first: elo_first, labels[1]: -elo_first},
        average_mcts_sims={
            label: mcts_sims[label] / max(1, searches[label])
            for label in labels
        },
        tactic_hit_rate={
            label: tactic_hits[label] / max(1, searches[label])
            for label in labels
        },
        timeout_rate={
            label: timed_outs[label] / max(1, searches[label])
            for label in labels
        },
        recommended_label=recommended,
        game_records=tuple(records),
        opening_mode=opening_mode,
        opening_seed=opening_seed,
        opening_count=len(openings),
        opening_length_min=opening_length_min,
        opening_length_max=opening_length_max,
        openings=openings,
    )
