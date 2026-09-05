"""Train the small policy-value network on self-play records.

Loss = cross-entropy(policy logits, MCTS visit distribution)
     + MSE(tanh value, game outcome +/-1/0),
with all 8 dihedral symmetries applied on the fly. Requires PyTorch
(``gomoku/requirements-ml.txt``); checkpoints are written atomically.
"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

try:
    import numpy as np
    import torch
    from torch import nn
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


def load_records(patterns: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (planes (N,2,S,S), policies (N,S*S), outcomes (N,1))."""

    plane_list: list[np.ndarray] = []
    policy_list: list[np.ndarray] = []
    outcome_list: list[float] = []
    for pattern in patterns:
        paths = sorted(glob.glob(pattern))
        if not paths:
            raise SystemExit(f"no files match {pattern!r}")
        for path in paths:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    plane_list.append(
                        np.asarray(record["planes"], dtype=np.float32)
                    )
                    policy_list.append(
                        np.asarray(record["policy"], dtype=np.float32)
                    )
                    outcome_list.append(float(record["outcome"]))
    planes = np.stack(plane_list)
    policies = np.stack(policy_list)
    outcomes = np.asarray(outcome_list, dtype=np.float32)[:, None]
    return planes, policies, outcomes


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


def evaluate(
    net,
    planes: torch.Tensor,
    policies: torch.Tensor,
    outcomes: torch.Tensor,
    *,
    batch_size: int,
    ce_loss,
    mse_loss,
) -> tuple[float, float]:
    total_loss = 0.0
    correct = 0
    count = 0
    with torch.no_grad():
        for start in range(0, len(planes), batch_size):
            plane_batch = planes[start : start + batch_size]
            policy_batch = policies[start : start + batch_size]
            outcome_batch = outcomes[start : start + batch_size]
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
    return total_loss / max(1, count), correct / max(1, count)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the HardAI policy-value network."
    )
    parser.add_argument(
        "--data",
        action="append",
        required=True,
        help="Glob pattern for gzip-JSONL self-play files (repeatable).",
    )
    parser.add_argument("--output", type=Path, default="model.pt")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--blocks", type=int, default=4)
    parser.add_argument("--channels", type=int, default=64)
    parser.add_argument("--val-fraction", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cuda", action="store_true")
    args = parser.parse_args()

    planes, policies, outcomes = load_records(args.data)
    print(f"records={len(planes)}")

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(planes))
    val_count = max(1, int(len(planes) * args.val_fraction))
    train_order = order[val_count:]
    val_order = order[:val_count]
    print(f"train={len(train_order)} val={len(val_order)}")

    size = planes.shape[-1]
    net = GomokuNet(size=size, blocks=args.blocks, channels=args.channels)
    device = "cuda" if args.cuda and torch.cuda.is_available() else "cpu"
    net.to(device)
    perms = tuple(
        torch.as_tensor(perm, device=device)
        for perm in symmetry_transforms(size)
    )

    train_planes = torch.as_tensor(planes[train_order], device=device)
    train_policies = torch.as_tensor(policies[train_order], device=device)
    train_outcomes = torch.as_tensor(outcomes[train_order], device=device)
    val_planes = torch.as_tensor(planes[val_order], device=device)
    val_policies = torch.as_tensor(policies[val_order], device=device)
    val_outcomes = torch.as_tensor(outcomes[val_order], device=device)

    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr)
    ce_loss = nn.CrossEntropyLoss()
    mse_loss = nn.MSELoss()

    for epoch in range(1, args.epochs + 1):
        net.train()
        epoch_order = rng.permutation(len(train_planes))
        total_loss = 0.0
        correct = 0
        for start in range(0, len(epoch_order), args.batch_size):
            indices = epoch_order[start : start + args.batch_size]
            plane_batch = train_planes[indices]
            policy_batch = train_policies[indices]
            outcome_batch = train_outcomes[indices]
            plane_batch, policy_batch = augment_batch(
                plane_batch, policy_batch, perms, rng
            )
            optimizer.zero_grad()
            logits, value = net(plane_batch)
            loss = ce_loss(logits, policy_batch) + mse_loss(
                value, outcome_batch
            )
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(indices)
            correct += int(
                (logits.detach().argmax(dim=1) == policy_batch.argmax(dim=1))
                .sum()
                .item()
            )
        count = len(train_planes)
        train_loss = total_loss / max(1, count)
        train_acc = correct / max(1, count)
        net.eval()
        val_loss, val_acc = evaluate(
            net,
            val_planes,
            val_policies,
            val_outcomes,
            batch_size=args.batch_size,
            ce_loss=ce_loss,
            mse_loss=mse_loss,
        )
        print(
            f"epoch={epoch} train_loss={train_loss:.4f} "
            f"train_acc={train_acc:.3f} val_loss={val_loss:.4f} "
            f"val_acc={val_acc:.3f}",
            flush=True,
        )
        save_model(net, f"{args.output}.epoch{epoch}")

    save_model(net, args.output)
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
