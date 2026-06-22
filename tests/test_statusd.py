from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from nemovcs import statusd


def have_git() -> bool:
    return shutil.which("git") is not None


def identity(name: str) -> statusd.WorktreeIdentity:
    root = Path("/tmp") / name
    return statusd.WorktreeIdentity(
        root=root,
        gitdir=root / ".git",
        common_gitdir=root / ".git",
        head_label="main",
    )


class FakeTimer:
    def __init__(self):
        self.scheduled: list[tuple[float, object]] = []

    def __call__(self, delay_seconds, callback):
        self.scheduled.append((delay_seconds, callback))
        return callback

    def fire_next(self):
        _delay, callback = self.scheduled.pop(0)
        callback()


@unittest.skipUnless(have_git(), "git executable is required")
class WorktreeIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "main"
        self.root.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "NemoVCS Test"],
            cwd=self.root,
            check=True,
        )
        (self.root / "tracked.txt").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_normal_repository_identity(self):
        identity = statusd.identify_worktree(self.root)

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.root, self.root)
        self.assertEqual(identity.gitdir, self.root / ".git")
        self.assertEqual(identity.common_gitdir, self.root / ".git")
        self.assertEqual(identity.head_label, "main")

    def test_child_path_resolves_to_same_identity(self):
        child = self.root / "src"
        child.mkdir()

        root_identity = statusd.identify_worktree(self.root)
        child_identity = statusd.identify_worktree(child)

        self.assertEqual(child_identity, root_identity)

    def test_linked_worktree_has_distinct_gitdir_and_shared_common_gitdir(self):
        linked = Path(self.tmp.name) / "linked"
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature", str(linked)],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        main_identity = statusd.identify_worktree(self.root)
        linked_identity = statusd.identify_worktree(linked)

        self.assertIsNotNone(main_identity)
        self.assertIsNotNone(linked_identity)
        assert main_identity is not None
        assert linked_identity is not None
        self.assertEqual(linked_identity.root, linked)
        self.assertEqual(linked_identity.head_label, "feature")
        self.assertNotEqual(linked_identity.root, main_identity.root)
        self.assertNotEqual(linked_identity.gitdir, main_identity.gitdir)
        self.assertEqual(linked_identity.common_gitdir, main_identity.common_gitdir)

    def test_non_repository_path_returns_none(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()

        self.assertIsNone(statusd.identify_worktree(outside))


class WorktreeCacheTest(unittest.TestCase):
    def test_seen_worktree_inserts_entry(self):
        cache = statusd.WorktreeCache(max_worktrees=2)
        first = identity("one")

        entry = cache.touch(first)

        self.assertEqual(entry.identity, first)
        self.assertEqual(cache.identities(), [first])
        self.assertIn(first, cache)

    def test_seen_existing_worktree_moves_it_to_front(self):
        cache = statusd.WorktreeCache(max_worktrees=3)
        first = identity("one")
        second = identity("two")
        third = identity("three")

        cache.touch(first)
        cache.touch(second)
        cache.touch(third)
        cache.touch(first)

        self.assertEqual(cache.identities(), [first, third, second])

    def test_default_limit_evicts_oldest_thirteenth_worktree(self):
        evicted: list[statusd.WorktreeIdentity] = []

        class TrackingCache(statusd.WorktreeCache):
            def on_evict(self, entry: statusd.WorktreeEntry) -> None:
                evicted.append(entry.identity)

        cache = TrackingCache()
        identities = [identity(f"repo-{idx}") for idx in range(13)]

        for item in identities:
            entry = cache.touch(item)
        entry.statuses["tracked.txt"] = statusd.EmblemStatus.MODIFIED

        self.assertEqual(len(cache), statusd.DEFAULT_MAX_WORKTREES)
        self.assertEqual(evicted, [identities[0]])
        self.assertNotIn(identities[0], cache)
        self.assertEqual(cache.identities()[0], identities[-1])

    def test_invalid_cache_size_is_rejected(self):
        with self.assertRaises(ValueError):
            statusd.WorktreeCache(max_worktrees=0)


class StatusDaemonSchedulerTest(unittest.TestCase):
    def test_mark_stale_schedules_one_debounced_scan(self):
        timer = FakeTimer()
        scans: list[statusd.WorktreeIdentity] = []

        def scan(entry: statusd.WorktreeEntry) -> None:
            scans.append(entry.identity)
            entry.scanned = True

        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        core = statusd.StatusDaemonCore(cache, timer=timer, scan_func=scan)

        self.assertTrue(core.mark_stale(first.cache_key, [first.root / "a.txt"]))
        self.assertTrue(core.mark_stale(first.cache_key, [first.root / "b.txt"]))

        self.assertEqual(len(timer.scheduled), 1)
        self.assertTrue(entry.stale)
        self.assertEqual(entry.stale_paths, {"a.txt", "b.txt"})
        self.assertEqual(
            statusd.path_status(entry, first.root / "a.txt"),
            statusd.EmblemStatus.STALE,
        )

        timer.fire_next()

        self.assertEqual(scans, [first])
        self.assertFalse(entry.stale)
        self.assertEqual(entry.stale_paths, set())
        self.assertEqual(core.changed_worktrees, [first.cache_key])

    def test_mark_stale_for_unknown_worktree_returns_false(self):
        core = statusd.StatusDaemonCore(timer=FakeTimer())

        self.assertFalse(core.mark_stale("/tmp/missing"))

    def test_mark_stale_during_scan_requests_rescan(self):
        timer = FakeTimer()
        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        holder: dict[str, statusd.StatusDaemonCore] = {}

        def scan(_entry: statusd.WorktreeEntry) -> None:
            _entry.scanned = True
            holder["core"].mark_stale(first.cache_key, [first.root / "changed.txt"])

        core = statusd.StatusDaemonCore(cache, timer=timer, scan_func=scan)
        holder["core"] = core

        core.scan_entry(entry)

        self.assertFalse(entry.rescan_needed)
        self.assertTrue(entry.scan_scheduled)
        self.assertEqual(len(timer.scheduled), 1)


@unittest.skipUnless(have_git(), "git executable is required")
class WorktreeCacheIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "main"
        self.root.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "NemoVCS Test"],
            cwd=self.root,
            check=True,
        )
        (self.root / "tracked.txt").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_seen_ignores_non_repository_paths(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        cache = statusd.WorktreeCache()

        seen = cache.seen([outside])

        self.assertEqual(seen, [])
        self.assertEqual(len(cache), 0)

    def test_seen_linked_worktrees_as_separate_entries(self):
        linked = Path(self.tmp.name) / "linked"
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature", str(linked)],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        cache = statusd.WorktreeCache()

        seen = cache.seen([self.root, linked])

        self.assertEqual(len(seen), 2)
        self.assertEqual(len(cache), 2)
        self.assertEqual(cache.identities(), [seen[1], seen[0]])
        self.assertNotEqual(seen[0].root, seen[1].root)
        self.assertNotEqual(seen[0].gitdir, seen[1].gitdir)
        self.assertEqual(seen[0].common_gitdir, seen[1].common_gitdir)


@unittest.skipUnless(have_git(), "git executable is required")
class WorktreeScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "main"
        self.root.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "NemoVCS Test"],
            cwd=self.root,
            check=True,
        )
        (self.root / "tracked.txt").write_text("initial\n", encoding="utf-8")
        (self.root / "dir").mkdir()
        (self.root / "dir" / "clean.txt").write_text("clean\n", encoding="utf-8")
        (self.root / "dir" / "nested.txt").write_text("nested\n", encoding="utf-8")
        (self.root / "deleted.txt").write_text("delete me\n", encoding="utf-8")
        (self.root / "rename-old.txt").write_text("rename me\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        identity = statusd.identify_worktree(self.root)
        assert identity is not None
        self.entry = statusd.WorktreeEntry(identity)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_maps_changed_paths_to_primary_emblem_statuses(self):
        (self.root / "tracked.txt").write_text("modified\n", encoding="utf-8")
        (self.root / "untracked.txt").write_text("new\n", encoding="utf-8")
        (self.root / "deleted.txt").unlink()
        subprocess.run(
            ["git", "mv", "rename-old.txt", "rename-new.txt"],
            cwd=self.root,
            check=True,
        )

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.path_status(self.entry, self.root / "tracked.txt"),
            statusd.EmblemStatus.MODIFIED,
        )
        self.assertEqual(
            statusd.path_status(self.entry, self.root / "untracked.txt"),
            statusd.EmblemStatus.MODIFIED,
        )
        self.assertEqual(
            statusd.path_status(self.entry, self.root / "deleted.txt"),
            statusd.EmblemStatus.MODIFIED,
        )
        self.assertEqual(
            statusd.path_status(self.entry, self.root / "rename-new.txt"),
            statusd.EmblemStatus.MODIFIED,
        )
        self.assertEqual(
            statusd.path_status(self.entry, self.root / "rename-old.txt"),
            statusd.EmblemStatus.MODIFIED,
        )
        self.assertEqual(
            statusd.path_status(self.entry, self.root / "dir" / "clean.txt"),
            statusd.EmblemStatus.OK,
        )

    def test_conflict_maps_to_conflicted_and_dominates_folder_aggregate(self):
        subprocess.run(
            ["git", "checkout", "-b", "other"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        (self.root / "dir" / "nested.txt").write_text("other\n", encoding="utf-8")
        subprocess.run(
            ["git", "commit", "-am", "other"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        (self.root / "dir" / "nested.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(
            ["git", "commit", "-am", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "merge", "other"],
            cwd=self.root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.path_status(self.entry, self.root / "dir" / "nested.txt"),
            statusd.EmblemStatus.CONFLICTED,
        )
        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root / "dir"),
            statusd.EmblemStatus.CONFLICTED,
        )
        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root),
            statusd.EmblemStatus.CONFLICTED,
        )

    def test_folder_aggregate_reports_modified_descendant(self):
        (self.root / "dir" / "nested.txt").write_text("modified\n", encoding="utf-8")

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root / "dir"),
            statusd.EmblemStatus.MODIFIED,
        )
        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root),
            statusd.EmblemStatus.MODIFIED,
        )

    def test_unscanned_entry_reports_loading(self):
        self.assertEqual(
            statusd.path_status(self.entry, self.root / "tracked.txt"),
            statusd.EmblemStatus.LOADING,
        )

    def test_failed_scan_records_error(self):
        failed = statusd.WorktreeEntry(self.entry.identity)
        with mock.patch("nemovcs.statusd.git.run_git") as run_git:
            run_git.return_value = statusd.git.GitResult(
                ("git",),
                self.root,
                128,
                "",
                "fatal: failed\n",
            )

            statusd.scan_worktree(failed)

        self.assertTrue(failed.scanned)
        self.assertEqual(failed.error, "fatal: failed")
        self.assertEqual(
            statusd.path_status(failed, self.root / "tracked.txt"),
            statusd.EmblemStatus.ERROR,
        )

    def test_linked_worktree_scan_updates_only_linked_entry(self):
        linked = Path(self.tmp.name) / "linked"
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature", str(linked)],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        linked_identity = statusd.identify_worktree(linked)
        assert linked_identity is not None
        linked_entry = statusd.WorktreeEntry(linked_identity)
        (linked / "tracked.txt").write_text("linked change\n", encoding="utf-8")

        statusd.scan_worktree(linked_entry)
        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.path_status(linked_entry, linked / "tracked.txt"),
            statusd.EmblemStatus.MODIFIED,
        )
        self.assertEqual(
            statusd.path_status(self.entry, self.root / "tracked.txt"),
            statusd.EmblemStatus.OK,
        )

    def test_format_cache_probe_prints_identity_and_path_status(self):
        (self.root / "tracked.txt").write_text("modified\n", encoding="utf-8")

        exit_code, stdout, stderr = statusd.format_cache_probe(
            [self.root / "tracked.txt"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Cache:\n1. ", stdout)
        self.assertIn(f"   gitdir: {self.root / '.git'}", stdout)
        self.assertIn("   head: main", stdout)
        self.assertIn("Paths:", stdout)
        self.assertIn(
            f"{self.root / 'tracked.txt'}: {statusd.EmblemStatus.MODIFIED}",
            stdout,
        )

    def test_format_cache_probe_reports_non_repository_paths(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()

        exit_code, stdout, stderr = statusd.format_cache_probe([outside])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "not inside a Git working tree\n")


if __name__ == "__main__":
    unittest.main()
