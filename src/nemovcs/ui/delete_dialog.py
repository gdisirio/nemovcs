"""GTK3 confirmation and logger flow for VCS-aware deletion."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from nemovcs import backends
from nemovcs.backends.base import BackendCommandPhase
from nemovcs.ui import confirm, info_dialog, logger


MAX_DETAIL_PATHS = 10


def run(paths: Sequence[str]) -> int:
    selected = list(paths or ["."])
    phases = delete_phases(selected)
    if not phases:
        info_dialog.show_error(
            "Unable to delete this selection.",
            "Select versioned files or folders below the working-copy root.",
        )
        return 1

    if not confirm.confirm(
        "Delete selected paths?",
        (
            "This removes the selected paths from disk and schedules their "
            "deletion for the next commit. Modified or unversioned content "
            "may be refused by the version control system."
        ),
        detail=confirmation_detail(selected),
        ok_label="Delete",
        action_style="destructive-action",
    ):
        return 0

    return logger.run("Delete", phases)


def delete_phases(paths: Sequence[str | Path]) -> list[BackendCommandPhase]:
    return backends.delete_phases(paths)


def confirmation_detail(paths: Sequence[str | Path]) -> str:
    normalized = [
        str(Path(path).expanduser().resolve(strict=False))
        for path in paths
    ]
    visible = normalized[:MAX_DETAIL_PATHS]
    lines = [f"Selected: {path}" for path in visible]
    remaining = len(normalized) - len(visible)
    if remaining:
        lines.append(f"... and {remaining} more")
    return "\n".join(lines)
