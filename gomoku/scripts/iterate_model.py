"""One iteration of the self-play training loop.

Cycle: (1) generate self-play games (with the current model's priors once
one exists), (2) train a candidate network on the deterministic replay
buffer (a bounded sample of the most recent self-play shards, not just the
newest file), (3) arena the candidate-model HardAI against the current-model
HardAI (or the heuristic provider on the first run), (4) keep the candidate
as ``current.pt`` only if its 95% Wilson score interval is entirely above
0.5. Each run appends one JSON line to ``runs.jsonl`` under the model
directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.promotion import should_promote  # noqa: E402
from gomoku.ai.replay import select_replay_files  # noqa: E402


def _run(arguments: list[str]) -> str:
    print(f"+ {' '.join(arguments)}", flush=True)
    completed = subprocess.run(
        [sys.executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if output:
        print(output, end="", flush=True)
    return completed.stdout or ""


def _parse_train_records(output: str) -> int | None:
    for line in reversed(output.splitlines()):
        for token in line.split():
            if token.startswith("train_records="):
                try:
                    return int(token.split("=", 1)[1])
                except ValueError:
                    return None
    return None


def _load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Self-play -> train -> arena -> keep-if-stronger cycle."
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=PROJECT_ROOT / "models",
        help="Checkpoints, data and run log live here (default: gomoku/models).",
    )
    parser.add_argument("--selfplay-games", type=int, default=100)
    parser.add_argument("--mcts-capacity", type=int, default=800)
    parser.add_argument("--train-epochs", type=int, default=3)
    parser.add_argument(
        "--replay-window",
        type=int,
        default=8,
        help="Train on the newest N self-play shards (N=0 means all).",
    )
    parser.add_argument(
        "--replay-max-records",
        type=int,
        default=200_000,
        help="Upper bound of sampled training records (0 = unlimited).",
    )
    parser.add_argument(
        "--arena-opening-mode",
        default="generated",
        choices=("fixed", "generated"),
        help=(
            "Promotion match openings: generated is a serious configurable "
            "match, fixed is the fast smoke suite."
        ),
    )
    parser.add_argument(
        "--arena-opening-count",
        type=int,
        default=16,
        help="Generated openings per promotion match (played with both colors).",
    )
    parser.add_argument(
        "--arena-opening-seed",
        type=int,
        default=0,
        help="Seed for generated promotion openings (deterministic).",
    )
    parser.add_argument(
        "--arena-opening-length",
        type=int,
        default=4,
        help="Generated opening length in stones.",
    )
    parser.add_argument(
        "--arena-mcts-capacity",
        type=int,
        default=None,
        help="MCTS capacity for the promotion match (default: --mcts-capacity).",
    )
    parser.add_argument(
        "--cuda",
        action="store_true",
        help="Train on CUDA when available (passed to train_policy_value.py).",
    )
    args = parser.parse_args()

    model_dir: Path = args.model_dir
    data_dir = model_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = model_dir / "runs.jsonl"
    run_index = (
        sum(1 for _ in open(log_path, encoding="utf-8"))
        if log_path.exists()
        else 0
    )
    current = model_dir / "current.pt"
    candidate = model_dir / "candidate.pt"
    data_file = data_dir / f"run_{run_index:04d}.jsonl.gz"

    selfplay_args = [
        str(SCRIPTS / "generate_selfplay_data.py"),
        "--games",
        str(args.selfplay_games),
        "--mcts-capacity",
        str(args.mcts_capacity),
        "--output",
        str(data_file),
    ]
    if current.exists():
        selfplay_args += ["--model", str(current)]
    _run(selfplay_args)

    replay_files = select_replay_files(data_dir, window=args.replay_window)
    print(f"replay_window={args.replay_window}")
    for path in replay_files:
        print(f"replay_shard={path}")
    train_args = [
        str(SCRIPTS / "train_policy_value.py"),
        "--output",
        str(candidate),
        "--epochs",
        str(args.train_epochs),
        "--replay-max-records",
        str(args.replay_max_records),
    ]
    for path in replay_files:
        train_args += ["--data", str(path)]
    if args.cuda:
        train_args += ["--cuda"]
    train_output = _run(train_args)
    train_records = _parse_train_records(train_output)

    config_a = model_dir / f"candidate_config_{run_index:04d}.json"
    config_b = model_dir / f"current_config_{run_index:04d}.json"
    config_a.write_text(
        json.dumps({"model_path": str(candidate)}),
        encoding="utf-8",
    )
    baseline = {"model_path": str(current)} if current.exists() else {}
    config_b.write_text(
        json.dumps(baseline),
        encoding="utf-8",
    )
    report_path = model_dir / f"arena_report_{run_index:04d}.json"
    arena_mcts_capacity = (
        args.arena_mcts_capacity
        if args.arena_mcts_capacity is not None
        else args.mcts_capacity
    )
    arena_args = [
        str(SCRIPTS / "hard_ai_arena.py"),
        "--engine-a",
        "hard",
        "--engine-b",
        "hard",
        "--config-a",
        str(config_a),
        "--config-b",
        str(config_b),
        "--mcts-capacity",
        str(arena_mcts_capacity),
        "--opening-mode",
        args.arena_opening_mode,
        "--output",
        str(report_path),
    ]
    if args.arena_opening_mode == "generated":
        arena_args += [
            "--opening-seed",
            str(args.arena_opening_seed),
            "--opening-count",
            str(args.arena_opening_count),
            "--opening-length",
            str(args.arena_opening_length),
        ]
    else:
        arena_args += ["--openings", "default"]
    _run(arena_args)

    report = _load_report(report_path)
    candidate_score = report["score_rate"]["A"]
    lower_bound = report["score_confidence_95"]["A"][0]
    kept = should_promote(report)
    if kept:
        shutil.copy2(candidate, current)
        print(
            f"kept: candidate score={candidate_score:.3f} "
            f"95% CI lower={lower_bound:.3f} > 0.5",
            flush=True,
        )
    else:
        print(
            f"discarded: candidate score={candidate_score:.3f} "
            f"95% CI lower={lower_bound:.3f} <= 0.5",
            flush=True,
        )

    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "run": run_index,
                    "kept": kept,
                    "score_rate": candidate_score,
                    "confidence_95": report["score_confidence_95"]["A"],
                    "games": report["games"],
                    "wins": report["wins"],
                    "draws": report["draws"],
                    "data_file": str(data_file),
                    "replay_files": [str(path) for path in replay_files],
                    "replay_window": args.replay_window,
                    "replay_max_records": args.replay_max_records,
                    "train_records": train_records,
                    "opening_mode": report["opening_mode"],
                    "opening_seed": report["opening_seed"],
                    "opening_count": report["opening_count"],
                    "opening_length_min": report["opening_length_min"],
                    "opening_length_max": report["opening_length_max"],
                    "candidate": str(candidate),
                }
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
