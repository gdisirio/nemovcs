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

from . import git


DEFAULT_MAX_WORKTREES = 12
DEFAULT_DEBOUNCE_SECONDS = 0.75
DBUS_BUS_NAME = "io.github.gdisirio.NemoVCS.Statusd"
DBUS_OBJECT_PATH = "/io/github/gdisirio/NemoVCS/Statusd"
DBUS_INTERFACE = "io.github.gdisirio.NemoVCS.Statusd"


class EmblemStatus(StrEnum):
    CONFLICTED = "conflicted"
    MODIFIED = "modified"
    OK = "ok"
    LOADING = "loading"
    STALE = "stale"
    ERROR = "error"


EMBLEM_PRIORITY = {
    EmblemStatus.ERROR: 50,
    EmblemStatus.CONFLICTED: 40,
    EmblemStatus.MODIFIED: 30,
    EmblemStatus.STALE: 20,
    EmblemStatus.LOADING: 10,
    EmblemStatus.OK: 0,
}


@dataclass(frozen=True)
class WorktreeIdentity:
    root: Path
    gitdir: Path
    common_gitdir: Path
    head_label: str

    @property
    def cache_key(self) -> str:
        return str(self.root)


@dataclass
class WorktreeEntry:
    identity: WorktreeIdentity
    statuses: dict[str, EmblemStatus] = field(default_factory=dict)
    scanned: bool = False
    error: str = ""
    stale: bool = False
    stale_paths: set[str] = field(default_factory=set)
    scan_scheduled: bool = False
    scan_in_flight: bool = False
    rescan_needed: bool = False


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
            identity = identify_worktree(path)
            if identity is None:
                continue
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


class StatusDaemonCore:
    def __init__(
        self,
        cache: WorktreeCache | None = None,
        *,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
        timer: Callable[[float, Callable[[], None]], object] | None = None,
        scan_func: Callable[[WorktreeEntry], None] | None = None,
        status_changed_callback: Callable[[str, list[str]], None] | None = None,
    ):
        self.cache = cache if cache is not None else WorktreeCache()
        self.debounce_seconds = debounce_seconds
        self.timer = timer if timer is not None else immediate_timer
        self.scan_func = scan_func if scan_func is not None else scan_worktree
        self.status_changed_callback = status_changed_callback
        self.changed_worktrees: list[str] = []
        self.monitor_manager = None
        self.cache.evict_callback = self.on_cache_evict

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
            self.scan_entry(entry, notify=False)
            if self.monitor_manager is not None:
                self.monitor_manager.ensure(entry)
            scanned_keys.add(identity.cache_key)
            changed_worktrees.append(identity.cache_key)
        return changed_worktrees

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
        if entry.scan_in_flight:
            entry.rescan_needed = True
            return

        entry.scan_scheduled = False
        self.scan_entry(entry)

    def scan_entry(self, entry: WorktreeEntry, *, notify: bool = True) -> None:
        changed_paths = status_changed_paths(entry)
        entry.scan_in_flight = True
        try:
            self.scan_func(entry)
        finally:
            entry.scan_in_flight = False
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

    def status_record(self, path: str | Path) -> dict[str, str]:
        identity = identify_worktree(path)
        if identity is None:
            return {
                "path": str(path),
                "worktree_id": "",
                "root": "",
                "gitdir": "",
                "common_gitdir": "",
                "head": "",
                "status": EmblemStatus.ERROR,
                "error": "not inside a Git working tree",
            }

        entry = self.cache.get(identity)
        if entry is None:
            return {
                "path": str(path),
                "worktree_id": identity.cache_key,
                "root": str(identity.root),
                "gitdir": str(identity.gitdir),
                "common_gitdir": str(identity.common_gitdir),
                "head": identity.head_label,
                "status": EmblemStatus.LOADING,
                "error": "",
            }

        return {
            "path": str(path),
            "worktree_id": identity.cache_key,
            "root": str(identity.root),
            "gitdir": str(identity.gitdir),
            "common_gitdir": str(identity.common_gitdir),
            "head": identity.head_label,
            "status": path_status(entry, path),
            "error": entry.error,
        }


