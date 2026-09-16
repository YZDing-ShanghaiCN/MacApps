"""Deterministic HardAI arena: hard-vs-hard or hard-vs-normal diagnostics."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.arena import DEFAULT_ARENA_OPENINGS  # noqa: E402
from gomoku.ai.hard_arena import (  # noqa: E402
    compare_hard_configs,
    compare_hard_vs_normal,
    load_hard_config,
)
from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG  # noqa: E402
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG  # noqa: E402
from gomoku.ai.opening_generator import generate_openings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic HardAI arena. HardAI engines run with a "
            "never-advancing clock and mcts_node_capacity (clean exit); "
            "NormalAI engines run on node budgets. JSON configs may contain "
            "any HardAIConfig fields merged with the defaults."
        )
    )
    parser.add_argument("--engine-a", default="hard", choices=("hard", "normal"))
    parser.add_argument("--engine-b", default="hard", choices=("hard", "normal"))
    parser.add_argument("--config-a", type=Path)
    parser.add_argument("--config-b", type=Path)
    parser.add_argument("--mcts-capacity", type=int, default=2_000)
    parser.add_argument("--normal-node-budget", type=int, default=2_000)
    parser.add_argument("--max-moves", type=int, default=100)
    parser.add_argument(
        "--opening-mode",
        default="fixed",
        choices=("fixed", "generated"),
        help=(
            "fixed: the --openings suite (fast smoke); "
            "generated: reproducible diverse legal openings."
        ),
    )
    parser.add_argument(
        "--openings",
        default="default",
        choices=("default", "empty"),
        help=(
            "Fixed-mode opening suite: default: 5 fixed openings, "
            "empty: no opening stones."
        ),
    )
    parser.add_argument(
        "--opening-seed",
        type=int,
        default=0,
        help="RNG seed for generated openings (deterministic).",
    )
    parser.add_argument(
        "--opening-count",
        type=int,
        default=16,
        help="Number of generated openings (each played with both colors).",
    )
    parser.add_argument(
        "--opening-length",
        type=int,
        default=4,
        help="Minimum generated opening length in stones.",
    )
    parser.add_argument(
        "--opening-length-max",
        type=int,
        default=None,
        help="Optional maximum opening length (per-opening range).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the aggregate report and complete move records as JSON.",
    )
    args = parser.parse_args()

    hard_a = (
        load_hard_config(args.config_a, DEFAULT_HARD_AI_CONFIG)
        if args.config_a
        else DEFAULT_HARD_AI_CONFIG
    )
    hard_b = (
        load_hard_config(args.config_b, DEFAULT_HARD_AI_CONFIG)
        if args.config_b
        else DEFAULT_HARD_AI_CONFIG
    )
    if args.opening_mode == "generated":
        openings = generate_openings(
            seed=args.opening_seed,
            count=args.opening_count,
            length=args.opening_length,
            size=DEFAULT_HARD_AI_CONFIG.board_size,
            length_max=args.opening_length_max,
        )
        opening_kwargs = dict(
            opening_mode="generated",
            opening_seed=args.opening_seed,
            opening_length_min=args.opening_length,
            opening_length_max=(
                args.opening_length_max
                if args.opening_length_max is not None
                else args.opening_length
            ),
        )
        print(
            f"openings=generated seed={args.opening_seed} "
            f"count={len(openings)} length={args.opening_length}"
            f"-{args.opening_length_max or args.opening_length}"
        )
    else:
        openings = ((),) if args.openings == "empty" else DEFAULT_ARENA_OPENINGS
        opening_kwargs = dict(opening_mode="fixed")

    if args.engine_a == args.engine_b == "hard":
        summary = compare_hard_configs(
            hard_a,
            hard_b,
            mcts_capacity=args.mcts_capacity,
            max_moves=args.max_moves,
            openings=openings,
            **opening_kwargs,
        )
    elif args.engine_a == "hard" and args.engine_b == "normal":
        summary = compare_hard_vs_normal(
            hard_a,
            DEFAULT_NORMAL_AI_CONFIG,
            mcts_capacity=args.mcts_capacity,
            normal_node_budget=args.normal_node_budget,
            max_moves=args.max_moves,
            openings=openings,
            **opening_kwargs,
        )
    elif args.engine_a == "normal" and args.engine_b == "hard":
        summary = compare_hard_vs_normal(
            hard_b,
            DEFAULT_NORMAL_AI_CONFIG,
            mcts_capacity=args.mcts_capacity,
            normal_node_budget=args.normal_node_budget,
            max_moves=args.max_moves,
            openings=openings,
            **opening_kwargs,
        )
    else:
        raise SystemExit(
            "normal-vs-normal belongs to compare_normal_ai_configs.py; "
            "this arena compares HardAI against HardAI or NormalAI."
        )

    print(
        f"games={summary.games} draws={summary.draws} "
        f"recommended={summary.recommended_label or 'inconclusive'}"
    )
    for label in sorted(summary.wins):
        low, high = summary.score_confidence_95[label]
        print(
            f"{label}: wins={summary.wins[label]} "
            f"score={summary.score_rate[label]:.3f} "
            f"95%=[{low:.3f},{high:.3f}] "
            f"elo={summary.elo_difference[label]:+.1f} "
            f"avg_mcts_sims={summary.average_mcts_sims[label]:.1f} "
            f"tactic_hit={summary.tactic_hit_rate[label]:.3f} "
            f"timeout={summary.timeout_rate[label]:.3f}"
        )
    if args.output:
        args.output.write_text(
            json.dumps(asdict(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"report={args.output}")


if __name__ == "__main__":
    main()
