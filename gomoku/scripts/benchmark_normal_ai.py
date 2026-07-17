"""Run repeatable NormalAI diagnostics without asserting machine timings."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.normal_ai import NormalAI  # noqa: E402
from gomoku.core.board import Board  # noqa: E402
from gomoku.core.enums import Player  # noqa: E402


POSITIONS = {
    "opening": [(7, 7, Player.BLACK)],
    "balanced_midgame": [
        (7, 7, Player.BLACK),
        (7, 8, Player.WHITE),
        (8, 8, Player.BLACK),
        (6, 6, Player.WHITE),
        (8, 7, Player.BLACK),
        (6, 8, Player.WHITE),
    ],
    "tactical": [
        (7, 5, Player.BLACK),
        (7, 6, Player.BLACK),
        (7, 8, Player.BLACK),
        (6, 7, Player.WHITE),
        (8, 7, Player.WHITE),
    ],
}


def main() -> None:
    print(
        "position move depth nodes qnodes tt_hits eval_hits cutoffs "
        "vcf elapsed_ms"
    )
    for name, stones in POSITIONS.items():
        board = Board()
        for row, col, player in stones:
            board.place(row, col, player)
        ai = NormalAI(Player.WHITE)
        move = ai.choose_move(board)
        stats = ai.last_search_stats
        print(
            name,
            move,
            stats.completed_depth,
            stats.nodes,
            stats.quiescence_nodes,
            stats.tt_hits,
            stats.eval_cache_hits,
            stats.beta_cutoffs,
            stats.vcf_found,
            round(stats.elapsed_ms, 1),
        )


if __name__ == "__main__":
    main()
