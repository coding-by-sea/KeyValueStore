"""TimedKeyValueStore built on persistent (immutable) data structures.

Same interface as main.TimedKeyValueStore, different snapshot strategy.
The whole store is one immutable map: key -> immutable vector of Items sorted
by timestamp. Every write builds a new map that shares almost all of its
structure with the old one, so old versions stay intact for free:

  snapshot() saves a reference to the current map    -> O(1)
  restore()  points the store back at a saved map    -> O(1)
  put()      creates a new map version               -> O(log n) for in-order writes
"""

import copy
from bisect import bisect_right
from itertools import count
from typing import Any, Hashable, NamedTuple, Optional

from pyrsistent import PMap, PVector, pmap, pvector


class Item(NamedTuple):
    timestamp: int
    value: Any
    ttl: Optional[int] = None


def _timestamp(item: Item) -> int:
    return item.timestamp


class PersistentKeyValueStore:
    """In-memory key-value store with timestamped writes, TTL expiration,
    and O(1) snapshot/restore.

    Stored values are copied on put and get so callers can't change data that
    snapshots share.
    """

    def __init__(self):
        self._state: PMap[str, PVector[Item]] = pmap()
        self._snapshots: dict[Hashable, PMap[str, PVector[Item]]] = {}
        self._ids = count()

    def put(self, key: str, value: Any, timestamp: int = 0, ttl: Optional[int] = None) -> None:
        """Store `value` for `key` at `timestamp`, optionally expiring after `ttl` time units."""
        item = Item(timestamp=timestamp, value=copy.deepcopy(value), ttl=ttl)
        items: PVector[Item] = self._state.get(key, pvector())

        if not items or timestamp >= items[-1].timestamp:
            # Common case: newest write so far. Appending is O(log n).
            items = items.append(item)
        else:
            # Out-of-order write: insert after any items with the same timestamp
            # so the later write wins. Rebuilding the vector costs O(n).
            i = bisect_right(items, timestamp, key=_timestamp)
            items = items[:i].append(item).extend(items[i:])

        self._state = self._state.set(key, items)

    def get(self, key: str, at_time: Optional[int] = None) -> Optional[Any]:
        """Return the value active for `key` at `at_time`.

        If `at_time` is None, return the most up-to-date value.
        Returns None if no valid value exists.
        """
        items = self._state.get(key)
        if items is None:
            return None
        if at_time is None:
            return copy.deepcopy(items[-1].value)

        # Start at the newest write with timestamp <= at_time and walk back.
        for i in range(bisect_right(items, at_time, key=_timestamp) - 1, -1, -1):
            item = items[i]
            if item.ttl is None or at_time < item.timestamp + item.ttl:
                return copy.deepcopy(item.value)
        return None

    def delete(self, key: str) -> bool:
        """Remove `key` entirely. Returns True if it existed, False otherwise."""
        if key not in self._state:
            return False
        self._state = self._state.remove(key)
        return True

    def snapshot(self) -> Hashable:
        """Capture the full current state and return a snapshot id."""
        snapshot_id = next(self._ids)
        self._snapshots[snapshot_id] = self._state
        return snapshot_id

    def restore(self, snapshot_id: Hashable) -> None:
        """Roll the store back to the state captured by `snapshot_id`."""
        if snapshot_id not in self._snapshots:
            raise KeyError(f"Snapshot with id {snapshot_id} does not exist.")
        self._state = self._snapshots[snapshot_id]


if __name__ == "__main__":
    db = PersistentKeyValueStore()
    db.put("x", "a", timestamp=1)
    db.put("x", "b", timestamp=5, ttl=10)
    print(db.get("x", at_time=7))   # expect "b"
    print(db.get("x", at_time=20))  # expect "a"
    sid = db.snapshot()
    db.put("x", "c", timestamp=25)
    db.restore(sid)
    print(db.get("x", at_time=25))  # expect "a"
