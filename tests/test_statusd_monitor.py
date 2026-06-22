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


class WorktreeMonitorManagerTest(unittest.TestCase):
    def test_monitor_paths_include_worktree_and_git_metadata(self):
        first = identity("repo")

        paths = statusd_monitor.monitor_paths(first)

        self.assertEqual(
            paths,
            [
                first.root,
                first.gitdir / "index",
                first.gitdir / "HEAD",
                first.common_gitdir / "refs",
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
        self.assertIn(linked.gitdir / "index", paths)
        self.assertIn(linked.gitdir / "HEAD", paths)
        self.assertIn(linked.common_gitdir / "refs", paths)

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
