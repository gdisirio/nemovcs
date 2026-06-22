"""Client-side status cache helpers for future Nemo integration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path


StatusRecord = dict[str, str]
SeenFunc = Callable[[Sequence[str]], Sequence[str]]
GetStatusFunc = Callable[[Sequence[str]], Sequence[StatusRecord]]


class StatusClientCache:
    """Small path-record cache invalidated by daemon StatusChanged signals."""

    def __init__(self):
        self.records: dict[str, StatusRecord] = {}

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
                self.records[normalize_path(path)] = dict(record)

    def get(self, path: str | Path) -> StatusRecord | None:
        record = self.records.get(normalize_path(path))
        return dict(record) if record is not None else None

    def invalidate(
        self,
        worktree_id: str,
        changed_paths: Sequence[str | Path],
    ) -> list[str]:
        changed = [normalize_path(path) for path in changed_paths]
        removed: list[str] = []
        for path, record in list(self.records.items()):
            if record.get("worktree_id") != worktree_id:
                continue
            if not changed or any(
                paths_overlap(path, changed_path)
                for changed_path in changed
            ):
                removed.append(path)
                del self.records[path]
        return removed


def normalize_path(path: str | Path) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return str(candidate.resolve(strict=False))


def paths_overlap(first: str | Path, second: str | Path) -> bool:
    left = Path(normalize_path(first))
    right = Path(normalize_path(second))
    return left == right or is_relative_to(left, right) or is_relative_to(right, left)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
