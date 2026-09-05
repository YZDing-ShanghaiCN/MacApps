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
        return self._net

    def policy(
        self,
        position: SearchPosition,
        player: Player | int,
        legal_moves: list[Move],
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> dict[Move, float]:
        """Softmax over legal moves from the network's policy head."""

        if timeout_check is not None:
            timeout_check()
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
