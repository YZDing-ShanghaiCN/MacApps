"""Deterministic PUCT Monte-Carlo tree search for the HardAI fallback.

Design notes
------------
* **No rollouts**: every simulation selects through the tree, expands one
  leaf child and evaluates it with the injected :class:`PolicyValueProvider`;
  a move that wins immediately scores 1.0 and a full board 0.5.
* **PUCT** (documented choice): a child ``c`` of node ``n`` is scored from
  ``n.player``'s perspective as
  ``(1 - Q_c) + c_puct * P_c * sqrt(N_n) / (1 + N_c)``
  with values in ``[0, 1]``. Ties are broken by ``(center distance, row,
  col)`` with strict ``>`` comparisons, so equal trees reproduce identical
  searches; ``random.Random(config.mcts_seed)`` is kept for future use.
* **Priors**: the policy provider scores the tactical pool (empty cells
  within ``candidate_radius`` of a stone, the center neighborhood on an
  empty board, plus ``priority_moves``). Pool moves get
  ``(1 - eps) * policy + eps / N_all``, i.e. the uniform epsilon mass is
  spread over *all* legal moves so far-away moves are never fully
  unreachable in prior space; only pool moves become children.
* **Always legal**: the returned move is the most-visited child (ties by
  center distance), else the highest-prior pool move, else the
  center-nearest empty cell — even with zero simulations after a cancel.
  An empty board is answered by convention with the center cell, without
  searching.
* **Root reuse**: when enabled, a fresh root wraps the previous search's
  subtree (kept statistics) iff the previous search did not time out and
  the Zobrist hash (side to move included) matches. Reuse only warms up
  statistics; legality is re-verified on the current board every time.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from gomoku.ai.hard_ai_config import HardAIConfig
from gomoku.ai.policy_value import PolicyValueProvider
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win

Move = tuple[int, int]


class MCTSTimeout(RuntimeError):
    """Internal cooperative deadline signal; never escapes MCTS."""


@dataclass(frozen=True)
class MCTSRootMove:
    move: Move
    visits: int
    value: float


@dataclass(frozen=True)
class MCTSResult:
    move: Move | None
    simulations: int
    root_visits: int
    elapsed_ms: float
    timed_out: bool
    value: float
    root_moves: tuple[MCTSRootMove, ...] = ()


class _Node:
    __slots__ = (
        "move",
        "parent",
        "children",
        "priors",
        "untried",
        "visits",
        "value_sum",
        "terminal",
        "terminal_value",
        "player",
    )

    def __init__(
        self,
        *,
        move: Move | None,
        player: Player,
        parent: "_Node | None" = None,
    ) -> None:
        self.move = move
        self.parent = parent
        self.player = player
        self.children: dict[Move, _Node] = {}
        self.priors: dict[Move, float] = {}
        self.untried: list[Move] = []
        self.visits = 0
        self.value_sum = 0.0
        self.terminal = False
        self.terminal_value = 0.5


class MCTS:
    """PUCT search with injectable clock; deterministic for equal trees."""

    def __init__(
        self,
        config: HardAIConfig,
        provider: PolicyValueProvider,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.provider = provider
        self.clock = clock
        self._rng = random.Random(config.mcts_seed)
        self._reuse_hash: int | None = None
        self._reuse_subtree: _Node | None = None
        self._reuse_timed_out = False

    # ------------------------------------------------------------------ API

    def search(
        self,
        board: Board,
        player: Player | int,
        *,
        time_budget_ms: float,
        cancel_event: threading.Event | None = None,
        priority_moves: tuple[Move, ...] = (),
    ) -> MCTSResult:
        mover = Player(player)
        started = self.clock()
        budget = max(1.0, time_budget_ms)
        deadline = started + budget / 1000.0
        zobrist = ZobristTable(board.size, self.config.zobrist_seed)
        position = SearchPosition.from_board(
            board,
            mover,
            zobrist,
            max_candidate_radius=self.config.candidate_radius,
        )
        simulations = 0
        timed_out = False
        if position.empty_count == position.size * position.size:
            center = position.size // 2
            return MCTSResult(
                move=(center, center),
                simulations=0,
                root_visits=0,
                elapsed_ms=max(
                    0.0, (self.clock() - started) * 1000.0
                ),
                timed_out=False,
                value=0.5,
            )
        root = self._make_root(position)
        if not root.untried and not root.children:
            return MCTSResult(
                move=self._final_move(position, root),
                simulations=0,
                root_visits=0,
                elapsed_ms=max(
                    0.0, (self.clock() - started) * 1000.0
                ),
                timed_out=False,
                value=0.5,
            )
        immediate = self._immediate_win(position, mover, priority_moves)
        if immediate is not None:
            return MCTSResult(
                move=immediate,
                simulations=0,
                root_visits=0,
                elapsed_ms=max(
                    0.0, (self.clock() - started) * 1000.0
                ),
                timed_out=False,
                value=1.0,
                root_moves=(MCTSRootMove(immediate, 0, 1.0),),
            )
        try:
            while True:
                self._check_timeout(deadline, cancel_event, simulations)
                simulations += 1
                node = root
                while not node.untried and node.children:
                    child = self._best_child(node)
                    position.make_move(*child.move)
                    node = child
                if node.terminal or (not node.untried and not node.children):
                    value = node.terminal_value
                else:
                    move = node.untried.pop(0)
                    position.make_move(*move)
                    child = _Node(
                        move=move, player=node.player.opponent, parent=node
                    )
                    node.children[move] = child
                    last = position.last_move
                    if (
                        last is not None
                        and check_win(
                            position, last.row, last.col, node.player
                        )
                    ):
                        value = 0.0
                        child.terminal = True
                        child.terminal_value = 0.0
                    elif position.empty_count == 0:
                        value = 0.5
                        child.terminal = True
                        child.terminal_value = 0.5
                    else:
                        child.priors, child.untried = self._expand(
                            position, child.player, priority_moves
                        )
                        value = self.provider.value(
                            position,
                            child.player,
                            timeout_check=None,
                        )
                    node = child
                while node is not root:
                    node.visits += 1
                    node.value_sum += value
                    value = 1.0 - value
                    node = node.parent
                    position.undo_move()
                root.visits += 1
                root.value_sum += value
        except MCTSTimeout:
            timed_out = True
        move = self._final_move(position, root)
        elapsed = (self.clock() - started) * 1000.0
        self._remember_reuse(position.hash_key, root, timed_out)
        return MCTSResult(
            move=move,
            simulations=simulations,
            root_visits=root.visits,
            elapsed_ms=max(0.0, elapsed),
            timed_out=timed_out,
            value=self._root_value(root),
            root_moves=self._root_moves(root),
        )

    # ------------------------------------------------------------- plumbing

    def _make_root(self, position: SearchPosition) -> _Node:
        root = _Node(move=None, player=position.current_player)
        if (
            self.config.mcts_reuse_root
            and not self._reuse_timed_out
            and self._reuse_hash == position.hash_key
            and self._reuse_subtree is not None
            and self._reuse_subtree.player == position.current_player
        ):
            old = self._reuse_subtree
            root.children = {
                move: child
                for move, child in old.children.items()
                if position.is_empty(*move)
            }
            root.priors = {
                move: prior
                for move, prior in old.priors.items()
                if position.is_empty(*move)
            }
            root.untried = []
        else:
            root.priors, root.untried = self._expand(
                position, root.player, ()
            )
        return root

    def _expand(
        self,
        position: SearchPosition,
        player: Player,
        priority_moves: tuple[Move, ...],
    ) -> tuple[dict[Move, float], list[Move]]:
        pool = sorted(
            self._policy_pool(position) | {
                move
                for move in priority_moves
                if position.is_empty(*move)
            }
        )
        priors: dict[Move, float] = {}
        if not pool:
            return priors, []
        policy = self.provider.policy(
            position, player, pool, timeout_check=None
        )
        epsilon = self.config.mcts_uniform_prior_epsilon
        uniform = epsilon / max(1, position.empty_count)
        for move in pool:
            priors[move] = (1.0 - epsilon) * policy.get(move, 0.0) + uniform
        if priority_moves:
            bonus = self.config.mcts_priority_prior_bonus
            for move in priority_moves:
                if move in priors:
                    priors[move] *= bonus
            total = sum(priors.values())
            if total > 0.0:
                priors = {move: p / total for move, p in priors.items()}
        untried = sorted(
            pool,
            key=lambda move: (
                -priors.get(move, 0.0),
                self._center_distance(position, move),
                move[0],
                move[1],
            ),
        )
        return priors, untried

    def _policy_pool(self, position: SearchPosition) -> set[Move]:
        radius = self.config.candidate_radius
        if not position.occupied:
            center = position.size // 2
            return {
                (row, col)
                for row in range(
                    max(0, center - radius),
                    min(position.size, center + radius + 1),
                )
                for col in range(
                    max(0, center - radius),
                    min(position.size, center + radius + 1),
                )
                if position.is_empty(row, col)
            }
        return set(position.nearby_empty_moves(radius))

    def _immediate_win(
        self,
        position: SearchPosition,
        mover: Player,
        priority_moves: tuple[Move, ...],
    ) -> Move | None:
        candidates = sorted(
            self._policy_pool(position)
            | {
                move
                for move in priority_moves
                if position.is_empty(*move)
            }
        )
        wins = [
            move
            for move in candidates
            if position.move_wins(*move, mover)
        ]
        if not wins:
            return None
        return min(
            wins,
            key=lambda move: (
                self._center_distance(position, move),
                move[0],
                move[1],
            ),
        )

    def _best_child(self, node: _Node) -> _Node:
        parent_visits = max(1, node.visits)
        exploration = self.config.mcts_exploration_constant
        best: _Node | None = None
        best_score = float("-inf")
        for move in sorted(node.children):
            child = node.children[move]
            if child.visits > 0:
                child_q = child.value_sum / child.visits
            else:
                child_q = 0.5
            prior = node.priors.get(move, 0.0)
            score = (
                1.0 - child_q
                + exploration
                * prior
                * (parent_visits ** 0.5)
                / (1.0 + child.visits)
            )
            if score > best_score:
                best_score = score
                best = child
        if best is None:
            raise RuntimeError("Selection reached a childless open node.")
        return best

    def _check_timeout(
        self,
        deadline: float,
        cancel_event: threading.Event | None,
        simulations: int,
    ) -> None:
        if simulations % self.config.timeout_check_interval_nodes != 0:
            return
        if (cancel_event is not None and cancel_event.is_set()) or (
            self.clock() >= deadline
        ):
            raise MCTSTimeout

    def _final_move(
        self, position: SearchPosition, root: _Node
    ) -> Move | None:
        if root.children:
            best_move = max(
                sorted(root.children),
                key=lambda move: (
                    root.children[move].visits,
                    -self._center_distance(position, move),
                    -move[0],
                    -move[1],
                ),
            )
            return best_move
        if root.priors:
            return max(
                sorted(root.priors),
                key=lambda move: (
                    root.priors[move],
                    -self._center_distance(position, move),
                    -move[0],
                    -move[1],
                ),
            )
        return self._center_nearest(position)

    def _center_nearest(self, position: SearchPosition) -> Move | None:
        center = position.size // 2
        empty = [
            (row, col)
            for row in range(position.size)
            for col in range(position.size)
            if position.is_empty(row, col)
        ]
        if not empty:
            return None
        return min(
            empty,
            key=lambda move: (
                max(abs(move[0] - center), abs(move[1] - center)),
                move[0],
                move[1],
            ),
        )

    def _center_distance(self, position: SearchPosition, move: Move) -> float:
        center = (position.size - 1) / 2
        return max(abs(move[0] - center), abs(move[1] - center))

    def _root_value(self, root: _Node) -> float:
        if root.visits == 0:
            return 0.5
        return root.value_sum / root.visits

    def _root_moves(self, root: _Node) -> tuple[MCTSRootMove, ...]:
        moves = []
        for move in sorted(root.children):
            child = root.children[move]
            value = child.value_sum / child.visits if child.visits else 0.5
            moves.append(MCTSRootMove(move, child.visits, value))
        moves.sort(key=lambda item: (-item.visits, item.move))
        return tuple(moves)

    def _remember_reuse(
        self, hash_key: int, root: _Node, timed_out: bool
    ) -> None:
        self._reuse_hash = hash_key
        self._reuse_subtree = root
        self._reuse_timed_out = timed_out

    def clear_reuse(self) -> None:
        self._reuse_hash = None
        self._reuse_subtree = None
        self._reuse_timed_out = False
