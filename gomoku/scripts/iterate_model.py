"""One iteration of the self-play training loop.

Cycle: (1) generate self-play games (with the current model's priors once
one exists), (2) train a candidate network, (3) arena the candidate-model
HardAI against the current-model HardAI (or the heuristic provider on the
first run), (4) keep the candidate as ``current.pt`` only if its 95% Wilson
score interval is entirely above 0.5. Each run appends one JSON line to
``runs.jsonl`` under the model directory.
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


def _run(arguments: list[str]) -> None:
    print(f"+ {' '.join(arguments)}", flush=True)
    subprocess.run([sys.executable, *arguments], check=True)


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
        "--openings",
        default="default",
        choices=("default", "empty"),
        help="Arena openings: default plays 10 games, empty plays 2.",
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

    _run(
        [
            str(SCRIPTS / "train_policy_value.py"),
            "--data",
            str(data_file),
            "--output",
            str(candidate),
            "--epochs",
            str(args.train_epochs),
        ]
    )

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
    _run(
        [
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
            str(args.mcts_capacity),
            "--openings",
            args.openings,
            "--output",
            str(report_path),
        ]
    )

    report = _load_report(report_path)
    candidate_score = report["score_rate"]["A"]
    lower_bound = report["score_confidence_95"]["A"][0]
    kept = lower_bound > 0.5
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
                    "candidate": str(candidate),
                }
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
