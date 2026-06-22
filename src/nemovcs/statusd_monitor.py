"""Filesystem monitoring helpers for the status daemon prototype."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import statusd


MonitorCallback = Callable[[Path], None]
MonitorFactory = Callable[[Path, MonitorCallback], object]


class WorktreeMonitorManager:
    def __init__(
        self,
        core: statusd.StatusDaemonCore,
        *,
        monitor_factory: MonitorFactory | None = None,
    ):
        self.core = core
        self.monitor_factory = monitor_factory or gio_monitor
        self.monitors: dict[str, list[object]] = {}

    def ensure(self, entry: statusd.WorktreeEntry) -> None:
        worktree_id = entry.identity.cache_key
        if worktree_id in self.monitors:
            return

        handles: list[object] = []
        for path in monitor_paths(entry.identity):
            handles.append(
                self.monitor_factory(
                    path,
                    lambda changed_path, key=worktree_id: self.on_changed(
                        key,
                        changed_path,
                    ),
                )
            )
        self.monitors[worktree_id] = handles

    def stop(self, worktree_id: str) -> None:
        handles = self.monitors.pop(worktree_id, [])
        for handle in handles:
            cancel = getattr(handle, "cancel", None)
            if cancel is not None:
                cancel()

    def stop_all(self) -> None:
        for worktree_id in list(self.monitors):
            self.stop(worktree_id)

    def on_changed(self, worktree_id: str, changed_path: Path) -> None:
        self.core.mark_stale(worktree_id, [changed_path])


def monitor_paths(identity: statusd.WorktreeIdentity) -> list[Path]:
    candidates = [
        identity.root,
        identity.gitdir / "index",
        identity.gitdir / "HEAD",
        identity.common_gitdir / "refs",
        identity.common_gitdir / "packed-refs",
    ]
    return list(dict.fromkeys(candidates))


def gio_monitor(path: Path, callback: MonitorCallback):
    from gi.repository import Gio

    file = Gio.File.new_for_path(str(path))
    if path.is_dir():
        monitor = file.monitor_directory(Gio.FileMonitorFlags.NONE, None)
    else:
        monitor = file.monitor_file(Gio.FileMonitorFlags.NONE, None)

    def on_changed(_monitor, changed_file, _other_file, _event_type):
        changed = changed_file.get_path()
        callback(Path(changed) if changed else path)

    monitor.connect("changed", on_changed)
    return monitor
