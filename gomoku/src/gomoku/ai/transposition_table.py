"""Capacity-bounded transposition table for NormalAI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BoundType(str, Enum):
    EXACT = "exact"
    LOWER = "lower"
    UPPER = "upper"


@dataclass(frozen=True)
class TranspositionEntry:
    key: int
    depth: int
    score: int
    bound: BoundType
    best_move: tuple[int, int] | None
    generation: int
    extension_depth: int = 0


class TranspositionTable:
    """A deterministic set-associative transposition table.

    Collisions prefer the current search generation and then deeper entries.
    The fixed bucket array makes the configured capacity a strict upper bound.
    """

    def __init__(self, capacity: int, bucket_size: int = 4) -> None:
        if capacity <= 0:
            raise ValueError("Transposition table capacity must be positive.")
        self.capacity = capacity
        self.bucket_size = max(1, min(bucket_size, capacity))
        self.bucket_count = max(1, capacity // self.bucket_size)
        self._buckets: list[list[TranspositionEntry]] = [
            [] for _ in range(self.bucket_count)
        ]
        self.generation = 0
        self.probes = 0
        self.hits = 0
        self.collisions = 0
        self.replacements = 0

    def new_generation(self) -> int:
        self.generation += 1
        return self.generation

    def clear(self) -> None:
        self._buckets = [[] for _ in range(self.bucket_count)]

    def probe(self, key: int) -> TranspositionEntry | None:
        self.probes += 1
        for entry in self._buckets[key % self.bucket_count]:
            if entry.key == key:
                self.hits += 1
                return entry
        return None

    def store(self, entry: TranspositionEntry) -> None:
        bucket = self._buckets[entry.key % self.bucket_count]
        for index, current in enumerate(bucket):
            if current.key != entry.key:
                continue
            if (
                entry.depth > current.depth
                or entry.extension_depth > current.extension_depth
                or entry.bound == BoundType.EXACT
                or entry.generation > current.generation
            ):
                bucket[index] = entry
            return
        if len(bucket) < self.bucket_size:
            bucket.append(entry)
            return

        self.collisions += 1
        victim_index = min(
            range(len(bucket)),
            key=lambda index: (
                bucket[index].generation == entry.generation,
                bucket[index].depth + bucket[index].extension_depth,
                bucket[index].bound == BoundType.EXACT,
            ),
        )
        victim = bucket[victim_index]
        if (
            entry.generation > victim.generation
            or entry.depth + entry.extension_depth
            >= victim.depth + victim.extension_depth
        ):
            bucket[victim_index] = entry
            self.replacements += 1
