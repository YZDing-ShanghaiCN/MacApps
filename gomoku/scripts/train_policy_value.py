"""Train the small policy-value network on self-play records (streaming).

Loss = cross-entropy(policy logits, MCTS visit distribution)
     + MSE(tanh value, game outcome +/-1/0),
with all 8 dihedral symmetries applied on the fly. Records are streamed
from gzip JSONL shards through a deterministic bounded reservoir (see
:mod:`gomoku.ai.replay`), so memory use is capped by ``--replay-max-records``
instead of the total history size. Requires PyTorch
(``gomoku/requirements-ml.txt``); checkpoints are written atomically.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

try:
    import numpy as np
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, IterableDataset
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    print(
        "PyTorch is required for training. Install it with:\n"
        "  python3 -m pip install --user torch --index-url "
        "https://download.pytorch.org/whl/cpu\n"
        f"({exc})",
        file=sys.stderr,
    )
    raise SystemExit(1)

from gomoku.ai.model import GomokuNet, save_model, symmetry_transforms  # noqa: E402
from gomoku.ai.replay import (  # noqa: E402
    is_val_record,
    reservoir_sample,
    select_replay_files,
)


def resolve_data_files(patterns: list[str], *, window: int) -> list[Path]:
    """Expand ``--data`` entries (file, glob or directory) in sorted order.

    A directory entry is treated as a shard directory and reduced to its
    newest ``window`` ``run_*.jsonl.gz`` files via the replay selector.
    """

    files: list[Path] = []
    for pattern in patterns:
        if Path(pattern).is_dir():
            selected = select_replay_files(pattern, window=window)
            if not selected:
                raise SystemExit(f"no replay files in directory {pattern!r}")
            files.extend(selected)
        else:
            matched = sorted(Path(path) for path in glob.glob(pattern))
            if not matched:
                raise SystemExit(f"no files match {pattern!r}")
            files.extend(matched)
    deduped: list[Path] = []
    for path in files:
        if path not in deduped:
            deduped.append(path)
    return deduped


class ReplayDataset(IterableDataset):
    """Streaming dataset over replay shards with a seeded per-epoch sample.

    ``num_workers=0`` is required: the reservoir and the epoch seed make the
    iteration order fully deterministic for a fixed ``sample_seed``.
    """

    def __init__(
        self,
        files: list[Path],
        *,
        sample_seed: int,
        max_records: int | None,
        val_fraction: float,
        want_val: bool,
    ) -> None:
        super().__init__()
        self.files = files
        self.sample_seed = sample_seed
        self.max_records = max_records
        self.val_fraction = val_fraction
        self.want_val = want_val

    def __iter__(self):
        import random

        rng = random.Random(self.sample_seed)
        for path, line_index, record in reservoir_sample(
            self.files, rng, self.max_records
        ):
            if is_val_record(path, line_index, self.val_fraction) != (
                self.want_val
            ):
                continue
            planes = torch.from_numpy(
                np.asarray(record["planes"], dtype=np.float32)
            )
            policy = torch.from_numpy(
                np.asarray(record["policy"], dtype=np.float32)
            )
            outcome = torch.as_tensor(
                [float(record["outcome"])], dtype=torch.float32
            )
            yield planes, policy, outcome


def augment_batch(
    planes: torch.Tensor,
    policies: torch.Tensor,
    perms: tuple[torch.Tensor, ...],
    rng: np.random.Generator,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Apply a random dihedral transform to every sample in the batch."""

    batch = planes.shape[0]
    size = planes.shape[-1]
    choices = rng.integers(0, len(perms), size=batch)
    transformed_planes = []
    transformed_policies = []
    for index, perm_index in enumerate(choices):
        perm = perms[int(perm_index)]
        transformed_planes.append(
            planes[index].reshape(2, -1)[:, perm].reshape(2, size, size)
        )
        transformed_policies.append(policies[index][perm])
    return (
        torch.stack(transformed_planes),
        torch.stack(transformed_policies),
    )


def _evaluate_loader(
    net,
    loader,
    *,
    ce_loss,
    mse_loss,
) -> tuple[float, float, int]:
    total_loss = 0.0
    correct = 0
    count = 0
    with torch.no_grad():
        for plane_batch, policy_batch, outcome_batch in loader:
            logits, value = net(plane_batch)
            loss = ce_loss(logits, policy_batch) + mse_loss(
                value, outcome_batch
            )
            total_loss += float(loss.item()) * len(plane_batch)
            correct += int(
                (logits.argmax(dim=1) == policy_batch.argmax(dim=1))
                .sum()
                .item()
            )
            count += len(plane_batch)
    return total_loss / max(1, count), correct / max(1, count), count


def _board_size(files: list[Path]) -> int:
    import gzip
    import json

    with gzip.open(files[0], "rt", encoding="utf-8") as handle:
        first = json.loads(handle.readline())
    return len(np.asarray(first["planes"])[0])


