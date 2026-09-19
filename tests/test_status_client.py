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

    def test_invalidate_drops_record_whose_worktree_membership_changed(self):
        cache = status_client.StatusClientCache()
        root = Path("/tmp/newrepo")
        # Previously cached as non-versioned: empty worktree id.
        cache.update(
            [{"path": str(root), "worktree_id": "", "status": "error"}]
        )

        # The directory just became a Git worktree; the daemon reports a change
        # there under the new worktree id.
        removed = cache.invalidate(f"git:{root}", [root])

        self.assertEqual(removed, [str(root)])
        self.assertIsNone(cache.get(root))

    def test_invalidate_ignores_sibling_with_common_name_prefix(self):
        cache = status_client.StatusClientCache()
        root = Path("/tmp/repo")
        cache.update(
            [
                {"path": str(root / "dir"), "worktree_id": "w", "status": "ok"},
                {"path": str(root / "dir2"), "worktree_id": "w", "status": "ok"},
                {
                    "path": str(root / "dir" / "a.txt"),
                    "worktree_id": "w",
                    "status": "ok",
                },
                {
                    "path": str(root / "dir" / "a.txt.bak"),
                    "worktree_id": "w",
                    "status": "ok",
                },
            ]
        )

        removed = cache.invalidate("w", [root / "dir" / "a.txt"])

        self.assertEqual(removed, [str(root / "dir"), str(root / "dir" / "a.txt")])
        self.assertIsNotNone(cache.get(root / "dir2"))
        self.assertIsNotNone(cache.get(root / "dir" / "a.txt.bak"))

    def test_records_are_bounded_least_recently_used_first(self):
        cache = status_client.StatusClientCache(max_records=2)
        cache.update(
            [
                {"path": "/tmp/a", "status": "ok"},
                {"path": "/tmp/b", "status": "ok"},
            ]
        )
        # Reading a record makes it recently used.
        self.assertIsNotNone(cache.get("/tmp/a"))

        cache.update([{"path": "/tmp/c", "status": "ok"}])

        self.assertIsNone(cache.get("/tmp/b"))
        self.assertIsNotNone(cache.get("/tmp/a"))
        self.assertIsNotNone(cache.get("/tmp/c"))
        self.assertEqual(len(cache.records), 2)

    def test_max_records_must_be_positive(self):
        with self.assertRaises(ValueError):
            status_client.StatusClientCache(max_records=0)


class PathOverlapIndexTest(unittest.TestCase):
    def test_matches_equal_ancestor_and_descendant_paths(self):
        index = status_client.PathOverlapIndex(["/tmp/repo/dir/file.txt"])

        self.assertTrue(index)
        self.assertTrue(index.overlaps("/tmp/repo/dir/file.txt"))
        self.assertTrue(index.overlaps("/tmp/repo/dir"))
        self.assertTrue(index.overlaps("/tmp/repo"))
        self.assertTrue(index.overlaps("/"))

    def test_rejects_unrelated_and_name_prefix_paths(self):
        index = status_client.PathOverlapIndex(["/tmp/repo/dir/file.txt"])

        self.assertFalse(index.overlaps("/tmp/repo2"))
        self.assertFalse(index.overlaps("/tmp/repo/dir2/file.txt"))
        self.assertFalse(index.overlaps("/tmp/repo/dir/file.txt.bak"))
        self.assertFalse(index.overlaps("/tmp/other/dir/file.txt"))

    def test_directory_change_covers_descendants(self):
        index = status_client.PathOverlapIndex(["/tmp/repo/dir"])

        self.assertTrue(index.overlaps("/tmp/repo/dir/deep/nested.txt"))
        self.assertFalse(index.overlaps("/tmp/repo/other.txt"))

    def test_empty_index_is_falsy(self):
        index = status_client.PathOverlapIndex([])

        self.assertFalse(index)
        self.assertFalse(index.overlaps("/tmp/repo"))

    def test_paths_overlap_helper_normalizes_both_sides(self):
        self.assertTrue(
            status_client.paths_overlap(Path("/tmp/repo/dir"), "/tmp/repo/dir/x")
        )
        self.assertFalse(status_client.paths_overlap("/tmp/repo", "/tmp/repo2"))


if __name__ == "__main__":
    unittest.main()
