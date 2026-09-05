"""Generate self-play training data with deterministic pure-MCTS games."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG  # noqa: E402
from gomoku.ai.selfplay import generate_selfplay_data  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate gzip-JSONL self-play records: per move, two "
            "player-perspective planes, the MCTS root visit distribution as "
            "policy target, and the retroactive game outcome +1/-1/0 from "
            "the mover's perspective."
        )
    )
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--output", type=Path, default="selfplay.jsonl.gz")
    parser.add_argument("--mcts-capacity", type=int, default=800)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--temperature-cutoff", type=int, default=12)
    parser.add_argument("--max-moves", type=int, default=120)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument(
        "--model",
        type=Path,
        help="Optional trained model for priors (policy improvement loop).",
    )
    args = parser.parse_args()

    provider = None
    if args.model:
        from gomoku.ai.model_provider import ModelPolicyValueProvider

        provider = ModelPolicyValueProvider(
            DEFAULT_HARD_AI_CONFIG, str(args.model)
        )
        print(f"priors={args.model}")

    written = generate_selfplay_data(
        DEFAULT_HARD_AI_CONFIG,
        games=args.games,
        output_path=args.output,
        seed=args.seed,
        mcts_capacity=args.mcts_capacity,
        temperature=args.temperature,
        temperature_cutoff=args.temperature_cutoff,
        max_moves=args.max_moves,
        provider=provider,
        start_index=args.start_index,
    )
    print(f"records={written} output={args.output}")


if __name__ == "__main__":
    main()
