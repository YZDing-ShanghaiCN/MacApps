"""Trained-model policy/value provider for the HardAI MCTS fallback.

Implements the :class:`PolicyValueProvider` protocol with a network saved
by :func:`gomoku.ai.model.save_model`. torch is imported lazily and the
network is loaded on first use, so merely constructing this provider (or
importing the module) costs nothing when no model is configured. The
heuristic provider remains the default; this class is only used when a
``model_path`` is configured or injected explicitly.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from gomoku.ai.hard_ai_config import HardAIConfig
from gomoku.ai.model import encode_grid, load_model
from gomoku.ai.search_position import SearchPosition
from gomoku.core.enums import Player

Move = tuple[int, int]


class ModelPolicyValueProvider:
    """Deterministic policy/value from a trained GomokuNet."""

    def __init__(self, config: HardAIConfig, model_path: str) -> None:
        self.config = config
        self.model_path = model_path
        self._net = None
        self._arch = None
        self._cache_key = None
        self._cache_logits = None

    def _ensure_net(self):
        if self._net is None:
            try:
                import torch  # noqa: F401
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "model_path is configured but PyTorch is not installed. "
                    "Install it with: python3 -m pip install --user torch "
                    "--index-url https://download.pytorch.org/whl/cpu"
                ) from exc
            self._net = load_model(self.model_path)
            self._arch = {
                "size": self._net.size,
                "blocks": self._net.blocks,
                "channels": self._net.channels,
            }
        return self._net

    def arch_info(self) -> dict | None:
        """Architecture metadata of the loaded network, or None before load."""

        return self._arch

    def _logits(self, position, player, timeout_check):
        """One forward pass per (position, player), shared by policy() and
        global_top_k() via a one-slot cache. The deadline check runs on
        every call, even on a cache hit."""

        if timeout_check is not None:
            timeout_check()
        key = (position.hash_key, int(player))
        if self._cache_key == key:
            return self._cache_logits
        import torch

        net = self._ensure_net()
        if position.size != net.size:
            raise ValueError(
                f"Model expects board size {net.size}, "
                f"got {position.size}."
            )
        planes = encode_grid(position.grid, player)
        with torch.no_grad():
            logits, _ = net(
                torch.as_tensor(planes).unsqueeze(0)
            )
        logits = logits.squeeze(0).numpy().astype(np.float64)
        self._cache_key = key
        self._cache_logits = logits
        return logits

    @staticmethod
    def _center_distance(position, move: Move) -> float:
        center = (position.size - 1) / 2
        return max(abs(move[0] - center), abs(move[1] - center))

    def policy(
        self,
        position: SearchPosition,
        player: Player | int,
        legal_moves: list[Move],
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> dict[Move, float]:
        """Softmax over legal moves from the network's policy head."""

        logits = self._logits(position, player, timeout_check)
        size = position.size
        masked = np.full(size * size, -np.inf)
        for move in legal_moves:
            masked[move[0] * size + move[1]] = 0.0
        scores = logits + masked
        maximum = float(scores.max())
        weights = np.exp(scores - maximum)
        total = float(weights.sum())
        if total <= 0.0:
            share = 1.0 / len(legal_moves)
            return {move: share for move in legal_moves}
        return {
            move: float(weights[move[0] * size + move[1]] / total)
            for move in legal_moves
        }

    def global_top_k(
        self,
        position: SearchPosition,
        player: Player | int,
        k: int,
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> tuple[Move, ...]:
        """The k highest-prior legal moves over the whole board.

        Ties are broken by (center distance, row, col), so the result is
        deterministic. Shares the forward pass with policy() for the same
        (position, player) via the logits cache.
        """

        if k <= 0:
            return ()
        logits = self._logits(position, player, timeout_check)
        size = position.size
        indices = [
            index
            for index in range(size * size)
            if position.is_empty(index // size, index % size)
        ]
        if not indices:
            return ()
        indices.sort(
            key=lambda index: (
                -logits[index],
                self._center_distance(
                    position, (index // size, index % size)
                ),
                index // size,
                index % size,
            )
        )
        return tuple(
            (index // size, index % size)
            for index in indices[: min(k, len(indices))]
        )

    def value(
        self,
        position: SearchPosition,
        player: Player | int,
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> float:
        """Win probability in (0, 1) from ``player``'s perspective."""

        if timeout_check is not None:
            timeout_check()
        if position.empty_count == 0 or (
            position.empty_count == position.size * position.size
        ):
            return 0.5
        import torch

        net = self._ensure_net()
        planes = encode_grid(position.grid, player)
        with torch.no_grad():
            _, value = net(
                torch.as_tensor(planes).unsqueeze(0)
            )
        return (float(value.item()) + 1.0) / 2.0
