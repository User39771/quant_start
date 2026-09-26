"""Small exact block-timestamp cache backed by SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Mapping


class TimestampConflictError(Exception):
    """Raised when one block number is associated with two timestamps."""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS block_timestamps ("
        "block_number INTEGER PRIMARY KEY, timestamp INTEGER NOT NULL)"
    )
    connection.commit()
    return connection


def lookup_timestamps(path: Path, blocks) -> dict[int, int]:
    unique = list(dict.fromkeys(int(block) for block in blocks))
    if not unique:
        return {}
    found: dict[int, int] = {}
    connection = _connect(path)
    try:
        for offset in range(0, len(unique), 900):
            batch = unique[offset : offset + 900]
            placeholders = ",".join("?" for _ in batch)
            found.update(
                (int(block), int(timestamp))
                for block, timestamp in connection.execute(
                    f"SELECT block_number, timestamp FROM block_timestamps WHERE block_number IN ({placeholders})",
                    batch,
                )
            )
    finally:
        connection.close()
    return found


def insert_exact_timestamps(path: Path, mapping: Mapping[int, int]) -> tuple[int, int]:
    values = {int(block): int(timestamp) for block, timestamp in mapping.items()}
    if any(block < 0 or timestamp <= 0 for block, timestamp in values.items()):
        raise ValueError("block numbers must be nonnegative and timestamps must be positive")
    if not values:
        return 0, 0
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = lookup_timestamps_in_connection(connection, values)
        conflicts = {
            block: (existing[block], timestamp)
            for block, timestamp in values.items()
            if block in existing and existing[block] != timestamp
        }
        if conflicts:
            block, pair = next(iter(conflicts.items()))
            raise TimestampConflictError(
                f"timestamp conflict for block {block}: existing={pair[0]} incoming={pair[1]}"
            )
        new_rows = [(block, timestamp) for block, timestamp in values.items() if block not in existing]
        connection.executemany(
            "INSERT INTO block_timestamps (block_number, timestamp) VALUES (?, ?)",
            new_rows,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return len(new_rows), len(values) - len(new_rows)


def lookup_timestamps_in_connection(
    connection: sqlite3.Connection, blocks
) -> dict[int, int]:
    unique = list(dict.fromkeys(int(block) for block in blocks))
    found: dict[int, int] = {}
    for offset in range(0, len(unique), 900):
        batch = unique[offset : offset + 900]
        placeholders = ",".join("?" for _ in batch)
        found.update(
            (int(block), int(timestamp))
            for block, timestamp in connection.execute(
                f"SELECT block_number, timestamp FROM block_timestamps WHERE block_number IN ({placeholders})",
                batch,
            )
        )
    return found
