"""GTK3 revert dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nemovcs import backends
from nemovcs.backends.base import BackendChangeItem, BackendCommandPhase
from nemovcs.ui import logger
from nemovcs.ui.stage_dialog import (
    COL_INCLUDED,
    COL_ITEM,
    StageDialog,
)


def run(paths: Sequence[str]) -> int:
    window = RevertDialog(paths or ["."])
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


class RevertDialog(StageDialog):
    def __init__(self, paths: Sequence[str]):
        super().__init__(paths, operation="stage")
        self.set_title("Revert")
        self.stage_button.set_label("Revert Selected")

    def load_items(self) -> None:
        self.store.clear()
        self.items_by_root = backends.commit_items(self.paths)

        total = 0
        conflicted = 0
        for root, items in self.items_by_root.items():
            for item in items:
                if not item.tracked:
                    continue
                total += 1
                conflicted += 1 if item.conflicted else 0
                self.store.append(
                    [
                        self.default_selected(item),
                        self.status_icon(item.status),
                        item.status,
                        self.file_icon(item),
                        root.name,
                        item.path,
                        item.old_path or "",
                        item,
                    ]
                )

        repo_count = len(self.items_by_root)
        if total:
            self.status_label.set_text(
                f"{total} files in {repo_count} repository(s): "
                f"{conflicted} conflicted"
            )
        elif repo_count:
            self.status_label.set_text(f"No files to revert in {repo_count} repository(s).")
        else:
            self.status_label.set_text("No versioned repository selected.")
            self.exit_code = 1

        self.stage_button.set_sensitive(total > 0)

    @staticmethod
    def default_selected(item: BackendChangeItem) -> bool:
        return item.tracked

    def on_include_toggled(self, _renderer: Gtk.CellRendererToggle, path: str) -> None:
        row = self.store[path]
        row[COL_INCLUDED] = not row[COL_INCLUDED]

    def on_context_toggle(self, _item: Gtk.MenuItem) -> None:
        for iter_ in self.selected_iters():
            self.store[iter_][COL_INCLUDED] = not self.store[iter_][COL_INCLUDED]

    def on_stage_clicked(self, _button: Gtk.Button) -> None:
        paths_by_root = self.checked_stage_paths_by_root()
        phases = self.stage_phases(paths_by_root)
        if not phases:
            self.show_error("Select at least one file to revert.")
            return
        if not self.confirm_revert(paths_by_root):
            return

        window = logger.LoggerWindow(
            "Revert",
            phases,
            on_complete=self.on_stage_logger_complete,
        )
        self.active_logger = window
        window.connect("destroy", self.on_stage_logger_destroyed)
        window.set_transient_for(self)
        window.show_all()
        self.stage_button.set_sensitive(False)
        self.close_button.set_sensitive(False)
        self.set_deletable(False)

    def confirm_revert(self, paths_by_root: dict[Path, Sequence[str]]) -> bool:
        total = sum(len(paths) for paths in paths_by_root.values())
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Revert {total} selected path(s)?",
        )
        dialog.format_secondary_text(
            "This will discard local changes in tracked files. "
            "Unversioned files are not included."
        )
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def stage_phases(
        self,
        paths_by_root: dict[Path, Sequence[str]],
    ) -> list[BackendCommandPhase]:
        return revert_phases(paths_by_root)


def revert_phases(
    paths_by_root: dict[Path, Sequence[str]],
) -> list[BackendCommandPhase]:
    return backends.revert_phases(paths_by_root)