def identify_worktree(path: str | Path) -> WorktreeIdentity | None:
    """Return the Git worktree identity for `path`, or None outside Git."""

    probe = git.run_git(
        path,
        [
            "rev-parse",
            "--path-format=absolute",
            "--show-toplevel",
            "--git-dir",
            "--git-common-dir",
        ],
    )
    if not probe.ok:
        return None

    lines = [line.strip() for line in probe.stdout.splitlines()]
    if len(lines) < 3:
        return None

    root = Path(lines[0]).resolve(strict=False)
    gitdir = Path(lines[1]).resolve(strict=False)
    common_gitdir = Path(lines[2]).resolve(strict=False)
    return WorktreeIdentity(root, gitdir, common_gitdir, head_label(path))


def head_label(path: str | Path) -> str:
    branch = git.run_git(path, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if branch.ok:
        name = branch.stdout.strip()
        if name:
            return name

    commit = git.run_git(path, ["rev-parse", "--short", "HEAD"])
    if commit.ok:
        sha = commit.stdout.strip()
        if sha:
            return f"detached at {sha}"

    return "unknown"


def scan_worktree(entry: WorktreeEntry) -> None:
    result = git.run_git(entry.identity.root, ["status", "--porcelain=v2", "-z"])
    if not result.ok:
        entry.statuses.clear()
        entry.scanned = True
        entry.error = result.stderr.strip() or result.stdout.strip()
        return

    items = git.parse_status_porcelain_v2_z(
        entry.identity.root,
        result.stdout.encode("utf-8", errors="surrogateescape"),
    )
    statuses: dict[str, EmblemStatus] = {}
    for item in items:
        status = item_to_emblem_status(item)
        statuses[item.path] = status
        if item.old_path:
            statuses[item.old_path] = status

    entry.statuses = statuses
    entry.scanned = True
    entry.error = ""


def item_to_emblem_status(item: git.CommitItem) -> EmblemStatus:
    if item.conflicted or item.status == "conflicted":
        return EmblemStatus.CONFLICTED
    return EmblemStatus.MODIFIED


def path_status(entry: WorktreeEntry, path: str | Path) -> EmblemStatus:
    relpath = relative_path_in_worktree(entry.identity, path)
    if relpath is None:
        return EmblemStatus.ERROR
    if not entry.scanned:
        return EmblemStatus.LOADING
    if entry.error:
        return EmblemStatus.ERROR
    if entry.stale:
        relpath = relative_path_in_worktree(entry.identity, path)
        if not entry.stale_paths or relpath in entry.stale_paths:
            return EmblemStatus.STALE
    return entry.statuses.get(relpath, EmblemStatus.OK)


def aggregate_status(entry: WorktreeEntry, path: str | Path) -> EmblemStatus:
    relpath = relative_path_in_worktree(entry.identity, path)
    if relpath is None:
        return EmblemStatus.ERROR
    if not entry.scanned:
        return EmblemStatus.LOADING
    if entry.error:
        return EmblemStatus.ERROR
    if entry.stale:
        if not entry.stale_paths:
            return EmblemStatus.STALE
        for stale_path in entry.stale_paths:
            if relpath == "." or stale_path == relpath or stale_path.startswith(
                relpath.rstrip("/") + "/"
            ):
                return EmblemStatus.STALE

    if relpath == ".":
        prefix = ""
    else:
        prefix = relpath.rstrip("/") + "/"

    best = entry.statuses.get(relpath, EmblemStatus.OK)
    for item_path, status in entry.statuses.items():
        if prefix and not item_path.startswith(prefix):
            continue
        if EMBLEM_PRIORITY[status] > EMBLEM_PRIORITY[best]:
            best = status
    return best


def relative_path_in_worktree(
    identity: WorktreeIdentity,
    path: str | Path,
) -> str | None:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=False)

    try:
        relpath = candidate.relative_to(identity.root)
    except ValueError:
        return None

    return "." if str(relpath) == "." else relpath.as_posix()


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
        return 1, "", "not inside a Git working tree\n"

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
        lines.append(f"   gitdir: {identity.gitdir}")
        lines.append(f"   common-gitdir: {identity.common_gitdir}")
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
