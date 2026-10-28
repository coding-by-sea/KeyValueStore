import unittest

from main import TimedKeyValueStore


class TestLevel1Crud(unittest.TestCase):
    make_store = TimedKeyValueStore

    def setUp(self):
        self.db = self.make_store()

    def test_get_missing_key_returns_none(self):
        self.assertIsNone(self.db.get("missing"))

    def test_put_then_get(self):
        self.db.put("k", "a")
        self.assertEqual(self.db.get("k"), "a")

    def test_overwrite_without_timestamp_keeps_last_write(self):
        self.db.put("k", "a")
        self.db.put("k", "b")
        self.assertEqual(self.db.get("k"), "b")

    def test_overwrite_without_timestamp_at_time_zero(self):
        # All Level 1 writes default to timestamp 0, so the last one should win.
        self.db.put("k", "a")
        self.db.put("k", "b")
        self.assertEqual(self.db.get("k", at_time=0), "b")

    def test_delete_existing_key(self):
        self.db.put("k", "a")
        self.assertTrue(self.db.delete("k"))
        self.assertIsNone(self.db.get("k"))

    def test_delete_missing_key(self):
        self.assertFalse(self.db.delete("missing"))

    def test_get_missing_key_does_not_create_it(self):
        self.db.get("ghost")
        self.assertFalse(self.db.delete("ghost"))


class TestLevel2Timestamps(unittest.TestCase):
    make_store = TimedKeyValueStore

    def setUp(self):
        self.db = self.make_store()

    def test_out_of_order_writes_latest_timestamp_wins(self):
        self.db.put("k", "new", timestamp=10)
        self.db.put("k", "old", timestamp=5)
        self.assertEqual(self.db.get("k"), "new")

    def test_same_timestamp_last_write_wins(self):
        self.db.put("k", "a", timestamp=5)
        self.db.put("k", "b", timestamp=5)
        self.assertEqual(self.db.get("k"), "b")
        self.assertEqual(self.db.get("k", at_time=5), "b")


class TestLevel3TtlAndHistory(unittest.TestCase):
    make_store = TimedKeyValueStore

    def setUp(self):
        self.db = self.make_store()

    def test_get_before_first_write_returns_none(self):
        self.db.put("k", "a", timestamp=5)
        self.assertIsNone(self.db.get("k", at_time=4))

    def test_exact_timestamp_match(self):
        self.db.put("k", "a", timestamp=5)
        self.assertEqual(self.db.get("k", at_time=5), "a")

    def test_historical_lookup_between_writes(self):
        self.db.put("k", "a", timestamp=1)
        self.db.put("k", "b", timestamp=10)
        self.assertEqual(self.db.get("k", at_time=5), "a")
        self.assertEqual(self.db.get("k", at_time=15), "b")

    def test_no_ttl_never_expires(self):
        self.db.put("k", "a", timestamp=1)
        self.assertEqual(self.db.get("k", at_time=1_000_000), "a")

    def test_value_valid_within_ttl(self):
        self.db.put("k", "a", timestamp=5, ttl=10)
        self.assertEqual(self.db.get("k", at_time=14), "a")

    def test_value_expires_at_timestamp_plus_ttl(self):
        # Valid window is [timestamp, timestamp + ttl).
        self.db.put("k", "a", timestamp=5, ttl=10)
        self.assertIsNone(self.db.get("k", at_time=15))

    def test_zero_ttl_is_never_valid(self):
        self.db.put("k", "a", timestamp=5, ttl=0)
        self.assertIsNone(self.db.get("k", at_time=5))

    def test_expired_value_falls_back_to_older_live_value(self):
        self.db.put("x", "a", timestamp=1)
        self.db.put("x", "b", timestamp=5, ttl=10)
        self.assertEqual(self.db.get("x", at_time=7), "b")
        self.assertEqual(self.db.get("x", at_time=20), "a")

    def test_all_values_expired_returns_none(self):
        self.db.put("k", "a", timestamp=1, ttl=2)
        self.db.put("k", "b", timestamp=5, ttl=2)
        self.assertIsNone(self.db.get("k", at_time=10))


