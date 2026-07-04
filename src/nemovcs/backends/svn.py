"""Subversion backend adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from typing import Iterable, Sequence

from nemovcs.backends.base import (
    BackendChangeItem,
    BackendCommandPhase,
    BackendLog,
    BackendStatusItem,
    BackendStatusScan,
    BackendWorktreeIdentity,
    LogChange,
    LogEntry,
)


SVN_LOG_ACTIONS = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "replaced",
}


def parse_svn_log(data: str) -> list[LogEntry]:
    try:
        document = ET.fromstring(data)
    except ET.ParseError:
        return []

    entries: list[LogEntry] = []
    for logentry in document.findall("logentry"):
        message = logentry.findtext("msg") or ""
        summary, _, body = message.partition("\n")
        changes: list[LogChange] = []
        for path in logentry.findall("paths/path"):
            action = SVN_LOG_ACTIONS.get(path.get("action", ""), "modified")
            copyfrom = path.get("copyfrom-path")
            changes.append(
                LogChange(
                    action=action,
                    path=path.text or "",
                    old_path=copyfrom or None,
                )
            )
        entries.append(
            LogEntry(
                revision=logentry.get("revision", ""),
                author=logentry.findtext("author") or "",
                date=logentry.findtext("date") or "",
                summary=summary,
                body=body,
                changes=tuple(changes),
            )
        )
    return entries


DEFAULT_TIMEOUT_SECONDS = 15
MELD_MISSING_MESSAGE = "meld is required for visual diffs"


@dataclass(frozen=True)
class SvnResult:
    args: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def has_svn_metadata_ancestor(path: str | Path) -> bool:
    """Return True if `path` or one of its ancestors holds a `.svn` directory.

    An SVN working copy always keeps a `.svn` directory at its root (1.7+ keeps
    a single one there; older layouts keep one per directory), so a versioned
    path always has such an ancestor. This lets `root()` skip the `svn info`
    subprocess for the common case of non-SVN paths -- Git trees or plain
    folders -- which matters because backend detection runs on Nemo's UI thread
    while building the context menu.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=False)
    if not candidate.is_dir():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / ".svn").is_dir():
            return True
    return False


