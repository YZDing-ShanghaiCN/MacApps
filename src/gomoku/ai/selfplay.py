"""Self-play data generation for training the HardAI policy-value network.

Each game is played by pure MCTS (no VCF/VCT pipeline, whose hard decisions
would contaminate the visit-distribution labels) with an injectable
never-advancing clock and ``mcts_node_capacity`` as the deterministic sim
budget. Diversity comes from temperature sampling over the root visit
distribution; game outcomes are filled in retroactively as +1 / -1 / 0 from
each record's mover perspective.
"""

from __future__ import annotations

import gzip
import json
import random
from dataclasses import replace
from pathlib import Path

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG, HardAIConfig
from gomoku.ai.mcts import MCTS, MCTSRootMove
from gomoku.ai.model import encode_position
from gomoku.ai.policy_value import (
    HeuristicPolicyValueProvider,
    PolicyValueProvider,
)
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win

Move = tuple[int, int]

SelfPlayRecord = dict


def visit_distribution(root_moves: tuple[MCTSRootMove, ...], size: int) -> list[float]:
    """Visit proportions over all ``size * size`` cells (0 for unvisited).

    An empty ``root_moves`` (only the empty-board fast path) yields the
    uniform distribution over the whole board.
    """

    cells = size * size
    total = sum(item.visits for item in root_moves)
    if total <= 0:
        distribution = [0.0] * cells
        if root_moves:
            # Immediate-win short circuit: no simulations ran, so put all
            # mass on the winning move instead of teaching uniform noise.
            item = root_moves[0]
            distribution[item.move[0] * size + item.move[1]] = 1.0
            return distribution
        uniform = 1.0 / cells
        return [uniform] * cells
    distribution = [0.0] * cells
    for item in root_moves:
        distribution[item.move[0] * size + item.move[1]] = (
            item.visits / total
        )
    return distribution


def sample_move(
    root_moves: tuple[MCTSRootMove, ...],
    temperature: float,
    rng: random.Random,
    size: int,
    fallback: Move | None = None,
) -> Move | None:
    """Sample the played move from the visit distribution raised to 1/tau.

    ``temperature <= 0`` picks the most-visited move (ties: center-nearest).
    """

    if not root_moves:
        return fallback
    if temperature <= 0.0:
        return max(
            root_moves,
            key=lambda item: (
                item.visits,
                -_center_distance(size, item.move),
                -item.move[0],
                -item.move[1],
            ),
        ).move
    weights = [
        float(item.visits) ** (1.0 / temperature) for item in root_moves
    ]
    total = sum(weights)
    if total <= 0.0:
        return sample_move(root_moves, 0.0, rng, size, fallback)
    moves = [item.move for item in root_moves]
    return rng.choices(moves, weights=weights, k=1)[0]


def _center_distance(size: int, move: Move) -> float:
    center = (size - 1) / 2
    return max(abs(move[0] - center), abs(move[1] - center))


def play_selfplay_game(
    config: HardAIConfig = DEFAULT_HARD_AI_CONFIG,
    *,
    seed: int,
    mcts_capacity: int,
    temperature: float = 1.0,
    temperature_cutoff: int = 12,
    max_moves: int = 120,
    provider: PolicyValueProvider | None = None,
) -> list[SelfPlayRecord]:
    """Play one pure-MCTS game and return its labeled records."""

    rng = random.Random(seed)
    board = Board(config.board_size)
    mcts_config = replace(config, mcts_node_capacity=mcts_capacity)
    mcts = MCTS(
        mcts_config,
        provider or HeuristicPolicyValueProvider(mcts_config),
        clock=lambda: 0.0,
    )
    records: list[SelfPlayRecord] = []
    current = Player.BLACK
    played_moves = 0
    winner: Player | None = None
    limit = min(max_moves, board.size * board.size)

    while played_moves < limit:
        result = mcts.search(
            board,
            current,
            time_budget_ms=1_000_000.0,
        )
        move = result.move
        if move is None:
            break
        tau = (
            temperature
            if played_moves < temperature_cutoff
            else 0.0
        )
        played = sample_move(
            result.root_moves, tau, rng, board.size, fallback=move
        )
        records.append(
            {
                "player": int(current),
                "move": [played[0], played[1]],
                "planes": encode_position(board, current).tolist(),
                "policy": visit_distribution(result.root_moves, board.size),
                "outcome": 0,
            }
        )
        board.place(*played, current)
        played_moves += 1
        if check_win(board, played[0], played[1], current):
            winner = current
            break
        current = current.opponent

    outcome = 0 if winner is None else 1
    for record in records:
        if winner is None:
            record["outcome"] = 0
        else:
            record["outcome"] = (
                outcome if record["player"] == int(winner) else -outcome
            )
    return records


def generate_selfplay_data(
    config: HardAIConfig = DEFAULT_HARD_AI_CONFIG,
    *,
    games: int,
    output_path: str | Path,
    seed: int = 0,
    mcts_capacity: int = 800,
    temperature: float = 1.0,
    temperature_cutoff: int = 12,
    max_moves: int = 120,
    provider: PolicyValueProvider | None = None,
    start_index: int = 0,
    progress_every: int = 10,
) -> int:
    """Write ``games`` gzip-JSONL self-play games; returns records written.

    The gzip stream uses ``mtime=0`` so identical arguments produce
    byte-identical files; ``start_index > 0`` appends a new gzip member for
    resuming (readers transparently concatenate members).
    """

    mode = "ab" if start_index else "wb"
    written = 0
    with open(str(output_path), mode) as raw:
        for game_index in range(start_index, start_index + games):
            records = play_selfplay_game(
                config,
                seed=seed + game_index,
                mcts_capacity=mcts_capacity,
                temperature=temperature,
                temperature_cutoff=temperature_cutoff,
                max_moves=max_moves,
                provider=provider,
            )
            payload = "".join(
                json.dumps(record) + "\n" for record in records
            ).encode("utf-8")
            raw.write(gzip.compress(payload, compresslevel=9, mtime=0))
            written += len(records)
            if (game_index + 1) % progress_every == 0:
                print(
                    f"game {game_index + 1}/{start_index + games} "
                    f"records={written}",
                    flush=True,
                )
    return written
