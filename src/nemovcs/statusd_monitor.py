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
                    lambda changed_path, key=worktree_id, identity=entry.identity: self.on_changed(
                        key,
                        identity,
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

    def on_changed(
        self,
        worktree_id: str,
        identity: statusd.WorktreeIdentity,
        changed_path: Path,
    ) -> None:
        if is_vcs_metadata_path(identity, changed_path):
            self.core.mark_stale(worktree_id)
            return
        self.core.mark_stale(worktree_id, [changed_path])


def monitor_paths(identity: statusd.WorktreeIdentity) -> list[Path]:
    if identity.backend_id == "svn":
        return list(dict.fromkeys([identity.root, identity.gitdir / "wc.db"]))

    candidates = [
        identity.root,
        identity.gitdir,
        identity.common_gitdir,
        identity.gitdir / "index",
        identity.gitdir / "HEAD",
        identity.common_gitdir / "refs",
        identity.common_gitdir / "refs" / "heads",
        identity.common_gitdir / "refs" / "tags",
        identity.common_gitdir / "packed-refs",
    ]
    return list(dict.fromkeys(candidates))


def is_vcs_metadata_path(identity: statusd.WorktreeIdentity, path: Path) -> bool:
    if identity.backend_id == "svn":
        return is_relative_to(path, identity.gitdir)
    return is_relative_to(path, identity.gitdir) or is_relative_to(
        path,
        identity.common_gitdir,
    )


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


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
