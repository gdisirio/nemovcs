"""GTK3 rename dialog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nemovcs import backends
from nemovcs.backends.base import Backend, BackendCommandPhase
from nemovcs.ui import logger


@dataclass(frozen=True)
class RenameSource:
    backend: Backend
    root: Path
    path: Path
    relpath: str


def run(paths: Sequence[str]) -> int:
    window = RenameDialog(paths or ["."])
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


class RenameDialog(Gtk.Window):
    def __init__(self, paths: Sequence[str]):
        super().__init__(title="Rename")
        self.paths = list(paths)
        self.exit_code = 0
        self.source = rename_source(self.paths)
        self.active_logger: logger.LoggerWindow | None = None
        self.rename_completed = False

        self.set_default_size(560, 190)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        source_label = Gtk.Label(xalign=0)
        source_label.set_selectable(True)
        if self.source is None:
            source_label.set_text("Select one versioned file or folder to rename.")
        else:
            source_label.set_text(f"Rename: {self.source.path}")
        outer.pack_start(source_label, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        outer.pack_start(grid, True, True, 0)

        name_label = Gtk.Label(label="New Name", xalign=0)
        grid.attach(name_label, 0, 0, 1, 1)

        self.name_entry = Gtk.Entry()
        if self.source is not None:
            self.name_entry.set_text(self.source.path.name)
            self.name_entry.select_region(0, -1)
        grid.attach(self.name_entry, 1, 0, 1, 1)
        grid.get_child_at(1, 0).set_hexpand(True)

        buttons = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_layout(Gtk.ButtonBoxStyle.END)
        buttons.set_spacing(8)
        outer.pack_start(buttons, False, False, 0)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        buttons.add(self.cancel_button)

        self.rename_button = Gtk.Button(label="Rename")
        self.rename_button.get_style_context().add_class("suggested-action")
        self.rename_button.connect("clicked", self.on_rename_clicked)
        self.rename_button.set_sensitive(self.source is not None)
        buttons.add(self.rename_button)

    def target_name(self) -> str:
        return self.name_entry.get_text().strip()

    def on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self.destroy()

    def on_rename_clicked(self, _button: Gtk.Button) -> None:
        if self.source is None:
            self.show_error("Select one versioned file or folder to rename.")
            return

        error = validate_rename_target(self.source, self.target_name())
        if error:
            self.show_error(error)
            return

        phases = rename_phases(self.source, self.target_name())
        if not phases:
            self.show_error("Unable to build a rename command for this selection.")
            return

        window = logger.LoggerWindow(
            "Rename",
            phases,
            on_complete=self.on_rename_logger_complete,
        )
        self.active_logger = window
        window.connect("destroy", self.on_rename_logger_destroyed)
        window.set_transient_for(self)
        window.show_all()
        self.rename_button.set_sensitive(False)
        self.cancel_button.set_sensitive(False)
        self.set_deletable(False)

    def on_rename_logger_complete(self, ok: bool, _returncodes: list[int]) -> None:
        if ok:
            self.rename_completed = True
            self.hide()
            return

        self.set_deletable(True)
        self.cancel_button.set_sensitive(True)
        self.rename_button.set_sensitive(True)

    def on_rename_logger_destroyed(self, _window: logger.LoggerWindow) -> None:
        self.active_logger = None
        if self.rename_completed:
            self.destroy()

    def show_error(self, message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=message,
        )
        dialog.run()
        dialog.destroy()


def rename_source(paths: Sequence[str | Path]) -> RenameSource | None:
    if len(paths) != 1:
        return None

    path = absolute_path(paths[0])
    detected = backends.detect_root(path)
    if detected is None:
        return None

    backend, root = detected
    grouped = backend.group([path])
    relpaths = grouped.get(root)
    if not relpaths or len(relpaths) != 1:
        return None

    return RenameSource(
        backend=backend,
        root=root,
        path=path,
        relpath=relpaths[0],
    )


def validate_rename_target(source: RenameSource, target_name: str) -> str:
    target_text = target_name.strip()
    if not target_text:
        return "Enter a new name."

    target = Path(target_text)
    if target.is_absolute():
        return "New name must be relative."
    if str(target) in {"", "."}:
        return "Enter a new name."
    if len(target.parts) != 1:
        return "New name must be a single file or folder name."
    if any(part == ".." for part in target.parts):
        return "New name must not contain parent directory references."
    if target_text == source.path.name:
        return "Enter a different name."
    if (source.path.parent / target).exists():
        return "Target path already exists."
    return ""


def rename_phases(
    source: RenameSource,
    target_name: str,
) -> list[BackendCommandPhase]:
    target_path = source.path.parent / target_name.strip()
    try:
        target_relpath = target_path.resolve(strict=False).relative_to(
            source.root.resolve(strict=False)
        )
    except ValueError:
        return []
    return backends.rename_phases(
        source.root,
        source.relpath,
        target_relpath.as_posix(),
    )


def absolute_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve(strict=False)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
