"""Threat-space search for HardAI: verified VCF/VCT and forced defense.

Public API
----------
``find_immediate_win(board, player)``, ``find_forcing_win(...)`` and
``find_forced_defense(...)`` are stateless conveniences. They return ``None``
both for ``NOT_FOUND`` and for ``TIMEOUT``; use :class:`ThreatSearch` directly
when the distinction matters (HardAI keeps it for decisions and debugging).

Semantics
---------
* ``FOUND`` means every relevant defender reply (threat blocks, counter-win
  cells and counter-four cells) was enumerated completely and verified to
  lose; no reply set is ever truncated.
* ``NOT_FOUND`` means the search completed within budget and disproved a
  forcing win.
* ``TIMEOUT`` is inconclusive: it is never treated as a disproof and never
  yields a move (``attacker_moves`` stays empty). The deadline and cancel
  event are checked at every search node and inside every candidate/reply
  enumeration loop, so the budget is a real deadline.

The search is deterministic: candidates and replies are sorted by
``(tactical class, center distance, row, col)`` and the transposition table
uses depth-aware semantics (a shallow ``FOUND`` stays valid at deeper
remaining depth, a deep ``NOT_FOUND`` stays valid at shallower depth).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG, HardAIConfig
from gomoku.ai.pattern_matcher import (
    PATTERN_SEVERITY,
    PatternKind,
    PatternMatcher,
)
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import DIRECTIONS, check_win

Move = tuple[int, int]

MODE_VCF = "vcf"
MODE_VCT = "vct"
MODE_AUTO = "auto"
MODE_DEFENSE = "defense"

FOUR_KINDS = {PatternKind.OPEN_FOUR, PatternKind.CLOSED_FOUR}
THREE_KINDS = {PatternKind.OPEN_THREE, PatternKind.JUMP_THREE}
TACTICAL_KINDS = FOUR_KINDS | THREE_KINDS

DEFAULT_API_BUDGET_MS = 500.0


class SearchStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"


class ThreatSearchTimeout(RuntimeError):
    """Internal cooperative deadline signal; never escapes ThreatSearch."""


@dataclass(frozen=True)
class ThreatSearchResult:
    status: SearchStatus
    attacker_moves: tuple[Move, ...] = ()
    forced_defenses: tuple[Move, ...] = ()
    winning_points: tuple[Move, ...] = ()
    nodes: int = 0
    elapsed_ms: float = 0.0
    mode: str = ""

    @property
    def first_move(self) -> Move | None:
        return self.attacker_moves[0] if self.attacker_moves else None


class ThreatSearch:
    """Verified forcing-win search (VCF and VCT) plus forced defense."""

    def __init__(
        self,
        config: HardAIConfig,
        zobrist: ZobristTable,
        *,
        matcher: PatternMatcher | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.zobrist = zobrist
        self.matcher = matcher or PatternMatcher(config.pattern_line_cache_capacity)
        self.clock = clock
        self.nodes = 0
        self.tt_hits = 0
        self._table: OrderedDict[
            tuple[int, Player, str, int], tuple[ThreatSearchResult, int]
        ] = OrderedDict()

    # ------------------------------------------------------------------ API

    def immediate_win(self, board: Board, player: Player | int) -> tuple[Move, ...]:
        """All cells where ``player`` completes a five right now."""
        position = SearchPosition.from_board(
            board,
            Player(player),
            self.zobrist,
            max_candidate_radius=self.config.candidate_radius,
        )
        return self._winning_cells(position, Player(player))

    def find_forcing_win(
        self,
        board: Board,
        player: Player | int,
        *,
        mode: str = MODE_AUTO,
        max_depth: int | None = None,
        time_budget_ms: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ThreatSearchResult:
        """Search a verified forcing win for ``player``.

        ``mode``: MODE_VCF (fours only), MODE_VCT (fours + open/jump threes,
        VCF attempted first at every attacker node) or MODE_AUTO (VCF slice,
        then VCT iterative deepening, sharing one deadline).
        """
        attacker = Player(player)
        started = self.clock()
        budget = max(1.0, time_budget_ms if time_budget_ms is not None
                     else DEFAULT_API_BUDGET_MS)
        deadline = started + budget / 1000.0
        self.nodes = 0
        self.tt_hits = 0
        position = SearchPosition.from_board(
            board,
            attacker,
            self.zobrist,
            max_candidate_radius=self.config.candidate_radius,
        )
        vcf_depth = self.config.vcf_max_depth
        vct_depth = self.config.vct_max_depth
        if max_depth is not None:
            vcf_depth = min(vcf_depth, max(1, max_depth))
            vct_depth = min(vct_depth, max(1, max_depth))

        try:
            if mode in (MODE_VCF, MODE_AUTO):
                vcf_deadline = deadline
                if mode == MODE_AUTO:
                    vcf_deadline = (
                        started + budget * self.config.vcf_time_fraction / 1000.0
                    )
                vcf_result = self._search(
                    position, attacker, vcf_depth, MODE_VCF,
                    vcf_deadline, cancel_event,
                )
                if vcf_result.status == SearchStatus.FOUND:
                    return self._finish(vcf_result, started)
                if mode == MODE_VCF:
                    return self._finish(vcf_result, started)
            if mode in (MODE_VCT, MODE_AUTO):
                last: ThreatSearchResult | None = None
                for depth in range(2, vct_depth + 1):
                    result = self._search(
                        position, attacker, depth, MODE_VCT,
                        deadline, cancel_event,
                    )
                    if result.status == SearchStatus.FOUND:
                        return self._finish(result, started)
                    last = result
                return self._finish(
                    last or ThreatSearchResult(SearchStatus.NOT_FOUND), started
                )
            raise ValueError(f"Unknown threat search mode: {mode}.")
        except ThreatSearchTimeout:
            return self._finish(
                ThreatSearchResult(SearchStatus.TIMEOUT, mode=mode), started
            )

    def find_forced_defense(
        self,
        board: Board,
        me: Player | int,
        opponent_chain: tuple[Move, ...],
        *,
        time_budget_ms: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ThreatSearchResult:
        """Return a verified defense against an opponent forcing chain.

        Every candidate is tested: playing it must either win for ``me``
        immediately or leave the opponent without a verified forcing win.
        Candidates are the chain's proof-critical cells first, then empty
        interference cells (Chebyshev distance <= 1 of any chain cell);
        the candidate set is enumerated completely, never truncated.
        ``chain[0]`` is never returned blindly.
        """
        defender = Player(me)
        attacker = defender.opponent
        started = self.clock()
        budget = max(1.0, time_budget_ms if time_budget_ms is not None
                     else DEFAULT_API_BUDGET_MS)
        deadline = started + budget / 1000.0
        self.nodes = 0
        self.tt_hits = 0
        position = SearchPosition.from_board(
            board,
            defender,
            self.zobrist,
            max_candidate_radius=self.config.candidate_radius,
        )
        try:
            timeout_check = lambda: self._check_timeout(deadline, cancel_event)
            candidates = self._defense_candidates(
                position, opponent_chain, timeout_check
            )
            if not candidates:
                return self._finish(
                    ThreatSearchResult(
                        SearchStatus.NOT_FOUND, mode=MODE_DEFENSE
                    ),
                    started,
                )
            timed_out = False
            for move in candidates:
                self._check_timeout(deadline, cancel_event)
                position.make_move(*move)
                try:
                    last = position.last_move
                    if last is not None and check_win(
                        position, last.row, last.col, defender
                    ):
                        return self._finish(
                            ThreatSearchResult(
                                SearchStatus.FOUND,
                                forced_defenses=(move,),
                                winning_points=(move,),
                                mode=MODE_DEFENSE,
                            ),
                            started,
                        )
                    remaining = max(
                        0.0, (deadline - self.clock()) * 1000.0
                    )
                    continuation = self.find_forcing_win(
                        position,
                        attacker,
                        mode=MODE_AUTO,
                        time_budget_ms=remaining,
                        cancel_event=cancel_event,
                    )
                    if continuation.status == SearchStatus.NOT_FOUND:
                        return self._finish(
                            ThreatSearchResult(
                                SearchStatus.FOUND,
                                forced_defenses=(move,),
                                mode=MODE_DEFENSE,
                            ),
                            started,
                        )
                    if continuation.status == SearchStatus.TIMEOUT:
                        timed_out = True
                finally:
                    position.undo_move()
            return self._finish(
                ThreatSearchResult(
                    SearchStatus.TIMEOUT if timed_out else SearchStatus.NOT_FOUND,
                    mode=MODE_DEFENSE,
                ),
                started,
            )
        except ThreatSearchTimeout:
            return self._finish(
                ThreatSearchResult(SearchStatus.TIMEOUT, mode=MODE_DEFENSE),
                started,
            )

    def clear(self) -> None:
        self._table.clear()

    @property
    def table_size(self) -> int:
        return len(self._table)

    # ------------------------------------------------------------- plumbing

    def _finish(
        self, result: ThreatSearchResult, started: float
    ) -> ThreatSearchResult:
        return replace(
            result,
            nodes=self.nodes,
            elapsed_ms=max(0.0, (self.clock() - started) * 1000.0),
        )

    def _check_timeout(
        self,
        deadline: float,
        cancel_event: threading.Event | None,
    ) -> None:
        if (cancel_event is not None and cancel_event.is_set()) or (
            self.clock() >= deadline
        ):
            raise ThreatSearchTimeout

    def _winning_cells(
        self, position: SearchPosition, player: Player
    ) -> tuple[Move, ...]:
        wins = []
        for move in sorted(position.nearby_empty_moves(1)):
            if position.move_wins(*move, player):
                wins.append(move)
        return tuple(self._sort_moves(position, wins))

    def _sort_moves(
        self, position: SearchPosition, moves: list[Move]
    ) -> list[Move]:
        center = (position.size - 1) / 2
        return sorted(
            moves,
            key=lambda move: (
                max(abs(move[0] - center), abs(move[1] - center)),
                move[0],
                move[1],
            ),
        )

    def _patterns_after(
        self,
        position: SearchPosition,
        move: Move,
        player: Player,
        timeout_check: Callable[[], None] | None,
    ):
        row, col = move
        position.grid[row][col] = int(player)
        try:
            return self.matcher.find_patterns_through_move(
                position, player, move, timeout_check
            )
        finally:
            position.grid[row][col] = int(Player.EMPTY)

    def _would_create_four(
        self,
        position: SearchPosition,
        move: Move,
        player: Player,
        dr: int,
        dc: int,
    ) -> bool:
        """Would placing ``player`` at ``move`` create a four on one line?

        Exact: a four is a five-window holding exactly four friendly stones
        and one empty cell (the move counted as placed), matching the
        pattern matcher's classification. Dead fours have no such window.
        """
        row, col = move
        own = int(player)
        for shift in range(-4, 1):
            start_row = row + dr * shift
            start_col = col + dc * shift
            end_row = start_row + dr * 4
            end_col = start_col + dc * 4
            if not (
                position.is_inside(start_row, start_col)
                and position.is_inside(end_row, end_col)
            ):
                continue
            stones = 0
            valid = True
            for step in range(5):
                cell_row = start_row + dr * step
                cell_col = start_col + dc * step
                if (cell_row, cell_col) == (row, col):
                    stones += 1
                    continue
                cell = position.grid[cell_row][cell_col]
                if cell == own:
                    stones += 1
                elif cell != int(Player.EMPTY):
                    valid = False
                    break
            if valid and stones == 4:
                return True
        return False

    def _creates_four(
        self,
        position: SearchPosition,
        move: Move,
        player: Player,
        timeout_check: Callable[[], None] | None,
    ) -> bool:
        return any(
            self._would_create_four(position, move, player, dr, dc)
            for dr, dc in DIRECTIONS
        )

    def _has_three_window(
        self,
        position: SearchPosition,
        move: Move,
        player: Player,
    ) -> bool:
        """Cheap pre-filter: does placing a stone yield a three-stone window?

        Fast window scan; false positives are fine (the defender node
        re-verifies every threat exactly through the pattern matcher).
        """
        row, col = move
        own = int(player)
        for dr, dc in DIRECTIONS:
            for shift in range(-4, 1):
                start_row = row + dr * shift
                start_col = col + dc * shift
                end_row = start_row + dr * 4
                end_col = start_col + dc * 4
                if not (
                    position.is_inside(start_row, start_col)
                    and position.is_inside(end_row, end_col)
                ):
                    continue
                stones = 0
                valid = True
                for step in range(5):
                    cell_row = start_row + dr * step
                    cell_col = start_col + dc * step
                    if (cell_row, cell_col) == (row, col):
                        stones += 1
                        continue
                    cell = position.grid[cell_row][cell_col]
                    if cell == own:
                        stones += 1
                    elif cell != int(Player.EMPTY):
                        valid = False
                        break
                if valid and stones == 3:
                    return True
        return False

    def _threat_moves(
        self,
        position: SearchPosition,
        attacker: Player,
        include_threes: bool,
        timeout_check: Callable[[], None] | None,
    ) -> list[tuple[Move, int]]:
        """Tactical attacker moves, ordered (double four, four, three).

        Fours are detected with exact run counting; three candidates pass a
        cheap window pre-filter before the exact pattern-matcher probe.
        """
        pool = sorted(position.nearby_empty_moves(self.config.candidate_radius))
        ranked: list[tuple[Move, int]] = []
        for move in pool:
            if timeout_check is not None:
                timeout_check()
            four_dirs = [
                (dr, dc)
                for dr, dc in DIRECTIONS
                if self._would_create_four(position, move, attacker, dr, dc)
            ]
            if len(four_dirs) >= 2:
                ranked.append((move, 0))
                continue
            if four_dirs:
                ranked.append((move, 1))
                continue
            if include_threes and self._has_three_window(
                position, move, attacker
            ):
                severity = self._three_severity_after(
                    position, move, attacker, timeout_check
                )
                if severity > 0:
                    ranked.append((move, 2 + 100 - severity))
        return sorted(
            ranked,
            key=lambda item: (
                item[1],
                self._center_distance(position, item[0]),
                item[0][0],
                item[0][1],
            ),
        )

    def _three_severity_after(
        self,
        position: SearchPosition,
        move: Move,
        attacker: Player,
        timeout_check: Callable[[], None] | None,
    ) -> int:
        threes = [
            pattern
            for pattern in self._patterns_after(
                position, move, attacker, timeout_check
            )
            if pattern.kind in THREE_KINDS
        ]
        if not threes:
            return 0
        return max(PATTERN_SEVERITY[pattern.kind] for pattern in threes)

    def _center_distance(self, position: SearchPosition, move: Move) -> float:
        center = (position.size - 1) / 2
        return max(abs(move[0] - center), abs(move[1] - center))

    def _block_cells(
        self,
        position: SearchPosition,
        attacker: Player,
        last_attacker_move: Move,
        required_kinds: set[PatternKind],
        timeout_check: Callable[[], None] | None,
    ) -> set[Move]:
        """Exact key cells of every required-kind pattern the move created."""
        patterns = self.matcher.find_patterns_through_move(
            position, attacker, last_attacker_move, timeout_check
        )
        return {
            move
            for pattern in patterns
            if pattern.kind in required_kinds
            for move in pattern.key_empties
            if position.is_empty(*move)
        }

    def _counter_cells(
        self,
        position: SearchPosition,
        defender: Player,
        blocks: set[Move],
        timeout_check: Callable[[], None] | None,
    ) -> tuple[Move, ...]:
        """Defender replies that win or counter-four, beyond plain blocks.

        Win cells first, then four cells: both usually refute immediately
        (the attacker node then sees two defender winning cells), so trying
        them before the blocks keeps disproof cheap. The reply set is
        enumerated completely — no truncation — so a FOUND proof means every
        relevant defender reply was actually verified.
        """
        wins: list[Move] = []
        fours: list[Move] = []
        for move in self._sort_moves(
            position, list(position.nearby_empty_moves(1))
        ):
            if timeout_check is not None:
                timeout_check()
            if move in blocks:
                continue
            if position.move_wins(*move, defender):
                wins.append(move)
            elif self._creates_four(position, move, defender, timeout_check):
                fours.append(move)
        return tuple(wins + fours)

    def _defense_candidates(
        self,
        position: SearchPosition,
        opponent_chain: tuple[Move, ...],
        timeout_check: Callable[[], None] | None,
    ) -> tuple[Move, ...]:
        seen: set[Move] = set()
        candidates: list[Move] = []
        for move in opponent_chain:
            if timeout_check is not None:
                timeout_check()
            if (
                position.is_inside(*move)
                and position.is_empty(*move)
                and move not in seen
            ):
                seen.add(move)
                candidates.append(move)
        interference: list[Move] = []
        for row, col in opponent_chain:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if timeout_check is not None:
                        timeout_check()
                    candidate = (row + dr, col + dc)
                    if (
                        position.is_inside(*candidate)
                        and position.is_empty(*candidate)
                        and candidate not in seen
                    ):
                        seen.add(candidate)
                        interference.append(candidate)
        return tuple(candidates) + tuple(self._sort_moves(position, interference))

    # ----------------------------------------------------------- search

    def _search(
        self,
        position: SearchPosition,
        attacker: Player,
        remaining_depth: int,
        mode: str,
        deadline: float,
        cancel_event: threading.Event | None,
    ) -> ThreatSearchResult:
        self._check_timeout(deadline, cancel_event)
        self.nodes += 1
        if remaining_depth <= 0:
            return ThreatSearchResult(SearchStatus.NOT_FOUND, mode=mode)
        key = (position.hash_key, attacker, mode, remaining_depth)
        cached = self._table.get(key)
        if cached is not None:
            result, depth = cached
            if (
                result.status == SearchStatus.FOUND
                and depth <= remaining_depth
            ) or (
                result.status == SearchStatus.NOT_FOUND
                and depth >= remaining_depth
            ):
                self.tt_hits += 1
                self._table.move_to_end(key)
                return result

        result = self._search_uncached(
            position, attacker, remaining_depth, mode, deadline, cancel_event
        )
        if result.status != SearchStatus.TIMEOUT:
            self._store(key, result, remaining_depth)
        return result

    def _search_uncached(
        self,
        position: SearchPosition,
        attacker: Player,
        remaining_depth: int,
        mode: str,
        deadline: float,
        cancel_event: threading.Event | None,
    ) -> ThreatSearchResult:
        timeout_check = lambda: self._check_timeout(deadline, cancel_event)
        defender = attacker.opponent

        if mode == MODE_VCT:
            vcf_result = self._search(
                position,
                attacker,
                min(self.config.vcf_max_depth, remaining_depth),
                MODE_VCF,
                deadline,
                cancel_event,
            )
            if vcf_result.status == SearchStatus.FOUND:
                return replace(vcf_result, mode=MODE_VCT)
            if vcf_result.status == SearchStatus.TIMEOUT:
                return replace(vcf_result, mode=MODE_VCT)

        wins = self._winning_cells(position, attacker)
        if wins:
            return ThreatSearchResult(
                SearchStatus.FOUND,
                attacker_moves=(wins[0],),
                winning_points=wins,
                mode=mode,
            )

        defender_wins = self._winning_cells(position, defender)
        if defender_wins:
            if len(defender_wins) > 1:
                return ThreatSearchResult(SearchStatus.NOT_FOUND, mode=mode)
            block = defender_wins[0]
            position.make_move(*block)
            try:
                continuation = self._search_defender(
                    position,
                    attacker,
                    block,
                    remaining_depth - 1,
                    mode,
                    deadline,
                    cancel_event,
                )
                if continuation.status == SearchStatus.FOUND:
                    return ThreatSearchResult(
                        SearchStatus.FOUND,
                        attacker_moves=(block,) + continuation.attacker_moves,
                        forced_defenses=continuation.forced_defenses,
                        winning_points=continuation.winning_points,
                        mode=mode,
                    )
                return continuation
            finally:
                position.undo_move()

        for move, _kind in self._threat_moves(
            position, attacker, include_threes=(mode == MODE_VCT),
            timeout_check=timeout_check,
        ):
            timeout_check()
            position.make_move(*move)
            try:
                continuation = self._search_defender(
                    position,
                    attacker,
                    move,
                    remaining_depth - 1,
                    mode,
                    deadline,
                    cancel_event,
                )
                if continuation.status == SearchStatus.FOUND:
                    return ThreatSearchResult(
                        SearchStatus.FOUND,
                        attacker_moves=(move,) + continuation.attacker_moves,
                        forced_defenses=continuation.forced_defenses,
                        winning_points=continuation.winning_points,
                        mode=mode,
                    )
                if continuation.status == SearchStatus.TIMEOUT:
                    return continuation
            finally:
                position.undo_move()

        return ThreatSearchResult(SearchStatus.NOT_FOUND, mode=mode)

    def _search_defender(
        self,
        position: SearchPosition,
        attacker: Player,
        last_attacker_move: Move,
        remaining_depth: int,
        mode: str,
        deadline: float,
        cancel_event: threading.Event | None,
    ) -> ThreatSearchResult:
        """Defender-to-move node.

        ``remaining_depth`` counts attacker plies available after the
        defender's reply (the attacker's own move already consumed one).
        """
        self._check_timeout(deadline, cancel_event)
        self.nodes += 1
        defender = attacker.opponent
        timeout_check = lambda: self._check_timeout(deadline, cancel_event)
        required_kinds = FOUR_KINDS if mode == MODE_VCF else TACTICAL_KINDS
        blocks = self._block_cells(
            position, attacker, last_attacker_move, required_kinds,
            timeout_check,
        )
        if not blocks:
            # No required-kind pattern passes through the attacker's move
            # (fast classifiers can over-generate): it cannot be forcing.
            return ThreatSearchResult(SearchStatus.NOT_FOUND, mode=mode)
        replies = self._counter_cells(
            position, defender, blocks, timeout_check
        ) + tuple(sorted(blocks))

        canonical = None
        for defense in replies:
            timeout_check()
            position.make_move(*defense)
            try:
                last = position.last_move
                if last is not None and check_win(
                    position, last.row, last.col, defender
                ):
                    return ThreatSearchResult(
                        SearchStatus.NOT_FOUND, mode=mode
                    )
                continuation = self._search(
                    position,
                    attacker,
                    remaining_depth,
                    mode,
                    deadline,
                    cancel_event,
                )
                if continuation.status == SearchStatus.NOT_FOUND:
                    return ThreatSearchResult(
                        SearchStatus.NOT_FOUND, mode=mode
                    )
                if continuation.status == SearchStatus.TIMEOUT:
                    return continuation
                if canonical is None:
                    canonical = (defense, continuation)
            finally:
                position.undo_move()

        if canonical is None:
            return ThreatSearchResult(SearchStatus.NOT_FOUND, mode=mode)
        defense, continuation = canonical
        return ThreatSearchResult(
            SearchStatus.FOUND,
            attacker_moves=continuation.attacker_moves,
            forced_defenses=(defense,) + continuation.forced_defenses,
            winning_points=continuation.winning_points,
            mode=mode,
        )

    def _store(
        self,
        key: tuple[int, Player, str, int],
        result: ThreatSearchResult,
        depth: int,
    ) -> None:
        capacity = max(0, self.config.threat_transposition_capacity)
        if capacity == 0:
            return
        self._table[key] = (result, depth)
        self._table.move_to_end(key)
        while len(self._table) > capacity:
            self._table.popitem(last=False)


def _default_search(board: Board) -> ThreatSearch:
    zobrist = ZobristTable(board.size, DEFAULT_HARD_AI_CONFIG.zobrist_seed)
    return ThreatSearch(DEFAULT_HARD_AI_CONFIG, zobrist)


def find_immediate_win(board: Board, player: Player | int) -> Move | None:
    """First cell where ``player`` completes a five, or ``None``."""
    wins = _default_search(board).immediate_win(board, player)
    return wins[0] if wins else None


def find_forcing_win(
    board: Board,
    player: Player | int,
    max_depth: int | None = None,
    time_budget_ms: float | None = None,
) -> list[Move] | None:
    """Verified forcing win for ``player``.

    Returns the attacker move chain on ``FOUND``. Returns ``None`` for both
    ``NOT_FOUND`` and ``TIMEOUT`` — the two are only distinguishable through
    :class:`ThreatSearch`, which also reports nodes and elapsed time.
    """
    result = _default_search(board).find_forcing_win(
        board,
        player,
        mode=MODE_AUTO,
        max_depth=max_depth,
        time_budget_ms=time_budget_ms,
    )
    if result.status == SearchStatus.FOUND:
        return list(result.attacker_moves)
    return None


def find_forced_defense(
    board: Board,
    me: Player | int,
    opponent_chain: tuple[Move, ...],
) -> Move | None:
    """A verified defense against ``opponent_chain``, or ``None``.

    ``None`` means no defense could be verified within budget — not that the
    position is necessarily lost. See :class:`ThreatSearch` for the status.
    """
    result = _default_search(board).find_forced_defense(
        board, me, opponent_chain
    )
    if result.status == SearchStatus.FOUND and result.forced_defenses:
        return result.forced_defenses[0]
    return None
