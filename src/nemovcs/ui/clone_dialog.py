"""GTK3 clone dialog."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Literal, Sequence

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nemovcs.ui import logger


VcsKind = Literal["git", "svn"]


def run(paths: Sequence[str], *, vcs: VcsKind = "git") -> int:
    window = CloneDialog(paths or ["."], vcs=vcs)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


class CloneDialog(Gtk.Window):
    def __init__(self, paths: Sequence[str], *, vcs: VcsKind = "git"):
        super().__init__(title=dialog_title(vcs))
        self.vcs = vcs
        self.base_dir = clone_base_dir(paths or ["."])
        self.exit_code = 0
        self.active_logger: logger.LoggerWindow | None = None
        self.clone_completed = False
        self.target_name_autofilled = True

        self.set_default_size(620, 260)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        self.base_label = Gtk.Label(
            label=f"{operation_label(vcs)} into: {self.base_dir}",
            xalign=0,
        )
        self.base_label.set_selectable(True)
        outer.pack_start(self.base_label, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        outer.pack_start(grid, True, True, 0)

        url_label = Gtk.Label(label="Repository URL", xalign=0)
        grid.attach(url_label, 0, 0, 1, 1)

        self.url_entry = Gtk.Entry()
        self.url_entry.connect("changed", self.on_url_changed)
        grid.attach(self.url_entry, 1, 0, 1, 1)

        target_label = Gtk.Label(label="Target Folder", xalign=0)
        grid.attach(target_label, 0, 1, 1, 1)

        self.target_entry = Gtk.Entry()
        self.target_entry.connect("changed", self.on_target_changed)
        grid.attach(self.target_entry, 1, 1, 1, 1)

        self.submodules_check = Gtk.CheckButton(label="Recurse submodules")
        self.submodules_check.set_visible(vcs == "git")
        grid.attach(self.submodules_check, 1, 2, 1, 1)

        grid.set_column_homogeneous(False)
        grid.set_column_spacing(10)
        grid.get_child_at(1, 0).set_hexpand(True)

        buttons = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_layout(Gtk.ButtonBoxStyle.END)
        buttons.set_spacing(8)
        outer.pack_start(buttons, False, False, 0)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        buttons.add(self.cancel_button)

        self.clone_button = Gtk.Button(label=operation_label(vcs))
        self.clone_button.get_style_context().add_class("suggested-action")
        self.clone_button.connect("clicked", self.on_clone_clicked)
        buttons.add(self.clone_button)

    def repository_url(self) -> str:
        return self.url_entry.get_text().strip()

    def target_name(self) -> str:
        return self.target_entry.get_text().strip()

    def on_url_changed(self, _entry: Gtk.Entry) -> None:
        if not self.target_name_autofilled:
            return
        self.target_entry.set_text(derive_target_name(self.repository_url()))
        self.target_name_autofilled = True

    def on_target_changed(self, _entry: Gtk.Entry) -> None:
        self.target_name_autofilled = not bool(self.target_name())

    def on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self.destroy()

    def on_clone_clicked(self, _button: Gtk.Button) -> None:
        error = validate_clone_target(
            self.base_dir,
            self.repository_url(),
            self.target_name(),
        )
        if error:
            self.show_error(error)
            return

        phases = clone_phases(
            self.base_dir,
            self.repository_url(),
            self.target_name(),
            vcs=self.vcs,
            recurse_submodules=self.submodules_check.get_active(),
        )
        window = logger.LoggerWindow(
            dialog_title(self.vcs),
            phases,
            on_complete=self.on_clone_logger_complete,
        )
        self.active_logger = window
        window.connect("destroy", self.on_clone_logger_destroyed)
        window.set_transient_for(self)
        window.show_all()
        self.clone_button.set_sensitive(False)
        self.cancel_button.set_sensitive(False)
        self.set_deletable(False)

    def on_clone_logger_complete(self, ok: bool, _returncodes: list[int]) -> None:
        if ok:
            self.clone_completed = True
            self.hide()
            return

        self.set_deletable(True)
        self.cancel_button.set_sensitive(True)
        self.clone_button.set_sensitive(True)

    def on_clone_logger_destroyed(self, _window: logger.LoggerWindow) -> None:
        self.active_logger = None
        if self.clone_completed:
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


def clone_base_dir(paths: Sequence[str]) -> Path:
    first = Path(paths[0] if paths else ".").expanduser()
    if not first.is_absolute():
        first = Path.cwd() / first
    return first.resolve(strict=False)


def dialog_title(vcs: VcsKind) -> str:
    return "Git Clone" if vcs == "git" else "SVN Checkout"


def operation_label(vcs: VcsKind) -> str:
    return "Clone" if vcs == "git" else "Checkout"


def derive_target_name(url: str) -> str:
    value = url.strip()
    if not value:
        return ""
    value = value.rstrip("/")
    if ":" in value and "/" not in value.rsplit(":", 1)[0]:
        value = value.rsplit(":", 1)[1]
    name = value.rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")


def validate_clone_target(base_dir: Path, url: str, target_name: str) -> str:
    if not url.strip():
        return "Enter a repository URL."
    if not target_name.strip():
        return "Enter a target folder."

    target = Path(target_name)
    if target.is_absolute():
        return "Target folder must be relative."
    if len(target.parts) != 1:
        return "Target folder must be a single folder name."
    if any(part == ".." for part in target.parts):
        return "Target folder must not contain parent directory references."
    if str(target) in {"", "."}:
        return "Enter a target folder."
    if (base_dir / target).exists():
        return "Target folder already exists."
    return ""


def clone_phases(
    base_dir: Path,
    url: str,
    target_name: str,
    *,
    vcs: VcsKind = "git",
    recurse_submodules: bool = False,
) -> list[logger.CommandPhase]:
    if vcs == "svn":
        return [
            logger.CommandPhase(
                "SVN checkout",
                base_dir,
                ("svn", "checkout", url, target_name),
            )
        ]

    args = ["clone"]
    if recurse_submodules:
        args.append("--recurse-submodules")
    args.extend([url, target_name])
    return [logger.CommandPhase.git("Git clone", base_dir, args)]


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
