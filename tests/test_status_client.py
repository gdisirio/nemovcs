from pathlib import Path
import unittest

from nemovcs import status_client


class StatusClientCacheTest(unittest.TestCase):
    def test_refresh_calls_daemon_methods_and_caches_records(self):
        cache = status_client.StatusClientCache()
        seen_calls = []
        get_status_calls = []
        root = Path("/tmp/repo")

        def seen(paths):
            seen_calls.append(list(paths))
            return [str(root)]

        def get_status(paths):
            get_status_calls.append(list(paths))
            return [
                {
                    "path": str(root / "tracked.txt"),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "modified",
                }
            ]

        records = cache.refresh([root / "tracked.txt"], seen, get_status)

        self.assertEqual(seen_calls, [[str(root / "tracked.txt")]])
        self.assertEqual(get_status_calls, [[str(root / "tracked.txt")]])
        self.assertEqual(records[0]["status"], "modified")
        self.assertEqual(cache.get(root / "tracked.txt")["status"], "modified")

    def test_invalidate_removes_matching_worktree_records_only(self):
        cache = status_client.StatusClientCache()
        root = Path("/tmp/repo")
        other = Path("/tmp/other")
        cache.update(
            [
                {
                    "path": str(root / "tracked.txt"),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "modified",
                },
                {
                    "path": str(other / "tracked.txt"),
                    "backend": "git",
                    "worktree_id": f"git:{other}",
                    "status": "modified",
                },
            ]
        )

        removed = cache.invalidate(f"git:{root}", [root / "tracked.txt"])

        self.assertEqual(removed, [str(root / "tracked.txt")])
        self.assertIsNone(cache.get(root / "tracked.txt"))
        self.assertIsNotNone(cache.get(other / "tracked.txt"))

    def test_invalidate_keeps_same_root_from_other_backend(self):
        cache = status_client.StatusClientCache()
        root = Path("/tmp/repo")
        git_path = root / "git.txt"
        svn_path = root / "svn.txt"
        cache.update(
            [
                {
                    "path": str(git_path),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "modified",
                },
                {
                    "path": str(svn_path),
                    "backend": "svn",
                    "worktree_id": f"svn:{root}",
                    "status": "modified",
                },
            ]
        )

        removed = cache.invalidate(f"git:{root}", [])

        self.assertEqual(removed, [str(git_path)])
        self.assertIsNone(cache.get(git_path))
        self.assertIsNotNone(cache.get(svn_path))

    def test_invalidate_child_path_also_removes_parent_folder_aggregate(self):
        cache = status_client.StatusClientCache()
        root = Path("/tmp/repo")
        cache.update(
            [
                {
                    "path": str(root / "dir"),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "ok",
                },
                {
                    "path": str(root / "dir" / "nested.txt"),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "ok",
                },
                {
                    "path": str(root / "unrelated.txt"),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "ok",
                },
            ]
        )

        removed = cache.invalidate(f"git:{root}", [root / "dir" / "nested.txt"])

        self.assertEqual(
            removed,
            [str(root / "dir"), str(root / "dir" / "nested.txt")],
        )
        self.assertIsNotNone(cache.get(root / "unrelated.txt"))

    def test_empty_changed_paths_invalidates_whole_worktree(self):
        cache = status_client.StatusClientCache()
        root = Path("/tmp/repo")
        cache.update(
            [
                {
                    "path": str(root / "a.txt"),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "ok",
                },
                {
                    "path": str(root / "b.txt"),
                    "backend": "git",
                    "worktree_id": f"git:{root}",
                    "status": "ok",
                },
            ]
        )

        removed = cache.invalidate(f"git:{root}", [])

        self.assertEqual(removed, [str(root / "a.txt"), str(root / "b.txt")])


if __name__ == "__main__":
    unittest.main()
