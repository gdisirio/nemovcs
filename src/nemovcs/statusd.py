"""Status daemon model helpers.

This module intentionally contains no DBus, filesystem monitoring, or Nemo
plugin code yet. The first milestone is a testable model for identifying Git
worktrees, including linked worktrees.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import time

from . import backends
from . import config
from .backends.base import BackendStatusItem


DEFAULT_MAX_WORKTREES = config.DEFAULT_MAX_WORKTREES
DEFAULT_DEBOUNCE_SECONDS = config.DEFAULT_DEBOUNCE_SECONDS
DEFAULT_SCAN_TTL_SECONDS = config.DEFAULT_SCAN_TTL_SECONDS
DBUS_BUS_NAME = "io.github.gdisirio.NemoVCS.Statusd"
DBUS_OBJECT_PATH = "/io/github/gdisirio/NemoVCS/Statusd"
DBUS_INTERFACE = "io.github.gdisirio.NemoVCS.Statusd"


class EmblemStatus(StrEnum):
    CONFLICTED = "conflicted"
    MODIFIED = "modified"
    UNVERSIONED = "unversioned"
    IGNORED = "ignored"
    OK = "ok"
    LOADING = "loading"
    STALE = "stale"
    ERROR = "error"


EMBLEM_PRIORITY = {
    EmblemStatus.ERROR: 50,
    EmblemStatus.CONFLICTED: 40,
    EmblemStatus.MODIFIED: 30,
    EmblemStatus.UNVERSIONED: 25,
    EmblemStatus.STALE: 20,
    EmblemStatus.LOADING: 10,
    EmblemStatus.IGNORED: 0,
    EmblemStatus.OK: 0,
}


@dataclass(frozen=True)
class WorktreeIdentity:
    root: Path
    gitdir: Path
    common_gitdir: Path
    head_label: str
    backend_id: str = "git"

    @property
    def cache_key(self) -> str:
        return f"{self.backend_id}:{self.root}"


@dataclass
class WorktreeEntry:
    identity: WorktreeIdentity
    statuses: dict[str, EmblemStatus] = field(default_factory=dict)
    tracked_paths: set[str] = field(default_factory=set)
    scanned: bool = False
    error: str = ""
    stale: bool = False
    stale_paths: set[str] = field(default_factory=set)
    scan_scheduled: bool = False
    scan_in_flight: bool = False
    rescan_needed: bool = False
    last_scanned_at: float | None = None
    remote_url: str = ""


ScanWork = Callable[[], WorktreeEntry]
ScanComplete = Callable[[WorktreeEntry], None]
ScanScheduler = Callable[[ScanWork, ScanComplete], object]


class WorktreeCache:
    def __init__(self, max_worktrees: int = DEFAULT_MAX_WORKTREES):
        if max_worktrees < 1:
            raise ValueError("max_worktrees must be at least 1")
        self.max_worktrees = max_worktrees
        self._entries: OrderedDict[str, WorktreeEntry] = OrderedDict()
        self.evict_callback: Callable[[WorktreeEntry], None] | None = None

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, identity: WorktreeIdentity) -> bool:
        return identity.cache_key in self._entries

    def entries(self) -> list[WorktreeEntry]:
        return list(self._entries.values())

    def identities(self) -> list[WorktreeIdentity]:
        return [entry.identity for entry in self._entries.values()]

    def seen(self, paths: list[str | Path]) -> list[WorktreeIdentity]:
        seen_identities: list[WorktreeIdentity] = []
        for path in paths:
            entry = self.entry_for_cached_path(path)
            if entry is None:
                identity = identify_worktree(path)
                if identity is None:
                    continue
            else:
                identity = entry.identity
            self.touch(identity)
            seen_identities.append(identity)
        return seen_identities

    def touch(self, identity: WorktreeIdentity) -> WorktreeEntry:
        key = identity.cache_key
        if key in self._entries:
            entry = self._entries.pop(key)
            entry.identity = identity
        else:
            entry = WorktreeEntry(identity)

        self._entries[key] = entry
        self._entries.move_to_end(key, last=False)
        self._evict_oldest()
        return entry

    def get(self, identity: WorktreeIdentity) -> WorktreeEntry | None:
        return self._entries.get(identity.cache_key)

    def entry_by_key(self, worktree_id: str) -> WorktreeEntry | None:
        return self._entries.get(worktree_id)

    def entry_for_cached_path(self, path: str | Path) -> WorktreeEntry | None:
        candidate = normalized_path(path)
        matches = [
            entry
            for entry in self._entries.values()
            if relative_path_in_worktree(entry.identity, candidate) is not None
        ]
        if not matches:
            return None

        matches.sort(key=lambda entry: len(str(entry.identity.root)), reverse=True)
        entry = matches[0]
        if has_nested_vcs_marker(entry.identity, candidate):
            return None
        return entry

    def scan(self, identity: WorktreeIdentity) -> WorktreeEntry:
        entry = self.touch(identity)
        scan_worktree(entry)
        return entry

    def _evict_oldest(self) -> None:
        while len(self._entries) > self.max_worktrees:
            _key, entry = self._entries.popitem(last=True)
            self.on_evict(entry)

    def on_evict(self, entry: WorktreeEntry) -> None:
        """Hook for stopping monitors and releasing per-worktree resources later."""
        if self.evict_callback is not None:
            self.evict_callback(entry)

    def resize(self, max_worktrees: int) -> None:
        if max_worktrees < 1:
            raise ValueError("max_worktrees must be at least 1")
        self.max_worktrees = max_worktrees
        self._evict_oldest()


class StatusDaemonCore:
    def __init__(
        self,
        cache: WorktreeCache | None = None,
        *,
        debounce_seconds: float | None = None,
        scan_ttl_seconds: float | None = None,
        timer: Callable[[float, Callable[[], None]], object] | None = None,
        clock: Callable[[], float] | None = None,
        scan_scheduler: ScanScheduler | None = None,
        scan_func: Callable[[WorktreeEntry], None] | None = None,
        status_changed_callback: Callable[[str, list[str]], None] | None = None,
    ):
        self.cache = cache if cache is not None else WorktreeCache()
        self.debounce_seconds = (
            debounce_seconds if debounce_seconds is not None else DEFAULT_DEBOUNCE_SECONDS
        )
        self.scan_ttl_seconds = (
            scan_ttl_seconds
            if scan_ttl_seconds is not None
            else DEFAULT_SCAN_TTL_SECONDS
        )
        self.timer = timer if timer is not None else immediate_timer
        self.clock = clock if clock is not None else time.monotonic
        self.scan_scheduler = scan_scheduler
        self.scan_func = scan_func if scan_func is not None else scan_worktree
        self.status_changed_callback = status_changed_callback
        self.changed_worktrees: list[str] = []
        self.monitor_manager = None
        self.cache.evict_callback = self.on_cache_evict

    @classmethod
    def from_config(cls, **kwargs) -> "StatusDaemonCore":
        settings = config.load_statusd_settings()
        return cls(
            cache=WorktreeCache(max_worktrees=settings.max_worktrees),
            debounce_seconds=settings.debounce_seconds,
            scan_ttl_seconds=settings.scan_ttl_seconds,
            **kwargs,
        )

    def set_monitor_manager(self, monitor_manager) -> None:
        self.monitor_manager = monitor_manager

    def on_cache_evict(self, entry: WorktreeEntry) -> None:
        if self.monitor_manager is not None:
            self.monitor_manager.stop(entry.identity.cache_key)

    def seen(self, paths: list[str | Path]) -> list[str]:
        identities = self.cache.seen(paths)
        scanned_keys: set[str] = set()
        changed_worktrees: list[str] = []
        for identity in identities:
            if identity.cache_key in scanned_keys:
                continue
            entry = self.cache.touch(identity)
            if self.should_scan_seen_entry(entry):
                self.request_scan_entry(
                    entry,
                    notify=self.scan_scheduler is not None,
                )
            if self.monitor_manager is not None:
                self.monitor_manager.ensure(entry)
            scanned_keys.add(identity.cache_key)
            changed_worktrees.append(identity.cache_key)
        return changed_worktrees

    def should_scan_seen_entry(self, entry: WorktreeEntry) -> bool:
        return (
            not entry.scanned
            or entry.stale
            or bool(entry.error)
            or self.scan_ttl_expired(entry)
        )

    def scan_ttl_expired(self, entry: WorktreeEntry) -> bool:
        if self.scan_ttl_seconds <= 0:
            return False
        if entry.last_scanned_at is None:
            return True
        return self.clock() - entry.last_scanned_at >= self.scan_ttl_seconds

    def mark_stale(
        self,
        worktree_id: str,
        paths: list[str | Path] | None = None,
    ) -> bool:
        entry = self.cache.entry_by_key(worktree_id)
        if entry is None:
            return False

        entry.stale = True
        if paths:
            for path in paths:
                relpath = relative_path_in_worktree(entry.identity, path)
                if relpath is not None:
                    entry.stale_paths.add(relpath)

        if entry.scan_in_flight:
            entry.rescan_needed = True
            return True

        if not entry.scan_scheduled:
            entry.scan_scheduled = True
            self.timer(
                self.debounce_seconds,
                lambda key=worktree_id: self.run_scheduled_scan(key),
            )
        return True

    def run_scheduled_scan(self, worktree_id: str) -> None:
        entry = self.cache.entry_by_key(worktree_id)
        if entry is None:
            return
        if not entry.scan_scheduled:
            return
        if entry.scan_in_flight:
            entry.rescan_needed = True
            return

        entry.scan_scheduled = False
        self.request_scan_entry(entry)

    def request_scan_entry(self, entry: WorktreeEntry, *, notify: bool = True) -> None:
        if entry.scan_in_flight:
            entry.rescan_needed = True
            return

        entry.scan_scheduled = False
        if self.scan_scheduler is None:
            self.scan_entry(entry, notify=notify)
            return

        self.start_async_scan_entry(entry, notify=notify)

    def scan_entry(self, entry: WorktreeEntry, *, notify: bool = True) -> None:
        if entry.scan_in_flight:
            entry.rescan_needed = True
            return

        changed_paths = status_changed_paths(entry)
        entry.scan_in_flight = True
        try:
            self.scan_func(entry)
        finally:
            entry.scan_in_flight = False
        self.finish_scan_entry(entry, entry, changed_paths, notify=notify)

    def start_async_scan_entry(
        self,
        entry: WorktreeEntry,
        *,
        notify: bool = True,
    ) -> None:
        changed_paths = status_changed_paths(entry)
        entry.scan_in_flight = True

        def work() -> WorktreeEntry:
            scanned = WorktreeEntry(entry.identity)
            try:
                self.scan_func(scanned)
            except Exception as exc:
                scanned.statuses.clear()
                scanned.tracked_paths.clear()
                scanned.scanned = True
                scanned.error = str(exc)
            return scanned

        def complete(scanned: WorktreeEntry) -> None:
            self.finish_scan_entry(entry, scanned, changed_paths, notify=notify)

        assert self.scan_scheduler is not None
        self.scan_scheduler(work, complete)

    def finish_scan_entry(
        self,
        entry: WorktreeEntry,
        scanned: WorktreeEntry,
        changed_paths: list[str],
        *,
        notify: bool = True,
    ) -> None:
        if self.cache.entry_by_key(entry.identity.cache_key) is not entry:
            return

        entry.statuses = dict(scanned.statuses)
        entry.tracked_paths = set(scanned.tracked_paths)
        entry.remote_url = scanned.remote_url
        entry.scanned = scanned.scanned
        entry.error = scanned.error
        entry.scan_in_flight = False
        entry.last_scanned_at = self.clock()
        entry.stale = False
        entry.stale_paths.clear()
        self.changed_worktrees.append(entry.identity.cache_key)
        if notify:
            self.notify_status_changed(entry.identity.cache_key, changed_paths)

        if entry.rescan_needed:
            entry.rescan_needed = False
            self.mark_stale(entry.identity.cache_key)

    def notify_status_changed(self, worktree_id: str, paths: list[str]) -> None:
        if self.status_changed_callback is not None:
            self.status_changed_callback(worktree_id, paths)

    def get_status(self, paths: list[str | Path]) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for path in paths:
            records.append(self.status_record(path))
        return records

    def cache_records(self) -> list[dict[str, str]]:
        return [cache_record(entry) for entry in self.cache.entries()]

    def settings_record(self) -> dict[str, str]:
        return {
            "max_worktrees": str(self.cache.max_worktrees),
            "debounce_seconds": f"{self.debounce_seconds:g}",
            "scan_ttl_seconds": f"{self.scan_ttl_seconds:g}",
            "config_path": str(config.settings_path()),
        }

    def set_settings(self, values: dict[str, str]) -> dict[str, str]:
        settings = config.StatusdSettings.from_mapping(values)
        config.save_statusd_settings(settings)
        self.cache.resize(settings.max_worktrees)
        self.debounce_seconds = settings.debounce_seconds
        self.scan_ttl_seconds = settings.scan_ttl_seconds
        return self.settings_record()

    def status_record(self, path: str | Path) -> dict[str, str]:
        entry = self.cache.entry_for_cached_path(path)
        if entry is None:
            identity = identify_worktree(path)
        else:
            identity = entry.identity

        if identity is None:
            return {
                "path": str(path),
                "backend": "",
                "worktree_id": "",
                "root": "",
                "gitdir": "",
                "common_gitdir": "",
                "head": "",
                "remote": "",
                "status": EmblemStatus.ERROR,
                "error": "not inside a versioned working tree",
            }

        if entry is None:
            entry = self.cache.get(identity)
        if entry is None:
            return {
                "path": str(path),
                "backend": identity.backend_id,
                "worktree_id": identity.cache_key,
                "root": str(identity.root),
                "gitdir": str(identity.gitdir),
                "common_gitdir": str(identity.common_gitdir),
                "head": identity.head_label,
                "remote": "",
                "status": EmblemStatus.LOADING,
                "error": "",
            }

        return {
            "path": str(path),
            "backend": identity.backend_id,
            "worktree_id": identity.cache_key,
            "root": str(identity.root),
            "gitdir": str(identity.gitdir),
            "common_gitdir": str(identity.common_gitdir),
            "head": identity.head_label,
            "remote": entry.remote_url,
            "status": aggregate_status(entry, path),
            "error": entry.error,
        }


def cache_record(entry: WorktreeEntry) -> dict[str, str]:
    if entry.error:
        status = EmblemStatus.ERROR
    elif not entry.scanned:
        status = EmblemStatus.LOADING
    else:
        status = aggregate_status(entry, entry.identity.root)

    return {
        "path": str(entry.identity.root),
        "backend": entry.identity.backend_id,
        "worktree_id": entry.identity.cache_key,
        "root": str(entry.identity.root),
        "gitdir": str(entry.identity.gitdir),
        "common_gitdir": str(entry.identity.common_gitdir),
        "head": entry.identity.head_label,
        "remote": entry.remote_url,
        "status": str(status),
        "error": entry.error,
    }


def identify_worktree(path: str | Path) -> WorktreeIdentity | None:
    """Return the worktree identity for `path`, or None outside known VCS roots."""

    detected = backends.detect_worktree_identity(path)
    if detected is None:
        return None

    backend, identity = detected
    return WorktreeIdentity(
        root=identity.root,
        gitdir=identity.vcs_dir,
        common_gitdir=identity.common_dir,
        head_label=identity.head_label,
        backend_id=backend.id,
    )


def scan_worktree(entry: WorktreeEntry) -> None:
    backend = backends.backend_by_id(entry.identity.backend_id)
    if backend is None:
        entry.statuses.clear()
        entry.remote_url = ""
        entry.scanned = True
        entry.error = f"unknown backend: {entry.identity.backend_id}"
        return

    result = backend.scan_status(entry.identity.root)
    if not result.ok:
        entry.statuses.clear()
        entry.tracked_paths.clear()
        entry.remote_url = ""
        entry.scanned = True
        entry.error = result.error
        return

    statuses: dict[str, EmblemStatus] = {}
    for item in result.items:
        status = item_to_emblem_status(item)
        statuses[item.path] = status
        if item.old_path:
            statuses[item.old_path] = status

    entry.statuses = statuses
    entry.tracked_paths = set(result.tracked_paths)
    entry.remote_url = result.remote_url
    entry.scanned = True
    entry.error = ""


def item_to_emblem_status(item: BackendStatusItem) -> EmblemStatus:
    if item.conflicted:
        return EmblemStatus.CONFLICTED
    if item.status in {"untracked", "unversioned"}:
        return EmblemStatus.UNVERSIONED
    return EmblemStatus.MODIFIED


def path_status(entry: WorktreeEntry, path: str | Path) -> EmblemStatus:
    relpath = relative_path_in_worktree(entry.identity, path)
    if relpath is None:
        return EmblemStatus.ERROR
    if not entry.scanned:
        return EmblemStatus.LOADING
    if entry.error:
        return EmblemStatus.ERROR
    status = entry.statuses.get(relpath)
    if status is not None:
        return status
    if is_unversioned_directory(entry, relpath, path):
        return EmblemStatus.UNVERSIONED
    if is_ignored_path(entry, relpath, path):
        return EmblemStatus.IGNORED
    return EmblemStatus.OK


def aggregate_status(entry: WorktreeEntry, path: str | Path) -> EmblemStatus:
    relpath = relative_path_in_worktree(entry.identity, path)
    if relpath is None:
        return EmblemStatus.ERROR
    if not entry.scanned:
        return EmblemStatus.LOADING
    if entry.error:
        return EmblemStatus.ERROR

    if relpath == ".":
        prefix = ""
    else:
        prefix = relpath.rstrip("/") + "/"

    direct_status = entry.statuses.get(relpath)
    if direct_status == EmblemStatus.UNVERSIONED:
        return EmblemStatus.UNVERSIONED

    best = direct_status or EmblemStatus.OK
    for item_path, status in entry.statuses.items():
        if (
            status == EmblemStatus.UNVERSIONED
            and item_path != relpath
            and entry.identity.backend_id == "svn"
        ):
            continue
        if prefix and not item_path.startswith(prefix):
            continue
        if EMBLEM_PRIORITY[status] > EMBLEM_PRIORITY[best]:
            best = status
    if best == EmblemStatus.OK and is_unversioned_directory(entry, relpath, path):
        return EmblemStatus.UNVERSIONED
    if best == EmblemStatus.OK and is_ignored_path(entry, relpath, path):
        return EmblemStatus.IGNORED
    if (
        best == EmblemStatus.UNVERSIONED
        and not is_unversioned_directory(entry, relpath, path)
    ):
        return EmblemStatus.MODIFIED
    return best


def is_unversioned_directory(
    entry: WorktreeEntry,
    relpath: str,
    path: str | Path,
) -> bool:
    if entry.identity.backend_id != "git" or relpath == ".":
        return False

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=False)
    if not candidate.is_dir():
        return False

    prefix = relpath.rstrip("/") + "/"
    return not any(
        tracked == relpath or tracked.startswith(prefix)
        for tracked in entry.tracked_paths
    )


def is_ignored_path(
    entry: WorktreeEntry,
    relpath: str,
    path: str | Path,
) -> bool:
    if entry.identity.backend_id != "git" or relpath == ".":
        return False
    if relpath in entry.tracked_paths:
        return False

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=False)
    return candidate.is_file()


def relative_path_in_worktree(
    identity: WorktreeIdentity,
    path: str | Path,
) -> str | None:
    candidate = normalized_path(path)

    try:
        relpath = candidate.relative_to(identity.root)
    except ValueError:
        return None

    return "." if str(relpath) == "." else relpath.as_posix()


def normalized_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve(strict=False)


def has_nested_vcs_marker(identity: WorktreeIdentity, path: str | Path) -> bool:
    candidate = normalized_path(path)
    if not candidate.is_dir():
        candidate = candidate.parent

    try:
        relative = candidate.relative_to(identity.root)
    except ValueError:
        return False

    current = identity.root
    for part in relative.parts:
        current = current / part
        if current == identity.root:
            continue
        if (current / ".git").exists() or (current / ".svn").exists():
            return True
    return False


def status_changed_paths(entry: WorktreeEntry) -> list[str]:
    if not entry.stale_paths:
        return [str(entry.identity.root)]

    return [
        str(entry.identity.root / relpath)
        for relpath in sorted(entry.stale_paths)
        if relpath != "."
    ] or [str(entry.identity.root)]


def format_cache_probe(paths: list[str | Path]) -> tuple[int, str, str]:
    cache = WorktreeCache()
    identities = cache.seen(paths)
    if not identities:
        return 1, "", "not inside a versioned working tree\n"

    scanned_keys: set[str] = set()
    for identity in identities:
        if identity.cache_key in scanned_keys:
            continue
        cache.scan(identity)
        scanned_keys.add(identity.cache_key)

    lines: list[str] = []
    lines.append("Cache:")
    for idx, entry in enumerate(cache.entries(), start=1):
        identity = entry.identity
        lines.append(f"{idx}. {identity.root}")
        lines.append(f"   backend: {identity.backend_id}")
        lines.append(f"   vcs-dir: {identity.gitdir}")
        lines.append(f"   common-vcs-dir: {identity.common_gitdir}")
        lines.append(f"   head: {identity.head_label}")
        if entry.error:
            lines.append(f"   error: {entry.error}")

    lines.append("")
    lines.append("Paths:")
    for path in paths:
        identity = identify_worktree(path)
        if identity is None:
            lines.append(f"{path}: outside-worktree")
            continue
        entry = cache.get(identity)
        if entry is None:
            lines.append(f"{path}: loading")
            continue
        lines.append(f"{path}: {path_status(entry, path)}")

    return 0, "\n".join(lines) + "\n", ""


def immediate_timer(_delay_seconds: float, callback: Callable[[], None]) -> object:
    callback()
    return None