class SvnBackend:
    id = "svn"
    label = "Subversion"

    def is_worktree(self, path: str | Path) -> bool:
        return self.root(path) is not None

    def identity(self, path: str | Path) -> BackendWorktreeIdentity | None:
        root = self.root(path)
        if root is None:
            return None
        return BackendWorktreeIdentity(
            root=root,
            vcs_dir=root / ".svn",
            common_dir=root / ".svn",
            head_label=self.current_branch(root),
        )

    def root(self, path: str | Path) -> Path | None:
        if not has_svn_metadata_ancestor(path):
            return None
        result = self.run(path, ["info", "--show-item", "wc-root"])
        if not result.ok:
            return None
        output = result.stdout.strip()
        return Path(output).resolve(strict=False) if output else None

    def group(self, paths: Iterable[str | Path]) -> dict[Path, list[str]]:
        grouped: dict[Path, list[str]] = {}
        for path in paths:
            root = self.root(path)
            if root is None:
                continue
            grouped.setdefault(root, []).append(self.relative_to_root(path, root))
        return grouped

    def status(self, paths: Sequence[str | Path]) -> list[SvnResult]:
        results: list[SvnResult] = []
        for root, relpaths in self.group(paths or [Path.cwd()]).items():
            results.append(self.run(root, ["status", *relpaths]))
        return results

    def log(self, paths: Sequence[str | Path], limit: int) -> list[SvnResult]:
        results: list[SvnResult] = []
        for root, relpaths in self.group(paths or [Path.cwd()]).items():
            results.append(self.run(root, ["log", f"--limit={limit}", *relpaths]))
        return results

    def diff(self, paths: Sequence[str | Path]) -> list[SvnResult]:
        results: list[SvnResult] = []
        for root, relpaths in self.group(paths or [Path.cwd()]).items():
            results.append(self.run(root, ["diff", *relpaths], timeout=3600))
        return results

    def diff_commands(self, paths: Sequence[str | Path]) -> list[SvnResult]:
        results: list[SvnResult] = []
        for root, relpaths in self.group(paths or [Path.cwd()]).items():
            for relpath in relpaths:
                target = root if relpath == "." else root / relpath
                command = ("nemovcs", "svn-meld-diff", str(target))
                if shutil.which("meld") is None:
                    results.append(
                        SvnResult(command, root, 127, "", f"{MELD_MISSING_MESSAGE}\n")
                    )
                    continue
                results.append(SvnResult(command, root, 0, "", ""))
        return results

    def commit(
        self,
        paths: Sequence[str | Path],
        message: str | None,
    ) -> list[SvnResult]:
        results: list[SvnResult] = []
        for root, relpaths in self.group(paths or [Path.cwd()]).items():
            args = ["commit"]
            if message:
                args.extend(["-m", message])
            args.extend(relpaths)
            results.append(self.run(root, args, timeout=3600))
        return results

    def scan_status(self, root: str | Path) -> BackendStatusScan:
        result = self.run(root, ["status", "--xml"])
        if not result.ok:
            return BackendStatusScan(
                ok=False,
                error=result.stderr.strip() or result.stdout.strip(),
            )

        items = self.parse_status(root, result.stdout)
        remote_url = self.remote_url(root)
        return BackendStatusScan(
            ok=True,
            items=tuple(
                BackendStatusItem(
                    path=item.path,
                    status="unversioned" if not item.tracked else "modified",
                    old_path=item.old_path,
                    conflicted=item.conflicted,
                )
                for item in items
            ),
            remote_url=remote_url,
        )

    def scan_log(
        self,
        root: str | Path,
        *,
        limit: int,
        paths: Sequence[str] = (),
    ) -> BackendLog:
        args = ["log", "--xml", "--verbose", f"--limit={limit}", *paths]
        result = self.run(root, args)
        if not result.ok:
            return BackendLog(
                ok=False,
                error=result.stderr.strip() or result.stdout.strip(),
            )
        return BackendLog(ok=True, entries=tuple(parse_svn_log(result.stdout)))

    def commit_items(
        self,
        paths: Sequence[str | Path],
    ) -> dict[Path, list[BackendChangeItem]]:
        items_by_root: dict[Path, list[BackendChangeItem]] = {}
        for root, relpaths in self.group(paths or [Path.cwd()]).items():
            result = self.run(root, ["status", "--xml", *relpaths])
            if not result.ok:
                items_by_root[root] = []
                continue
            items_by_root[root] = self.parse_status(root, result.stdout)
        return items_by_root

    def current_branch(self, root: str | Path) -> str:
        url = self.run(root, ["info", "--show-item", "url"])
        revision = self.run(root, ["info", "--show-item", "revision"])
        url_text = url.stdout.strip() if url.ok else ""
        revision_text = revision.stdout.strip() if revision.ok else ""
        if url_text and revision_text:
            return f"{url_text} @ r{revision_text}"
        if url_text:
            return url_text
        if revision_text:
            return f"r{revision_text}"
        return "unknown"

    def remote_url(self, root: str | Path) -> str:
        result = self.run(root, ["info", "--show-item", "url"])
        return result.stdout.strip() if result.ok else ""

    def stage_phases(
        self,
        paths_by_root: dict[Path, Sequence[str]],
    ) -> list[BackendCommandPhase]:
        return [
            self.phase(f"Add {root.name}", root, ["add", "--parents", *relpaths])
            for root, relpaths in paths_by_root.items()
            if relpaths
        ]

    def commit_phases(
        self,
        root: str | Path,
        relpaths: Sequence[str],
        message: str,
    ) -> list[BackendCommandPhase]:
        return [
            self.phase(
                "Create commit",
                root,
                ["commit", "-m", message, *relpaths],
            )
        ]

    def log_phases(
        self,
        grouped_paths: dict[Path, list[str]],
        limit: int,
    ) -> list[BackendCommandPhase]:
        return [
            self.phase(f"Log {root.name}", root, ["log", f"--limit={limit}", *relpaths])
            for root, relpaths in grouped_paths.items()
        ]

    def update_phases(
        self,
        grouped_paths: dict[Path, list[str]],
    ) -> list[BackendCommandPhase]:
        return [
            self.phase(f"Update {root.name}", root, ["update"])
            for root in grouped_paths
        ]

    def push_phases(
        self,
        grouped_paths: dict[Path, list[str]],
    ) -> list[BackendCommandPhase]:
        return []

    def revert_phases(
        self,
        paths_by_root: dict[Path, Sequence[str]],
    ) -> list[BackendCommandPhase]:
        return [
            self.phase(f"Revert {root.name}", root, ["revert", *relpaths])
            for root, relpaths in paths_by_root.items()
            if relpaths
        ]

    def rename_phases(
        self,
        root: str | Path,
        source_relpath: str,
        target_relpath: str,
    ) -> list[BackendCommandPhase]:
        return [
            self.phase(
                f"Rename {Path(source_relpath).name}",
                root,
                ["move", source_relpath, target_relpath],
            )
        ]

    def file_diff_command(self, item: BackendChangeItem) -> list[str]:
        return ["nemovcs", "svn-meld-diff", str(item.root / item.path)]

    def update(self, paths: Sequence[str | Path]) -> list[SvnResult]:
        results: list[SvnResult] = []
        for root in self.group(paths or [Path.cwd()]):
            results.append(self.run(root, ["update"], timeout=300))
        return results

    def push(self, paths: Sequence[str | Path]) -> list[SvnResult]:
        return []

    def parse_status(self, root: str | Path, data: str) -> list[BackendChangeItem]:
        root_path = Path(root)
        try:
            document = ET.fromstring(data)
        except ET.ParseError:
            return []

        items: list[BackendChangeItem] = []
        for entry in document.findall(".//entry"):
            path = entry.get("path", "")
            wc_status = entry.find("wc-status")
            if not path or wc_status is None:
                continue
            item = wc_status.get("item", "")
            if item in {"normal", "ignored", "external", "none"}:
                continue
            items.append(
                BackendChangeItem(
                    backend_id=self.id,
                    root=root_path,
                    path=path,
                    status=self.status_label(item),
                    tracked=item != "unversioned",
                    conflicted=item == "conflicted",
                )
            )
        return items

    def status_label(self, item: str) -> str:
        return {
            "added": "added",
            "conflicted": "conflicted",
            "deleted": "deleted",
            "missing": "deleted",
            "modified": "modified",
            "replaced": "modified",
            "unversioned": "untracked",
        }.get(item, "changed")

    def run(
        self,
        cwd: str | Path,
        args: Sequence[str],
        *,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> SvnResult:
        resolved_cwd = self.path_for_svn(cwd)
        command = ("svn", *args)
        try:
            proc = subprocess.run(
                command,
                cwd=str(resolved_cwd),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            return SvnResult(command, resolved_cwd, 127, "", "svn executable not found\n")
        except subprocess.TimeoutExpired:
            return SvnResult(command, resolved_cwd, 124, "", "svn command timed out\n")
        return SvnResult(command, resolved_cwd, proc.returncode, proc.stdout, proc.stderr)

    def phase(
        self,
        title: str,
        cwd: str | Path,
        args: Sequence[str],
    ) -> BackendCommandPhase:
        cwd_path = Path(cwd)
        return BackendCommandPhase(
            title=title,
            cwd=cwd_path,
            command=("svn", *args),
        )

    def path_for_svn(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve(strict=False)
        if candidate.is_dir():
            return candidate
        parent = candidate.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        return parent

    def relative_to_root(self, path: str | Path, root: str | Path) -> str:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve(strict=False)
        root_path = Path(root).resolve(strict=False)
        try:
            rel = candidate.relative_to(root_path)
        except ValueError:
            return "."
        return "." if str(rel) == "." else rel.as_posix()
