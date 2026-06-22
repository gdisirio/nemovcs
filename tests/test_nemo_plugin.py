from pathlib import Path
import unittest

from nemovcs import nemo_plugin


class FakeLocation:
    def __init__(self, path):
        self.path = path

    def get_path(self):
        return self.path


class FakeItem:
    def __init__(self, path, uri_scheme="file"):
        self.path = path
        self.uri_scheme = uri_scheme
        self.emblems = []

    def get_uri_scheme(self):
        return self.uri_scheme

    def get_location(self):
        return FakeLocation(self.path)

    def add_emblem(self, emblem):
        self.emblems.append(emblem)


class NemoVCSInfoProviderCoreTest(unittest.TestCase):
    def test_file_item_path_resolves_absolute_path(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        item = FakeItem("/tmp/repo/tracked.txt")

        self.assertEqual(core.item_path(item), "/tmp/repo/tracked.txt")

    def test_non_file_item_is_ignored(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        item = FakeItem("/tmp/repo/tracked.txt", uri_scheme="trash")

        self.assertIsNone(core.update_item(item))

    def test_update_item_refreshes_status_and_adds_modified_emblem(self):
        seen_calls = []
        get_status_calls = []

        def seen(paths):
            seen_calls.append(list(paths))
            return ["/tmp/repo"]

        def get_status(paths):
            get_status_calls.append(list(paths))
            return [
                {
                    "path": "/tmp/repo/tracked.txt",
                    "worktree_id": "/tmp/repo",
                    "status": "modified",
                }
            ]

        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=seen,
            get_status=get_status,
        )
        item = FakeItem("/tmp/repo/tracked.txt")

        record = core.update_item(item)

        self.assertEqual(record["status"], "modified")
        self.assertEqual(seen_calls, [["/tmp/repo/tracked.txt"]])
        self.assertEqual(get_status_calls, [["/tmp/repo/tracked.txt"]])
        self.assertEqual(item.emblems, ["rabbitvcs-modified"])
        self.assertEqual(
            core.cache.get(Path("/tmp/repo/tracked.txt"))["status"],
            "modified",
        )

    def test_conflicted_status_adds_conflict_emblem(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: ["/tmp/repo"],
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/conflict.txt",
                    "worktree_id": "/tmp/repo",
                    "status": "conflicted",
                }
            ],
        )
        item = FakeItem("/tmp/repo/conflict.txt")

        core.update_item(item)

        self.assertEqual(item.emblems, ["rabbitvcs-conflicted"])

    def test_ok_status_does_not_add_emblem(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: ["/tmp/repo"],
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/tracked.txt",
                    "worktree_id": "/tmp/repo",
                    "status": "ok",
                }
            ],
        )
        item = FakeItem("/tmp/repo/tracked.txt")

        core.update_item(item)

        self.assertEqual(item.emblems, [])

    def test_primary_emblem_maps_only_visible_statuses(self):
        self.assertEqual(nemo_plugin.primary_emblem("modified"), "rabbitvcs-modified")
        self.assertEqual(
            nemo_plugin.primary_emblem("conflicted"),
            "rabbitvcs-conflicted",
        )
        self.assertIsNone(nemo_plugin.primary_emblem("ok"))
        self.assertIsNone(nemo_plugin.primary_emblem("loading"))
        self.assertIsNone(nemo_plugin.primary_emblem("stale"))
        self.assertIsNone(nemo_plugin.primary_emblem("error"))

    def test_daemon_error_is_recorded_and_does_not_escape(self):
        def seen(_paths):
            raise RuntimeError("no daemon")

        core = nemo_plugin.NemoVCSInfoProviderCore(seen=seen, get_status=lambda _: [])

        self.assertIsNone(core.update_path("/tmp/repo/tracked.txt"))
        self.assertEqual(core.last_error, "no daemon")


if __name__ == "__main__":
    unittest.main()
