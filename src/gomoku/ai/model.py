"""Policy-value network, board encoding and symmetries for HardAI training.

Only numpy is imported eagerly; torch is imported lazily inside functions so
the rest of the package (and the shipped game) stays ML-dependency-free.
Training data format: two player-perspective planes (mover, opponent) per
position, a 225-entry policy vector indexed ``row * size + col``, and an
outcome of +1 win / -1 loss / 0 draw from the mover's perspective.
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

import numpy as np

from gomoku.core.board import Board
from gomoku.core.enums import Player


def encode_grid(grid: list[list[int]], player: Player | int) -> np.ndarray:
    """Two player-perspective planes (mover, opponent), shape (2, size, size)."""

    mover = int(player)
    size = len(grid)
    planes = np.zeros((2, size, size), dtype=np.float32)
    for row in range(size):
        for col in range(size):
            cell = grid[row][col]
            if cell == int(Player.EMPTY):
                continue
            planes[0 if cell == mover else 1][row][col] = 1.0
    return planes


def encode_position(board: Board, player: Player | int) -> np.ndarray:
    """Convenience wrapper for objects exposing a ``grid`` attribute."""

    return encode_grid(board.grid, player)


@lru_cache(maxsize=None)
def symmetry_transforms(size: int) -> tuple[np.ndarray, ...]:
    """The 8 dihedral index permutations of a ``size`` x ``size`` grid.

    Each returned array ``perm`` satisfies ``transformed = original[perm]``
    for flat arrays indexed ``row * size + col`` (numpy fancy indexing), so
    one permutation serves planes (flattened) and policy vectors alike.
    """

    defs = (
        lambda r, c: (r, c),
        lambda r, c: (c, size - 1 - r),
        lambda r, c: (size - 1 - r, size - 1 - c),
        lambda r, c: (size - 1 - c, r),
        lambda r, c: (size - 1 - r, c),
        lambda r, c: (c, r),
        lambda r, c: (r, size - 1 - c),
        lambda r, c: (size - 1 - c, size - 1 - r),
    )
    perms = []
    for func in defs:
        perm = np.empty(size * size, dtype=np.int64)
        for new_row in range(size):
            for new_col in range(size):
                old_row, old_col = func(new_row, new_col)
                perm[new_row * size + new_col] = old_row * size + old_col
        perms.append(perm)
    return tuple(perms)


def _build_network_class():
    """Define the torch module class; called on demand via module __getattr__."""

    import torch
    from torch import nn

    class _ResidualBlock(nn.Module):
        def __init__(self, channels: int) -> None:
            super().__init__()
            self.body = nn.Sequential(
                nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(channels),
                nn.ReLU(inplace=True),
                nn.Conv2d(channels, channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(channels),
            )
            self.act = nn.ReLU(inplace=True)

        def forward(self, x):
            return self.act(x + self.body(x))

    class GomokuNet(nn.Module):
        """Small AlphaZero-style policy-value network.

        Input: ``(N, 2, size, size)`` player-perspective planes.
        Output: ``(policy_logits (N, size*size), value (N, 1) in [-1, 1])``.
        """

        def __init__(self, size: int = 15, blocks: int = 4, channels: int = 64):
            super().__init__()
            self.size = size
            self.blocks = blocks
            self.channels = channels
            self.conv_in = nn.Sequential(
                nn.Conv2d(2, channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(channels),
                nn.ReLU(inplace=True),
            )
            self.res_blocks = nn.ModuleList(
                _ResidualBlock(channels) for _ in range(blocks)
            )
            self.policy_conv = nn.Sequential(
                nn.Conv2d(channels, 2, 1, bias=False),
                nn.BatchNorm2d(2),
                nn.ReLU(inplace=True),
            )
            self.policy_fc = nn.Linear(2 * size * size, size * size)
            self.value_conv = nn.Sequential(
                nn.Conv2d(channels, 1, 1, bias=False),
                nn.BatchNorm2d(1),
                nn.ReLU(inplace=True),
            )
            self.value_fc = nn.Sequential(
                nn.Linear(size * size, 64),
                nn.ReLU(inplace=True),
                nn.Linear(64, 1),
                nn.Tanh(),
            )

        def forward(self, planes):
            x = self.conv_in(planes)
            for block in self.res_blocks:
                x = block(x)
            policy = self.policy_conv(x).flatten(1)
            policy = self.policy_fc(policy)
            value = self.value_conv(x).flatten(1)
            value = self.value_fc(value)
            return policy, value

    return GomokuNet


def __getattr__(name: str):
    if name == "GomokuNet":
        return _build_network_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def save_model(net, path: str | Path) -> None:
    """Atomically save network weights plus architecture metadata."""

    import torch

    payload = {
        "state_dict": net.state_dict(),
        "size": net.size,
        "blocks": net.blocks,
        "channels": net.channels,
    }
    destination = str(path)
    temporary = f"{destination}.tmp"
    torch.save(payload, temporary)
    os.replace(temporary, destination)


def load_model(path: str | Path):
    """Load a network saved by :func:`save_model`; returned in eval mode."""

    import torch

    payload = torch.load(
        str(path),
        map_location="cpu",
        weights_only=True,
    )
    net = _build_network_class()(
        size=payload["size"],
        blocks=payload["blocks"],
        channels=payload["channels"],
    )
    net.load_state_dict(payload["state_dict"])
    net.eval()
    return net
