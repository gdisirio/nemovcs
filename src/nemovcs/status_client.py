"""Client-side status cache helpers for the Nemo integration."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterator, Sequence
import os
from pathlib import Path


StatusRecord = dict[str, str]
SeenFunc = Callable[[Sequence[str]], Sequence[str]]
GetStatusFunc = Callable[[Sequence[str]], Sequence[StatusRecord]]

# Upper bound on cached path records. The cache is consulted and invalidated on
# Nemo's main thread, so it must stay small enough that a full walk is cheap;
# it only needs to cover the items Nemo currently shows plus some history.
DEFAULT_MAX_RECORDS = 4096


class StatusClientCache:
    """Small path-record cache invalidated by daemon StatusChanged signals.

    Records are keyed by normalized path and bounded to `max_records` entries,
    evicting least recently used paths first.
    """

    def __init__(self, max_records: int = DEFAULT_MAX_RECORDS):
        if max_records < 1:
            raise ValueError("max_records must be at least 1")
        self.max_records = max_records
        self.records: OrderedDict[str, StatusRecord] = OrderedDict()

    def refresh(
        self,
        paths: Sequence[str | Path],
        seen: SeenFunc,
        get_status: GetStatusFunc,
    ) -> list[StatusRecord]:
        path_strings = [str(path) for path in paths]
        seen(path_strings)
        records = [dict(record) for record in get_status(path_strings)]
        self.update(records)
        return records

    def update(self, records: Sequence[StatusRecord]) -> None:
        for record in records:
            path = record.get("path")
            if path:
                key = normalize_path(path)
                self.records[key] = dict(record)
                self.records.move_to_end(key)
        while len(self.records) > self.max_records:
            self.records.popitem(last=False)

    def get(self, path: str | Path) -> StatusRecord | None:
        key = normalize_path(path)
        record = self.records.get(key)
        if record is None:
            return None
        self.records.move_to_end(key)
        return dict(record)

    def invalidate(
        self,
        worktree_id: str,
        changed_paths: Sequence[str | Path],
    ) -> list[str]:
        # Match by path so a path that changed worktree membership (e.g. a
        # directory that just became a repository) is invalidated even though
        # its cached record still names the old/empty worktree. Fall back to
        # the worktree id only for whole-worktree signals that carry no
        # specific paths.
        #
        # This runs on Nemo's main thread for every StatusChanged signal, so
        # overlap checks are set lookups on already-normalized strings rather
        # than per-pair filesystem path resolution.
        index = PathOverlapIndex(changed_paths)
        removed: list[str] = []
        for path, record in list(self.records.items()):
            if index:
                matched = index.overlaps(path)
            else:
                matched = record.get("worktree_id") == worktree_id
            if matched:
                removed.append(path)
                del self.records[path]
        return removed


class PathOverlapIndex:
    """Precomputed lookup for "does this path overlap any changed path".

    Two normalized paths overlap when one equals or contains the other. The
    changed paths and all of their ancestors are stored in sets so that a
    candidate path is tested with O(depth) dictionary lookups and no
    filesystem access, regardless of how many changed paths there are.
    """

    def __init__(self, changed_paths: Sequence[str | Path]):
        self.changed: set[str] = set()
        self.changed_ancestors: set[str] = set()
        for path in changed_paths:
            normalized = normalize_path(path)
            self.changed.add(normalized)
            self.changed_ancestors.update(path_ancestors(normalized))

    def __bool__(self) -> bool:
        return bool(self.changed)

    def overlaps(self, normalized_path: str) -> bool:
        """Return True when `normalized_path` equals, contains, or lies under
        a changed path. The argument must already be normalized."""
        if normalized_path in self.changed:
            return True
        # The candidate contains a changed path.
        if normalized_path in self.changed_ancestors:
            return True
        # The candidate lies under a changed path.
        return any(
            ancestor in self.changed for ancestor in path_ancestors(normalized_path)
        )


def path_ancestors(normalized_path: str) -> Iterator[str]:
    """Yield the proper ancestors of a normalized absolute path, nearest first."""
    current = normalized_path
    while True:
        parent = os.path.dirname(current)
        if not parent or parent == current:
            return
        yield parent
        current = parent


def normalize_path(path: str | Path) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return str(candidate.resolve(strict=False))


def paths_overlap(first: str | Path, second: str | Path) -> bool:
    return PathOverlapIndex([second]).overlaps(normalize_path(first))

