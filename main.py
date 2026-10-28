"""
Implement a class called TimedKeyValueStore that evolves through four levels of functionality, commonly seen in system design / coding interviews for databases and caches.

Level 1 — Basic CRUD

put(key, value): store a value for a key.
get(key): return the current value, or None if the key doesn't exist.
delete(key): remove a key. Return True if it existed, False otherwise.
Level 2 — Timestamped writes

put(key, value, timestamp): every write is tagged with a timestamp (an integer you pass in).
get(key): must return the value with the latest timestamp seen so far for that key, even if writes arrive out of order (e.g. a write with timestamp 5 arrives after one with timestamp 10 — the timestamp 10 value should still win).
Level 3 — TTL and historical lookups

put(key, value, timestamp, ttl=None): ttl is the number of time units after timestamp that the value remains valid. If ttl is None, the value never expires.
get(key, at_time): return the value that was active for key at at_time — i.e. the most recent write at or before at_time whose TTL (if any) has not expired by at_time. Return None if no valid value exists at that time.
Level 4 — Snapshot and restore

snapshot(): capture the entire current state of the store and return a snapshot id (any hashable value, e.g. an incrementing integer).
restore(snapshot_id): roll the store back to exactly the state it was in when that snapshot was taken. Subsequent operations continue normally from the restored state.
Work through the levels in order — each builds on the previous one. A starter class skeleton with method stubs is provided.

"""
import copy
from typing import Any, Optional, Hashable, NamedTuple
from collections import defaultdict
from sortedcontainers import SortedKeyList


class Item(NamedTuple):
    timestamp: int
    value: Any
    ttl: Optional[int] = None


def _timestamp(item: Item) -> int:
    return item.timestamp


def _new_items() -> SortedKeyList:
    return SortedKeyList(key=_timestamp)


def _copy_items(items: SortedKeyList) -> SortedKeyList:
    # Items are immutable and values are copied on put/get, so a shallow copy is enough.
    return SortedKeyList(items, key=_timestamp)


class TimedKeyValueStore:
    """An in-memory key-value store with timestamped writes, TTL expiration,
    and snapshot/restore support.

    Work through the levels in order:
      Level 1: put(key, value) / get(key) / delete(key)
      Level 2: put(key, value, timestamp) with out-of-order write handling
      Level 3: put(..., ttl=None) and get(key, at_time) historical lookups
      Level 4: snapshot() / restore(snapshot_id)

    Snapshots are copy-on-write: a snapshot saves a key's items only the first
    time that key changes after the snapshot was taken.
    """

    def __init__(self):
        self.values: defaultdict[str, SortedKeyList] = defaultdict(_new_items)
        # (key, snapshot id) -> index into keys_history of the key's state at that snapshot
        self.changed_keys: dict[tuple[str, Hashable], int] = {}
        # snapshot id -> keys changed since that snapshot
        self.version_history: dict[Hashable, set[str]] = {}
        self.latest_version = 0
        # Saved key states; None means the key did not exist.
        self.keys_history: list[Optional[SortedKeyList]] = []
        # key -> newest snapshot id that has already saved this key
        self.saved_through: dict[str, int] = {}

    def put(self, key: str, value: Any, timestamp: int = 0, ttl: Optional[int] = None) -> None:
        """Store `value` for `key` at `timestamp`, optionally expiring after `ttl` time units."""
        self.write_history(key)
        self.values[key].add(Item(timestamp=timestamp, value=copy.deepcopy(value), ttl=ttl))

    def get(self, key: str, at_time: Optional[int] = None) -> Optional[Any]:
        """Return the value active for `key` at `at_time`.

        If `at_time` is None, return the most up-to-date value.
        Returns None if no valid value exists.
        """
        if key not in self.values:
            return None
        if at_time is None:
            return copy.deepcopy(self.values[key][-1].value)

        # Start at the newest write with timestamp <= at_time and walk back.
        for i in range(self.values[key].bisect_key_right(at_time) - 1, -1, -1):
            item = self.values[key][i]
            if item.ttl is None or at_time < item.timestamp + item.ttl:
                return copy.deepcopy(item.value)
        return None

    def delete(self, key: str) -> bool:
        """Remove `key` entirely. Returns True if it existed, False otherwise."""
        if key not in self.values:
            return False
        self.write_history(key)
        del self.values[key]
        return True

    def snapshot(self) -> Hashable:
        """Capture the full current state and return a snapshot id."""
        latest = self.latest_version
        self.version_history[latest] = set()
        self.latest_version += 1
        return latest

    def restore(self, snapshot_id: Hashable) -> None:
        """Roll the store back to the state captured by `snapshot_id`."""
        if snapshot_id not in self.version_history:
            raise KeyError(f"Snapshot with id {snapshot_id} does not exist.")
        for key in self.version_history[snapshot_id]:
            saved = self.keys_history[self.changed_keys[(key, snapshot_id)]]
            # Record the current state so other snapshots can still be restored.
            self.write_history(key)
            if saved is None:
                self.values.pop(key, None)
            else:
                self.values[key] = _copy_items(saved)

    def write_history(self, key: str) -> None:
        """Save `key`'s current state for every snapshot that hasn't saved it yet.

        Each call saves the key into all existing snapshots, so the only ones
        still missing it are those taken after its last save.
        """
        start = self.saved_through.get(key, -1) + 1
        if start >= self.latest_version:
            return
        self.keys_history.append(_copy_items(self.values[key]) if key in self.values else None)
        index = len(self.keys_history) - 1
        for version_number in range(start, self.latest_version):
            self.version_history[version_number].add(key)
            self.changed_keys[(key, version_number)] = index
        self.saved_through[key] = self.latest_version - 1


if __name__ == "__main__":
    # Simple manual smoke test — feel free to modify while developing.
    db = TimedKeyValueStore()
    db.put("x", "a", timestamp=1)
    db.put("x", "b", timestamp=5, ttl=10)
    print(db.get("x", at_time=7))   # expect "b"
    print(db.get("x", at_time=20))  # expect "a"
    sid = db.snapshot()
    db.put("x", "c", timestamp=25)
    db.restore(sid)
    print(db.get("x", at_time=25))  # expect "a"

