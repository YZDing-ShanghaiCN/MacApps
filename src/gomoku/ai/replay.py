"""Deterministic replay-buffer helpers for HardAI self-play training.

The training loop must never accumulate every historical record in RAM:
:func:`reservoir_sample` streams gzip JSONL shards in one pass and keeps at
most ``max_records`` items (a seeded reservoir, so identical arguments
reproduce identical samples). File ordering is always ``sorted()`` by name,
so replay selection is deterministic, and :func:`is_val_record` gives a
stable train/validation partition derived from ``(path, line_index)`` that
does not drift when sampling or the epoch changes.
"""

from __future__ import annotations

import gzip
import json
import random
import zlib
from pathlib import Path
from typing import Iterator

SelfPlayRecord = dict


def select_replay_files(
    data_dir: str | Path, *, window: int | None = None
) -> list[Path]:
    """Newest-first-sorted selection of ``run_*.jsonl.gz`` shards.

    ``window`` limits the selection to the most recent ``window`` files;
    ``None`` or ``<= 0`` selects everything. Ordering is the sorted file
    name, which is the iteration index format ``run_%04d.jsonl.gz``.
    """

    data_dir = Path(data_dir)
    paths = sorted(data_dir.glob("run_*.jsonl.gz"))
    if window is not None and window > 0:
        return paths[-window:]
    return paths


def iter_records(
    paths: list[Path] | tuple[Path, ...],
) -> Iterator[tuple[Path, int, SelfPlayRecord]]:
    """Stream every record of every shard as ``(path, line_index, record)``."""

    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line_index, line in enumerate(handle):
                yield path, line_index, json.loads(line)


def reservoir_sample(
    paths: list[Path] | tuple[Path, ...],
    rng: random.Random,
    max_records: int | None,
) -> Iterator[tuple[Path, int, SelfPlayRecord]]:
    """Deterministic single-pass bounded sample of the records in ``paths``.

    ``max_records`` of ``None``/``<= 0`` streams everything without
    buffering. Otherwise a classic reservoir keeps at most ``max_records``
    items; all randomness comes from ``rng``, so the same seed and file
    ordering reproduce the exact same sample.
    """

    if max_records is None or max_records <= 0:
        yield from iter_records(paths)
        return
    reservoir: list[tuple[Path, int, SelfPlayRecord]] = []
    count = 0
    for item in iter_records(paths):
        if count < max_records:
            reservoir.append(item)
        else:
            slot = rng.randrange(count + 1)
            if slot < max_records:
                reservoir[slot] = item
        count += 1
    yield from reservoir


def is_val_record(path: Path, line_index: int, val_fraction: float) -> bool:
    """Stable train/validation membership for one record.

    The hash depends only on the shard path and the line index, so a record
    keeps its split across epochs, seeds and sampling sizes. ``val_fraction``
    is interpreted as a proportion of records (0.05 => ~5% validation).
    """

    if val_fraction <= 0.0:
        return False
    key = f"{path}:{line_index}".encode("utf-8")
    return zlib.crc32(key) % 10_000 < round(val_fraction * 10_000)


def stream_split(
    paths: list[Path] | tuple[Path, ...],
    *,
    rng: random.Random,
    max_records: int | None,
    val_fraction: float,
    want_val: bool,
) -> Iterator[tuple[Path, int, SelfPlayRecord]]:
    """Stream the train (or validation) half of the bounded sample.

    Both halves run the identical reservoir with an identically seeded RNG,
    then partition by :func:`is_val_record`, so train and validation stay
    disjoint and together cover exactly the sampled records.
    """

    for path, line_index, record in reservoir_sample(
        paths, rng, max_records
    ):
        if is_val_record(path, line_index, val_fraction) == want_val:
            yield path, line_index, record
