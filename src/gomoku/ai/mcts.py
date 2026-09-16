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
* **Deadline authority**: the deadline and cancel event are checked before
  every simulation and inside the policy/value loops (the provider receives
  a ``timeout_check`` callback), so the budget is a real deadline, not an
  aspiration. The search also stops cleanly — not as a timeout — once
  ``mcts_node_capacity`` children have been created in this search.
* **Always legal**: the returned move is the most-visited child (ties by
  center distance), else the highest-prior pool move, else the
  center-nearest empty cell — even with zero simulations after a cancel.
  An empty board is answered by convention with the center cell, without
  searching.
* **Root reuse**: when enabled, a fresh root wraps the previous search's
  subtree (kept statistics) iff the previous search did not time out and
  the Zobrist hash (side to move included) matches (``reuse_plies=1``).
  Otherwise the stored subtree is advanced through the moves played since
  that search — the stored chosen move (one ply) and, when present, the
  opponent's reply (two plies) — validated by a board diff and Zobrist
  arithmetic (``reuse_plies=2``); any mismatch starts fresh. A clean
  completion via the node capacity is what makes reuse reachable. Reuse
  only warms up statistics; legality is re-verified on the current board
  every time and reused children are re-linked to the new root.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from gomoku.ai.hard_ai_config import HardAIConfig
from gomoku.ai.leaf_tactics import classify_leaf
from gomoku.ai.policy_value import PolicyValueProvider
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win

Move = tuple[int, int]


def apply_dirichlet_noise(
    priors: dict[Move, float],
    rng: random.Random,
    epsilon: float,
    alpha: float,
) -> dict[Move, float]:
    """Mix root priors with Dirichlet noise and renormalize.

    ``noisy = (1 - epsilon) * prior + epsilon * dirichlet(alpha)`` over the
    exact prior support, renormalized so the result sums to 1. All
    randomness comes from ``rng``, so equal seeds reproduce equal vectors.
    """

    moves = sorted(priors)
    if not moves or epsilon <= 0.0:
        return dict(priors)
    draws = [rng.gammavariate(alpha, 1.0) for _ in moves]
    total = sum(draws)
    noisy = {
        move: (1.0 - epsilon) * priors[move] + epsilon * draw / total
        for move, draw in zip(moves, draws)
    }
    mix_total = sum(noisy.values())
    if mix_total > 0.0:
        noisy = {move: value / mix_total for move, value in noisy.items()}
    return noisy


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
    root_noise_applied: bool = False
    reuse_plies: int = 0


