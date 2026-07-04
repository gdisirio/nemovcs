from pathlib import Path
import unittest

from nemovcs import statusd
from nemovcs import statusd_monitor


def identity(name: str) -> statusd.WorktreeIdentity:
    root = Path("/tmp") / name
    return statusd.WorktreeIdentity(
        root=root,
        gitdir=root / ".git",
        common_gitdir=root / ".git",
        head_label="main",
    )


class FakeHandle:
    def __init__(self, path, callback):
        self.path = path
        self.callback = callback
        self.canceled = False

    def cancel(self):
        self.canceled = True

    def emit(self, path):
        self.callback(path)


class FakeMonitorFactory:
    def __init__(self):
        self.handles = []

    def __call__(self, path, callback):
        handle = FakeHandle(path, callback)
        self.handles.append(handle)
        return handle


class FakeTimer:
    def __init__(self):
        self.scheduled = []

    def __call__(self, delay_seconds, callback):
        self.scheduled.append((delay_seconds, callback))
        return callback


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class WorktreeMonitorManagerTest(unittest.TestCase):
    def test_monitor_paths_include_worktree_and_git_metadata(self):
        first = identity("repo")

        paths = statusd_monitor.monitor_paths(first)

        self.assertEqual(
            paths,
            [
                first.root,
                first.gitdir,
                first.gitdir / "index",
                first.gitdir / "HEAD",
                first.common_gitdir / "refs",
                first.common_gitdir / "refs" / "heads",
                first.common_gitdir / "refs" / "tags",
                first.common_gitdir / "packed-refs",
            ],
        )

    def test_linked_worktree_paths_use_linked_gitdir_and_common_gitdir(self):
        root = Path("/tmp/main")
        linked = statusd.WorktreeIdentity(
            root=Path("/tmp/linked"),
            gitdir=root / ".git" / "worktrees" / "linked",
            common_gitdir=root / ".git",
            head_label="feature",
        )

        paths = statusd_monitor.monitor_paths(linked)

        self.assertIn(linked.root, paths)
        self.assertIn(linked.gitdir, paths)
        self.assertIn(linked.common_gitdir, paths)
        self.assertIn(linked.gitdir / "index", paths)
        self.assertIn(linked.gitdir / "HEAD", paths)
        self.assertIn(linked.common_gitdir / "refs", paths)
        self.assertIn(linked.common_gitdir / "refs" / "heads", paths)
        self.assertIn(linked.common_gitdir / "refs" / "tags", paths)

    def test_svn_paths_watch_worktree_and_wc_database(self):
        root = Path("/tmp/svn")
        svn = statusd.WorktreeIdentity(
            root=root,
            gitdir=root / ".svn",
            common_gitdir=root / ".svn",
            head_label="r1",
            backend_id="svn",
        )

        self.assertEqual(
            statusd_monitor.monitor_paths(svn),
            [root, root / ".svn" / "wc.db"],
        )

    def test_ensure_starts_monitors_once(self):
        factory = FakeMonitorFactory()
        core = statusd.StatusDaemonCore(timer=FakeTimer())
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        first = identity("repo")
        entry = statusd.WorktreeEntry(first)

        manager.ensure(entry)
        manager.ensure(entry)

        self.assertEqual(len(factory.handles), len(statusd_monitor.monitor_paths(first)))
        self.assertIn(first.cache_key, manager.monitors)

    def test_monitor_event_marks_worktree_stale(self):
        timer = FakeTimer()
        factory = FakeMonitorFactory()
        first = identity("repo")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        core = statusd.StatusDaemonCore(cache, timer=timer)
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        core.set_monitor_manager(manager)
        manager.ensure(entry)

        factory.handles[0].emit(first.root / "changed.txt")

        self.assertTrue(entry.stale)
        self.assertEqual(entry.stale_paths, {"changed.txt"})
        self.assertEqual(len(timer.scheduled), 1)

    def test_git_metadata_event_marks_whole_worktree_stale(self):
        timer = FakeTimer()
        factory = FakeMonitorFactory()
        first = identity("repo")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        core = statusd.StatusDaemonCore(cache, timer=timer)
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        core.set_monitor_manager(manager)
        manager.ensure(entry)

        factory.handles[1].emit(first.gitdir / "index.lock")

        self.assertTrue(entry.stale)
        self.assertEqual(entry.stale_paths, set())
        self.assertEqual(len(timer.scheduled), 1)

    def test_git_index_event_during_scan_is_ignored(self):
        timer = FakeTimer()
        factory = FakeMonitorFactory()
        first = identity("repo")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        entry.scan_in_flight = True
        core = statusd.StatusDaemonCore(cache, timer=timer)
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        core.set_monitor_manager(manager)
        manager.ensure(entry)

        factory.handles[1].emit(first.gitdir / "index.lock")

        self.assertFalse(entry.stale)
        self.assertEqual(entry.stale_paths, set())
        self.assertEqual(timer.scheduled, [])

    def test_git_index_event_just_after_scan_is_ignored(self):
        timer = FakeTimer()
        clock = FakeClock(now=10.1)
        factory = FakeMonitorFactory()
        first = identity("repo")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        entry.last_scanned_at = 10.0
        core = statusd.StatusDaemonCore(
            cache,
            debounce_seconds=0.25,
            timer=timer,
            clock=clock,
        )
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        core.set_monitor_manager(manager)
        manager.ensure(entry)

        factory.handles[1].emit(first.gitdir / "index")

        self.assertFalse(entry.stale)
        self.assertEqual(timer.scheduled, [])

    def test_git_index_event_after_suppression_window_marks_stale(self):
        timer = FakeTimer()
        clock = FakeClock(now=10.5)
        factory = FakeMonitorFactory()
        first = identity("repo")
        cache = statusd.WorktreeCache()
        entry = cache.touch(first)
        entry.scanned = True
        entry.last_scanned_at = 10.0
        core = statusd.StatusDaemonCore(
            cache,
            debounce_seconds=0.25,
            timer=timer,
            clock=clock,
        )
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        core.set_monitor_manager(manager)
        manager.ensure(entry)

        factory.handles[1].emit(first.gitdir / "index")

        self.assertTrue(entry.stale)
        self.assertEqual(entry.stale_paths, set())
        self.assertEqual(len(timer.scheduled), 1)

    def test_stop_cancels_all_worktree_monitors(self):
        factory = FakeMonitorFactory()
        core = statusd.StatusDaemonCore(timer=FakeTimer())
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        first = identity("repo")
        entry = statusd.WorktreeEntry(first)
        manager.ensure(entry)

        manager.stop(first.cache_key)

        self.assertNotIn(first.cache_key, manager.monitors)
        self.assertTrue(all(handle.canceled for handle in factory.handles))

    def test_cache_eviction_stops_monitors(self):
        factory = FakeMonitorFactory()
        cache = statusd.WorktreeCache(max_worktrees=1)
        core = statusd.StatusDaemonCore(cache, timer=FakeTimer())
        manager = statusd_monitor.WorktreeMonitorManager(
            core,
            monitor_factory=factory,
        )
        core.set_monitor_manager(manager)
        first = identity("one")
        second = identity("two")
        first_entry = cache.touch(first)
        manager.ensure(first_entry)

        cache.touch(second)

        self.assertNotIn(first.cache_key, manager.monitors)
        self.assertTrue(all(handle.canceled for handle in factory.handles))


if __name__ == "__main__":
    unittest.main()
