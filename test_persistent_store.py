"""Run the full test_main suite against PersistentKeyValueStore."""
import unittest

import test_main
from persistent_store import PersistentKeyValueStore


class TestLevel1Crud(test_main.TestLevel1Crud):
    make_store = PersistentKeyValueStore


class TestLevel2Timestamps(test_main.TestLevel2Timestamps):
    make_store = PersistentKeyValueStore


class TestLevel3TtlAndHistory(test_main.TestLevel3TtlAndHistory):
    make_store = PersistentKeyValueStore


class TestLevel4SnapshotRestore(test_main.TestLevel4SnapshotRestore):
    make_store = PersistentKeyValueStore


if __name__ == "__main__":
    unittest.main()