class _Node:
    __slots__ = (
        "move",
        "parent",
        "children",
        "priors",
        "untried",
        "pending",
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
        self.pending: list[Move] = []
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
        self._reuse_root_move: Move | None = None
        self._reuse_grid: list[list[int]] | None = None
        self._node_count = 0
        self._last_root_noise_applied = False
        self._last_reuse_plies = 0

    # ------------------------------------------------------------------ API

    def search(
        self,
        board: Board,
        player: Player | int,
        *,
        time_budget_ms: float,
        cancel_event: threading.Event | None = None,
        priority_moves: tuple[Move, ...] = (),
        root_noise: bool | None = None,
        noise_rng: random.Random | None = None,
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
        apply_noise = (
            self.config.selfplay_dirichlet_enabled
            if root_noise is None
            else root_noise
        )
        self._node_count = 0
        self._last_root_noise_applied = False
        self._last_reuse_plies = 0
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
        timeout_check = lambda: self._check_timeout(deadline, cancel_event)
        root = _Node(move=None, player=position.current_player)
        try:
            root = self._make_root(
                position,
                timeout_check,
                apply_noise=apply_noise,
                noise_rng=noise_rng,
            )
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
            while True:
                self._check_timeout(deadline, cancel_event)
                if (
                    self.config.mcts_node_capacity > 0
                    and self._node_count >= self.config.mcts_node_capacity
                ):
                    break
                node = root
                self._refill_untried(node)
                while not node.untried and node.children:
                    child = self._best_child(node)
                    position.make_move(*child.move)
                    node = child
                    self._refill_untried(node)
                if node.terminal or (not node.untried and not node.children):
                    value = node.terminal_value
                else:
                    move = node.untried.pop(0)
                    position.make_move(*move)
                    child = _Node(
                        move=move, player=node.player.opponent, parent=node
                    )
                    self._node_count += 1
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
                        leaf_priority = priority_moves
                        forced_value: float | None = None
                        if self.config.mcts_leaf_tactics_enabled:
                            tactics = classify_leaf(
                                position,
                                child.player,
                                self._policy_pool(position)
                                | {
                                    move
                                    for move in priority_moves
                                    if position.is_empty(*move)
                                },
                            )
                            if tactics.immediate_win is not None:
                                leaf_priority = priority_moves + (
                                    tactics.immediate_win,
                                )
                                forced_value = 1.0
                            elif tactics.double_four is not None:
                                forced_value = 1.0
                            elif tactics.opponent_win is not None:
                                leaf_priority = priority_moves + (
                                    tactics.opponent_win,
                                )
                        (
                            child.priors,
                            child.untried,
                            child.pending,
                        ) = self._expand(
                            position,
                            child.player,
                            leaf_priority,
                            timeout_check,
                        )
                        if forced_value is not None:
                            value = forced_value
                        else:
                            value = self.provider.value(
                                position,
                                child.player,
                                timeout_check=timeout_check,
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
                simulations += 1
        except MCTSTimeout:
            timed_out = True
        move = self._final_move(position, root)
        elapsed = (self.clock() - started) * 1000.0
        self._remember_reuse(position, root, timed_out, move)
        return MCTSResult(
            move=move,
            simulations=simulations,
            root_visits=root.visits,
            elapsed_ms=max(0.0, elapsed),
            timed_out=timed_out,
            value=self._root_value(root),
            root_moves=self._root_moves(root),
            root_noise_applied=self._last_root_noise_applied,
            reuse_plies=self._last_reuse_plies,
        )

    # ------------------------------------------------------------- plumbing

    def _make_root(
        self,
        position: SearchPosition,
        timeout_check: Callable[[], None] | None,
        *,
        apply_noise: bool = False,
        noise_rng: random.Random | None = None,
    ) -> _Node:
        if (
            self.config.mcts_reuse_root
            and not self._reuse_timed_out
            and self._reuse_subtree is not None
        ):
            old = self._reuse_subtree
            if (
                self._reuse_hash == position.hash_key
                and old.player == position.current_player
            ):
                self._last_reuse_plies = 1
                return self._wrap_subtree(position, old)
            rerooted = self._try_reroot(position, old)
            if rerooted is not None:
                self._last_reuse_plies = 2
                return self._wrap_subtree(
                    position, rerooted, inherit_stats=True
                )
        root = _Node(move=None, player=position.current_player)
        root.priors, root.untried, root.pending = self._expand(
            position, root.player, (), timeout_check
        )
        if apply_noise and root.priors:
            root.priors = apply_dirichlet_noise(
                root.priors,
                noise_rng if noise_rng is not None else self._rng,
                self.config.selfplay_dirichlet_epsilon,
                self.config.selfplay_dirichlet_alpha,
            )
            root.untried = sorted(
                root.untried,
                key=lambda move: (
                    -root.priors.get(move, 0.0),
                    self._center_distance(position, move),
                    move[0],
                    move[1],
                ),
            )
            self._last_root_noise_applied = True
        return root

    def _wrap_subtree(
        self,
        position: SearchPosition,
        node: _Node,
        *,
        inherit_stats: bool = False,
    ) -> _Node:
        """Re-link a stored subtree as the root of the current position.

        Statistics are preserved; children, priors, untried and pending
        moves that are no longer legal (occupied cells) are dropped. A
        cross-turn reroot also inherits the wrapped node's own visits and
        value sum, since that node already earned them on exactly this
        position.
        """

        root = _Node(move=None, player=position.current_player)
        if inherit_stats:
            root.visits = node.visits
            root.value_sum = node.value_sum
        root.children = {
            move: child
            for move, child in node.children.items()
            if position.is_empty(*move)
        }
        root.priors = {
            move: prior
            for move, prior in node.priors.items()
            if position.is_empty(*move)
        }
        root.untried = [
            move for move in node.untried if position.is_empty(*move)
        ]
        root.pending = [
            move for move in node.pending if position.is_empty(*move)
        ]
        for child in root.children.values():
            child.parent = root
        return root

    def _try_reroot(
        self, position: SearchPosition, old: _Node
    ) -> _Node | None:
        """Advance the stored subtree through the moves played since the
        previous search: our chosen move (one ply) and, when the opponent
        has replied, their move (two plies). Both the board diff and the
        Zobrist arithmetic are verified; any mismatch discards the reuse.
        """

        stored_move = self._reuse_root_move
        stored_grid = self._reuse_grid
        if stored_move is None or stored_grid is None:
            return None
        if len(stored_grid) != position.size or any(
            len(row) != position.size for row in stored_grid
        ):
            return None
        added = [
            (row, col, cell)
            for row in range(position.size)
            for col in range(position.size)
            if (cell := position.grid[row][col]) != stored_grid[row][col]
        ]
        ours = [move for move in added if move[2] == int(old.player)]
        if len(ours) != 1 or (ours[0][0], ours[0][1]) != stored_move:
            return None
        child = old.children.get(stored_move)
        if child is None:
            return None
        zobrist = position.zobrist
        theirs = [
            (row, col)
            for row, col, cell in added
            if cell != int(old.player)
        ]
        if len(theirs) == 0:
            if child.player != position.current_player:
                return None
            expected = (
                self._reuse_hash
                ^ zobrist.piece_key(*stored_move, old.player)
                ^ zobrist.side_to_move_key
            )
            if expected != position.hash_key:
                return None
            return child
        if len(theirs) == 1:
            opp_move = theirs[0]
            grandchild = child.children.get(opp_move)
            if (
                grandchild is None
                or grandchild.player != position.current_player
            ):
                return None
            expected = (
                self._reuse_hash
                ^ zobrist.piece_key(*stored_move, old.player)
                ^ zobrist.side_to_move_key
                ^ zobrist.piece_key(*opp_move, old.player.opponent)
                ^ zobrist.side_to_move_key
            )
            if expected != position.hash_key:
                return None
            return grandchild
        return None

    def _expand(
        self,
        position: SearchPosition,
        player: Player,
        priority_moves: tuple[Move, ...],
        timeout_check: Callable[[], None] | None,
    ) -> tuple[dict[Move, float], list[Move], list[Move]]:
        pool = sorted(
            self._policy_pool(position)
            | {
                move
                for move in priority_moves
                if position.is_empty(*move)
            }
            | self._global_pool(position, player, timeout_check)
        )
        priors: dict[Move, float] = {}
        if not pool:
            return priors, [], []
        policy = self.provider.policy(
            position, player, pool, timeout_check=timeout_check
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
        ordered = sorted(
            pool,
            key=lambda move: (
                -priors.get(move, 0.0),
                self._center_distance(position, move),
                move[0],
                move[1],
            ),
        )
        if self.config.mcts_pw_enabled:
            initial = self.config.mcts_pw_initial_children
            return priors, ordered[:initial], ordered[initial:]
        return priors, ordered, []

    def _global_pool(
        self,
        position: SearchPosition,
        player: Player,
        timeout_check: Callable[[], None] | None,
    ) -> set[Move]:
        """Whole-board candidates contributed by a trained model.

        The heuristic provider (and any provider without the hook)
        contributes nothing, so the local tactical pool stays the only
        candidate source in heuristic mode.
        """

        k = self.config.mcts_global_top_k
        if k <= 0:
            return set()
        top_k = getattr(self.provider, "global_top_k", None)
        if top_k is None:
            return set()
        return {
            move
            for move in top_k(
                position, player, k, timeout_check=timeout_check
            )
            if position.is_empty(*move)
        }

    def _children_allowed(self, visits: int) -> int:
        if not self.config.mcts_pw_enabled:
            return 10 ** 9
        return self.config.mcts_pw_initial_children + int(
            self.config.mcts_pw_growth * (visits ** 0.5)
        )

    def _refill_untried(self, node: _Node) -> None:
        """Promote the next slice of pending moves once visits allow it."""

        if not node.pending:
            return
        allowed = self._children_allowed(node.visits)
        exposed = len(node.children) + len(node.untried)
        if exposed < allowed:
            take = allowed - exposed
            node.untried.extend(node.pending[:take])
            del node.pending[:take]

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
    ) -> None:
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
        self,
        position: SearchPosition,
        root: _Node,
        timed_out: bool,
        chosen_move: Move | None,
    ) -> None:
        self._reuse_hash = position.hash_key
        self._reuse_subtree = root
        self._reuse_timed_out = timed_out
        self._reuse_root_move = chosen_move
        self._reuse_grid = [row.copy() for row in position.grid]

    def clear_reuse(self) -> None:
        self._reuse_hash = None
        self._reuse_subtree = None
        self._reuse_timed_out = False
        self._reuse_root_move = None
        self._reuse_grid = None
