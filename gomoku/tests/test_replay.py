from pathlib import Path
import gzip
import json
import random
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

import pytest  # noqa: E402

from gomoku.ai.replay import (  # noqa: E402
    is_val_record,
    reservoir_sample,
    select_replay_files,
    stream_split,
)


def _record(index: int) -> dict:
    planes = [[[0] * 15 for _ in range(15)] for _ in range(2)]
    planes[0][index % 15][index % 15] = 1
    policy = [1.0 / 225] * 225
    policy[index % 225] += 1.0 / 225
    return {
        "player": 1,
        "move": [index % 15, index % 15],
        "planes": planes,
        "policy": policy,
        "outcome": 1 if index % 2 == 0 else -1,
    }


def _write_shard(path: Path, count: int) -> None:
    payload = "".join(
        json.dumps(_record(index)) + "\n" for index in range(count)
    ).encode("utf-8")
    with open(path, "wb") as raw:
        raw.write(gzip.compress(payload, mtime=0))


def _make_shards(tmp_path: Path, counts: list[int]) -> list[Path]:
    paths = []
    for index, count in enumerate(counts):
        path = tmp_path / f"run_{index:04d}.jsonl.gz"
        _write_shard(path, count)
        paths.append(path)
    return paths


def test_select_replay_files_window_drops_only_oldest(tmp_path) -> None:
    paths = _make_shards(tmp_path, [5, 5, 5, 5, 5, 5])

    assert select_replay_files(tmp_path, window=4) == paths[-4:]
    assert select_replay_files(tmp_path, window=6) == paths
    assert select_replay_files(tmp_path, window=0) == paths
    assert select_replay_files(tmp_path, window=None) == paths


def test_select_replay_files_is_name_ordered_and_deterministic(
    tmp_path,
) -> None:
    _make_shards(tmp_path, [3, 3, 3])
    first = select_replay_files(tmp_path, window=2)
    second = select_replay_files(tmp_path, window=2)
    assert first == second
    assert [path.name for path in first] == [
        "run_0001.jsonl.gz",
        "run_0002.jsonl.gz",
    ]


def test_reservoir_sample_caps_records(tmp_path) -> None:
    paths = _make_shards(tmp_path, [40, 40, 40])
    rng = random.Random(7)

    sample = list(reservoir_sample(paths, rng, max_records=10))

    assert len(sample) == 10
    assert len({(str(path), line) for path, line, _ in sample}) == 10


def test_reservoir_sample_deterministic_same_seed(tmp_path) -> None:
    paths = _make_shards(tmp_path, [40, 40, 40])

    first = list(reservoir_sample(paths, random.Random(3), 25))
    second = list(reservoir_sample(paths, random.Random(3), 25))

    assert first == second


def test_reservoir_sample_different_seed_different_sample(tmp_path) -> None:
    paths = _make_shards(tmp_path, [60, 60, 60])

    first = list(reservoir_sample(paths, random.Random(11), 20))
    second = list(reservoir_sample(paths, random.Random(12), 20))

    assert first != second


def test_reservoir_sample_unlimited_streams_everything(tmp_path) -> None:
    paths = _make_shards(tmp_path, [7, 9])

    sample = list(reservoir_sample(paths, random.Random(0), None))

    assert len(sample) == 16


def test_stream_split_partitions_and_stays_stable(tmp_path) -> None:
    paths = _make_shards(tmp_path, [50, 50])

    train = list(
        stream_split(
            paths,
            rng=random.Random(5),
            max_records=60,
            val_fraction=0.25,
            want_val=False,
        )
    )
    val = list(
        stream_split(
            paths,
            rng=random.Random(5),
            max_records=60,
            val_fraction=0.25,
            want_val=True,
        )
    )
    again = list(
        stream_split(
            paths,
            rng=random.Random(5),
            max_records=60,
            val_fraction=0.25,
            want_val=True,
        )
    )

    keys_train = {(str(path), line) for path, line, _ in train}
    keys_val = {(str(path), line) for path, line, _ in val}
    assert keys_train.isdisjoint(keys_val)
    assert len(train) + len(val) == 60
    assert val == again


def test_is_val_record_depends_only_on_path_and_line(tmp_path) -> None:
    path = Path("data/run_0001.jsonl.gz")

    assert is_val_record(path, 3, 0.25) == is_val_record(path, 3, 0.25)
    assert isinstance(is_val_record(path, 4, 0.25), bool)
    assert is_val_record(path, 0, 0.0) is False
    assert is_val_record(path, 0, 1.0) is True


def test_tiny_streaming_training_smoke(tmp_path) -> None:
    pytest.importorskip("torch")
    import importlib.util

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "train_policy_value.py"
    )
    spec = importlib.util.spec_from_file_location(
        "train_policy_value_smoke", script
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    paths = _make_shards(tmp_path, [80])
    output = tmp_path / "smoke.pt"
    summary = module.train(
        data=[str(paths[0])],
        output=output,
        epochs=1,
        batch_size=16,
        lr=1e-3,
        blocks=1,
        channels=4,
        val_fraction=0.25,
        seed=0,
        replay_seed=0,
        replay_window=8,
        replay_max_records=64,
    )

    assert output.exists()
    assert summary["files"] == [str(paths[0])]
    epoch = summary["epochs"][0]
    assert epoch["train_records"] > 0
    assert epoch["val_records"] > 0
    assert epoch["train_loss"] >= 0.0
    assert epoch["val_loss"] >= 0.0
