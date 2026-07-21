"""Compare two NormalAI JSON configurations with deterministic self-play."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.arena import compare_configs, load_config  # noqa: E402
from gomoku.ai.normal_ai_config import (  # noqa: E402
    DEFAULT_NORMAL_AI_CONFIG,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare NormalAI configuration A and B. JSON files may contain "
            "any NormalAIConfig fields; pattern score objects are merged with defaults."
        )
    )
    parser.add_argument("--config-a", type=Path)
    parser.add_argument("--config-b", type=Path)
    parser.add_argument("--node-budget", type=int, default=2_000)
    parser.add_argument("--max-moves", type=int, default=100)
    args = parser.parse_args()

    config_a = (
        load_config(args.config_a, DEFAULT_NORMAL_AI_CONFIG)
        if args.config_a
        else DEFAULT_NORMAL_AI_CONFIG
    )
    config_b = (
        load_config(args.config_b, DEFAULT_NORMAL_AI_CONFIG)
        if args.config_b
        else DEFAULT_NORMAL_AI_CONFIG
    )
    summary = compare_configs(
        config_a,
        config_b,
        node_budget=args.node_budget,
        max_moves=args.max_moves,
    )
    print(f"games={summary.games} draws={summary.draws}")
    for label in ("A", "B"):
        print(
            f"{label}: wins={summary.wins[label]} "
            f"avg_nodes={summary.average_nodes[label]:.1f} "
            f"avg_depth={summary.average_completed_depth[label]:.2f}"
        )


if __name__ == "__main__":
    main()
