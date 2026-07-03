from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from nemovcs import statusd
from nemovcs.backends.base import BackendStatusScan


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
        self.assertEqual(identity.backend_id, "git")
        self.assertEqual(identity.cache_key, f"git:{self.root}")

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
        changed: list[tuple[str, list[str]]] = []

        def scan(entry: statusd.WorktreeEntry) -> None:
            scans.append(entry.identity)
            entry.scanned = True

        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        core = statusd.StatusDaemonCore(
            cache,
            timer=timer,
            scan_func=scan,
            status_changed_callback=lambda worktree_id, paths: changed.append(
                (worktree_id, paths)
            ),
        )

        self.assertTrue(core.mark_stale(first.cache_key, [first.root / "a.txt"]))
        self.assertTrue(core.mark_stale(first.cache_key, [first.root / "b.txt"]))

        self.assertEqual(len(timer.scheduled), 1)
        self.assertTrue(entry.stale)
        self.assertEqual(entry.stale_paths, {"a.txt", "b.txt"})
        self.assertEqual(
            statusd.path_status(entry, first.root / "a.txt"),
            statusd.EmblemStatus.OK,
        )

        timer.fire_next()

        self.assertEqual(scans, [first])
        self.assertFalse(entry.stale)
        self.assertEqual(entry.stale_paths, set())
        self.assertEqual(core.changed_worktrees, [first.cache_key])
        self.assertEqual(
            changed,
            [
                (
                    first.cache_key,
                    [str(first.root / "a.txt"), str(first.root / "b.txt")],
                )
            ],
        )

    def test_seen_scans_without_status_changed_signal(self):
        changed: list[tuple[str, list[str]]] = []
        first = identity("one")
        cache = statusd.WorktreeCache()

        def scan(_entry: statusd.WorktreeEntry) -> None:
            _entry.scanned = True

        core = statusd.StatusDaemonCore(
            cache,
            scan_func=scan,
            status_changed_callback=lambda worktree_id, paths: changed.append(
                (worktree_id, paths)
            ),
        )

        with mock.patch("nemovcs.statusd.identify_worktree", return_value=first):
            self.assertEqual(core.seen([first.root]), [first.cache_key])

        self.assertEqual(changed, [])

    def test_seen_does_not_rescan_fresh_worktree(self):
        first = identity("one")
        cache = statusd.WorktreeCache()
        scans: list[statusd.WorktreeIdentity] = []

        def scan(_entry: statusd.WorktreeEntry) -> None:
            scans.append(_entry.identity)
            _entry.scanned = True

        core = statusd.StatusDaemonCore(cache, scan_func=scan)

        with mock.patch("nemovcs.statusd.identify_worktree", return_value=first):
            self.assertEqual(core.seen([first.root]), [first.cache_key])
            self.assertEqual(core.seen([first.root / "file.txt"]), [first.cache_key])

        self.assertEqual(scans, [first])

    def test_seen_rescans_stale_worktree(self):
        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        entry.stale = True
        scans: list[statusd.WorktreeIdentity] = []

        def scan(_entry: statusd.WorktreeEntry) -> None:
            scans.append(_entry.identity)
            _entry.scanned = True

        core = statusd.StatusDaemonCore(cache, scan_func=scan)

        with mock.patch("nemovcs.statusd.identify_worktree", return_value=first):
            self.assertEqual(core.seen([first.root / "file.txt"]), [first.cache_key])

        self.assertEqual(scans, [first])
        self.assertFalse(entry.stale)

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

    def test_scan_entry_reports_worktree_root_when_no_specific_path_changed(self):
        changed: list[tuple[str, list[str]]] = []
        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)

        def scan(_entry: statusd.WorktreeEntry) -> None:
            _entry.scanned = True

        core = statusd.StatusDaemonCore(
            cache,
            scan_func=scan,
            status_changed_callback=lambda worktree_id, paths: changed.append(
                (worktree_id, paths)
            ),
        )

        core.scan_entry(entry)

        self.assertEqual(changed, [(first.cache_key, [str(first.root)])])

    def test_status_record_uses_folder_aggregate_status(self):
        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        entry.statuses["dir/nested.txt"] = statusd.EmblemStatus.MODIFIED
        core = statusd.StatusDaemonCore(cache)

        with mock.patch("nemovcs.statusd.identify_worktree", return_value=first):
            record = core.status_record(first.root / "dir")

        self.assertEqual(record["backend"], "git")
        self.assertEqual(record["worktree_id"], first.cache_key)
        self.assertEqual(record["status"], statusd.EmblemStatus.MODIFIED)

    def test_cache_records_include_one_record_per_worktree(self):
        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        entry.statuses["src/app.py"] = statusd.EmblemStatus.MODIFIED
        entry.statuses["tmp/generated.txt"] = statusd.EmblemStatus.UNVERSIONED
        core = statusd.StatusDaemonCore(cache)

        records = core.cache_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["path"], str(first.root))
        self.assertEqual(records[0]["worktree_id"], first.cache_key)
        self.assertEqual(records[0]["status"], "modified")

    def test_cache_records_show_loading_for_unscanned_worktree(self):
        first = identity("one")
        cache = statusd.WorktreeCache()
        cache.touch(first)
        core = statusd.StatusDaemonCore(cache)

        records = core.cache_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["path"], str(first.root))
        self.assertEqual(records[0]["status"], "loading")

    def test_settings_record_reports_cache_size_and_debounce(self):
        cache = statusd.WorktreeCache(max_worktrees=7)
        core = statusd.StatusDaemonCore(cache, debounce_seconds=1.25)

        record = core.settings_record()

        self.assertEqual(record["max_worktrees"], "7")
        self.assertEqual(record["debounce_seconds"], "1.25")
        self.assertTrue(record["config_path"].endswith("nemovcs/settings.json"))

    def test_from_config_uses_persisted_statusd_settings(self):
        with mock.patch("nemovcs.statusd.config.load_statusd_settings") as load_settings:
            load_settings.return_value = statusd.config.StatusdSettings(
                max_worktrees=5,
                debounce_seconds=2.5,
            )

            core = statusd.StatusDaemonCore.from_config()

        self.assertEqual(core.cache.max_worktrees, 5)
        self.assertEqual(core.debounce_seconds, 2.5)

    def test_set_settings_saves_and_applies_statusd_settings(self):
        cache = statusd.WorktreeCache(max_worktrees=7)
        core = statusd.StatusDaemonCore(cache, debounce_seconds=1.25)

        with mock.patch("nemovcs.statusd.config.save_statusd_settings") as save_settings:
            record = core.set_settings(
                {
                    "max_worktrees": "3",
                    "debounce_seconds": "0.5",
                }
            )

        self.assertEqual(core.cache.max_worktrees, 3)
        self.assertEqual(core.debounce_seconds, 0.5)
        self.assertEqual(record["max_worktrees"], "3")
        self.assertEqual(record["debounce_seconds"], "0.5")
        save_settings.assert_called_once_with(
            statusd.config.StatusdSettings(max_worktrees=3, debounce_seconds=0.5)
        )

    def test_git_unversioned_file_aggregate_remains_unversioned(self):
        first = identity("one")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        entry.statuses["new.txt"] = statusd.EmblemStatus.UNVERSIONED

        self.assertEqual(
            statusd.aggregate_status(entry, first.root / "new.txt"),
            statusd.EmblemStatus.UNVERSIONED,
        )

    def test_svn_unversioned_file_aggregate_remains_unversioned(self):
        root = Path("/tmp/wc")
        svn = statusd.WorktreeIdentity(
            root=root,
            gitdir=root / ".svn",
            common_gitdir=root / ".svn",
            head_label="trunk",
            backend_id="svn",
        )
        cache = statusd.WorktreeCache()
        entry = cache.touch(svn)
        entry.scanned = True
        entry.statuses["new.txt"] = statusd.EmblemStatus.UNVERSIONED

        self.assertEqual(
            statusd.aggregate_status(entry, root / "new.txt"),
            statusd.EmblemStatus.UNVERSIONED,
        )

    def test_svn_parent_ignores_unversioned_descendants_for_aggregate(self):
        root = Path("/tmp/wc")
        svn = statusd.WorktreeIdentity(
            root=root,
            gitdir=root / ".svn",
            common_gitdir=root / ".svn",
            head_label="trunk",
            backend_id="svn",
        )
        cache = statusd.WorktreeCache()
        entry = cache.touch(svn)
        entry.scanned = True
        entry.statuses["new.txt"] = statusd.EmblemStatus.UNVERSIONED

        self.assertEqual(
            statusd.aggregate_status(entry, root),
            statusd.EmblemStatus.OK,
        )


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
            statusd.EmblemStatus.UNVERSIONED,
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

    def test_scan_reports_nested_untracked_files_individually(self):
        (self.root / "untracked-dir").mkdir()
        (self.root / "untracked-dir" / "nested.txt").write_text(
            "new\n",
            encoding="utf-8",
        )

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.path_status(self.entry, self.root / "untracked-dir" / "nested.txt"),
            statusd.EmblemStatus.UNVERSIONED,
        )
        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root / "untracked-dir"),
            statusd.EmblemStatus.UNVERSIONED,
        )

    def test_scan_reports_root_with_untracked_child_as_modified(self):
        (self.root / "untracked.txt").write_text("new\n", encoding="utf-8")

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root),
            statusd.EmblemStatus.MODIFIED,
        )

    def test_scan_reports_versioned_directory_with_untracked_child_as_modified(self):
        (self.root / "dir" / "untracked.txt").write_text("new\n", encoding="utf-8")

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root / "dir"),
            statusd.EmblemStatus.MODIFIED,
        )

    def test_scan_reports_empty_untracked_directory_as_unversioned(self):
        (self.root / "empty-untracked-dir").mkdir()

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.path_status(self.entry, self.root / "empty-untracked-dir"),
            statusd.EmblemStatus.UNVERSIONED,
        )
        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root / "empty-untracked-dir"),
            statusd.EmblemStatus.UNVERSIONED,
        )

    def test_scan_reports_ignored_file_without_dirtying_parent(self):
        (self.root / ".git" / "info" / "exclude").write_text(
            "ignored.bin\n",
            encoding="utf-8",
        )
        (self.root / "ignored.bin").write_text("ignored\n", encoding="utf-8")

        statusd.scan_worktree(self.entry)

        self.assertEqual(
            statusd.path_status(self.entry, self.root / "ignored.bin"),
            statusd.EmblemStatus.IGNORED,
        )
        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root / "ignored.bin"),
            statusd.EmblemStatus.IGNORED,
        )
        self.assertEqual(
            statusd.aggregate_status(self.entry, self.root),
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
        backend = mock.Mock()
        backend.scan_status.return_value = BackendStatusScan(
            ok=False,
            error="fatal: failed",
        )
        with mock.patch("nemovcs.statusd.backends.backend_by_id", return_value=backend):

            statusd.scan_worktree(failed)

        backend.scan_status.assert_called_once_with(self.root)
        self.assertTrue(failed.scanned)
        self.assertEqual(failed.error, "fatal: failed")
        self.assertEqual(
            statusd.path_status(failed, self.root / "tracked.txt"),
            statusd.EmblemStatus.ERROR,
        )

    def test_scan_records_error_for_unknown_backend(self):
        failed = statusd.WorktreeEntry(
            statusd.WorktreeIdentity(
                root=self.root,
                gitdir=self.root / ".git",
                common_gitdir=self.root / ".git",
                head_label="main",
                backend_id="svn",
            )
        )
        with mock.patch("nemovcs.statusd.backends.backend_by_id", return_value=None):
            statusd.scan_worktree(failed)

        self.assertTrue(failed.scanned)
        self.assertEqual(failed.error, "unknown backend: svn")

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
        self.assertIn("   backend: git", stdout)
        self.assertIn(f"   vcs-dir: {self.root / '.git'}", stdout)
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
        self.assertEqual(stderr, "not inside a versioned working tree\n")


if __name__ == "__main__":
    unittest.main()