class TestLevel4SnapshotRestore(unittest.TestCase):
    make_store = TimedKeyValueStore

    def setUp(self):
        self.db = self.make_store()

    def test_snapshot_returns_hashable_id(self):
        sid = self.db.snapshot()
        self.assertIsNotNone(sid)
        hash(sid)

    def test_snapshot_ids_are_unique(self):
        self.assertNotEqual(self.db.snapshot(), self.db.snapshot())

    def test_restore_undoes_later_put(self):
        self.db.put("x", "a", timestamp=1)
        sid = self.db.snapshot()
        self.db.put("x", "c", timestamp=25)
        self.db.restore(sid)
        self.assertEqual(self.db.get("x", at_time=25), "a")
        self.assertEqual(self.db.get("x"), "a")

    def test_restore_removes_keys_added_after_snapshot(self):
        sid = self.db.snapshot()
        self.db.put("new", "v", timestamp=1)
        self.db.restore(sid)
        self.assertIsNone(self.db.get("new"))

    def test_restore_brings_back_deleted_key_with_history(self):
        self.db.put("k", "a", timestamp=1)
        self.db.put("k", "b", timestamp=5)
        sid = self.db.snapshot()
        self.db.delete("k")
        self.db.restore(sid)
        self.assertEqual(self.db.get("k", at_time=3), "a")
        self.assertEqual(self.db.get("k"), "b")

    def test_restore_same_snapshot_twice(self):
        self.db.put("k", "a", timestamp=1)
        sid = self.db.snapshot()
        self.db.restore(sid)
        self.db.put("k", "b", timestamp=2)
        self.db.restore(sid)
        self.assertEqual(self.db.get("k"), "a")

    def test_restore_keeps_later_snapshots(self):
        self.db.put("k", "a", timestamp=1)
        sid_a = self.db.snapshot()
        self.db.put("k", "b", timestamp=2)
        sid_b = self.db.snapshot()
        self.db.restore(sid_a)
        self.assertEqual(self.db.get("k"), "a")
        self.db.restore(sid_b)
        self.assertEqual(self.db.get("k"), "b")

    def test_operations_continue_after_restore(self):
        sid = self.db.snapshot()
        self.db.restore(sid)
        self.db.put("k", "a", timestamp=1)
        self.assertEqual(self.db.get("k"), "a")
        self.assertTrue(self.db.delete("k"))

    def test_snapshot_not_affected_by_mutating_stored_value(self):
        data = {"n": 1}
        self.db.put("k", data, timestamp=1)
        sid = self.db.snapshot()
        data["n"] = 2
        self.db.restore(sid)
        self.assertEqual(self.db.get("k"), {"n": 1})

    def test_restore_twice_with_writes_in_between(self):
        self.db.put("k", "a", timestamp=1)
        sid = self.db.snapshot()
        self.db.put("k", "b", timestamp=2)
        self.db.restore(sid)
        self.db.put("k", "c", timestamp=3)
        self.db.restore(sid)
        self.assertEqual(self.db.get("k"), "a")

    def test_snapshots_sharing_saved_state_stay_independent(self):
        self.db.put("k", "a", timestamp=1)
        sid_a = self.db.snapshot()
        sid_b = self.db.snapshot()
        self.db.put("k", "b", timestamp=2)
        self.db.restore(sid_a)
        self.db.put("k", "c", timestamp=3)
        self.db.restore(sid_b)
        self.assertEqual(self.db.get("k"), "a")

    def test_snapshot_not_affected_by_mutating_returned_value(self):
        self.db.put("k", {"n": 1}, timestamp=1)
        sid = self.db.snapshot()
        self.db.get("k")["n"] = 2
        self.db.restore(sid)
        self.assertEqual(self.db.get("k"), {"n": 1})

    def test_restore_after_key_added_then_deleted(self):
        sid = self.db.snapshot()
        self.db.put("k", "a", timestamp=1)
        self.db.delete("k")
        self.db.restore(sid)
        self.assertIsNone(self.db.get("k"))

    def test_restore_unknown_id_raises(self):
        with self.assertRaises(KeyError):
            self.db.restore("nope")


if __name__ == "__main__":
    unittest.main()