def train(
    *,
    data: list[str],
    output: str | Path,
    epochs: int = 3,
    batch_size: int = 256,
    lr: float = 1e-3,
    blocks: int = 4,
    channels: int = 64,
    val_fraction: float = 0.05,
    seed: int = 0,
    replay_seed: int | None = None,
    replay_window: int = 8,
    replay_max_records: int | None = 200_000,
    cuda: bool = False,
    print_fn=print,
) -> dict:
    """Train ``GomokuNet`` on the streaming replay sample; returns a summary."""

    files = resolve_data_files(data, window=replay_window)
    sample_seed = seed if replay_seed is None else replay_seed
    print_fn(f"replay_files={len(files)}")
    for path in files:
        print_fn(f"replay_shard={path}")

    size = _board_size(files)
    net = GomokuNet(size=size, blocks=blocks, channels=channels)
    device = "cuda" if cuda and torch.cuda.is_available() else "cpu"
    net.to(device)
    perms = tuple(
        torch.as_tensor(perm, device=device)
        for perm in symmetry_transforms(size)
    )

    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    ce_loss = nn.CrossEntropyLoss()
    mse_loss = nn.MSELoss()
    aug_rng = np.random.default_rng(seed)
    epoch_summaries: list[dict] = []

    for epoch in range(1, epochs + 1):
        train_loader = DataLoader(
            ReplayDataset(
                files,
                sample_seed=sample_seed + epoch,
                max_records=replay_max_records,
                val_fraction=val_fraction,
                want_val=False,
            ),
            batch_size=batch_size,
            num_workers=0,
        )
        val_loader = DataLoader(
            ReplayDataset(
                files,
                sample_seed=sample_seed + epoch,
                max_records=replay_max_records,
                val_fraction=val_fraction,
                want_val=True,
            ),
            batch_size=batch_size,
            num_workers=0,
        )

        net.train()
        total_loss = 0.0
        correct = 0
        train_count = 0
        for plane_batch, policy_batch, outcome_batch in train_loader:
            plane_batch = plane_batch.to(device)
            policy_batch = policy_batch.to(device)
            outcome_batch = outcome_batch.to(device)
            plane_batch, policy_batch = augment_batch(
                plane_batch, policy_batch, perms, aug_rng
            )
            optimizer.zero_grad()
            logits, value = net(plane_batch)
            loss = ce_loss(logits, policy_batch) + mse_loss(
                value, outcome_batch
            )
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(plane_batch)
            correct += int(
                (logits.detach().argmax(dim=1) == policy_batch.argmax(dim=1))
                .sum()
                .item()
            )
            train_count += len(plane_batch)
        train_loss = total_loss / max(1, train_count)
        train_acc = correct / max(1, train_count)
        net.eval()
        val_loss, val_acc, val_count = _evaluate_loader(
            net, val_loader, ce_loss=ce_loss, mse_loss=mse_loss
        )
        summary = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_acc": train_acc,
            "train_records": train_count,
            "val_loss": val_loss if val_count else None,
            "val_acc": val_acc if val_count else None,
            "val_records": val_count,
        }
        epoch_summaries.append(summary)
        if val_count:
            print_fn(
                f"epoch={epoch} train_loss={train_loss:.4f} "
                f"train_acc={train_acc:.3f} val_loss={val_loss:.4f} "
                f"val_acc={val_acc:.3f} "
                f"train_records={train_count} val_records={val_count}",
                flush=True,
            )
        else:
            print_fn(
                f"epoch={epoch} train_loss={train_loss:.4f} "
                f"train_acc={train_acc:.3f} "
                f"train_records={train_count} val_records=0",
                flush=True,
            )
        save_model(net, f"{output}.epoch{epoch}")

    save_model(net, output)
    print_fn(f"saved={output}")
    return {
        "output": str(output),
        "files": [str(path) for path in files],
        "size": size,
        "epochs": epoch_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the HardAI policy-value network."
    )
    parser.add_argument(
        "--data",
        action="append",
        required=True,
        help=(
            "Gzip-JSONL self-play file, glob, or shard directory "
            "(repeatable; directories are limited by --replay-window)."
        ),
    )
    parser.add_argument("--output", type=Path, default="model.pt")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--channels", type=int, default=64)
    parser.add_argument("--val-fraction", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--replay-window",
        type=int,
        default=8,
        help="Keep only the newest N shards of each --data directory.",
    )
    parser.add_argument(
        "--replay-max-records",
        type=int,
        default=200_000,
        help="Upper bound of the sampled training records (0 = unlimited).",
    )
    parser.add_argument(
        "--replay-seed",
        type=int,
        default=None,
        help="Reservoir sampling seed (default: --seed).",
    )
    parser.add_argument("--cuda", action="store_true")
    args = parser.parse_args()

    train(
        data=args.data,
        output=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        blocks=args.blocks,
        channels=args.channels,
        val_fraction=args.val_fraction,
        seed=args.seed,
        replay_seed=args.replay_seed,
        replay_window=args.replay_window,
        replay_max_records=args.replay_max_records,
        cuda=args.cuda,
    )


if __name__ == "__main__":
    main()
