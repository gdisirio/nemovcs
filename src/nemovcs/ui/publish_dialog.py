"""GTK3 publish dialog: create a remote for a local repository via a forge CLI."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Sequence

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nemovcs import git
from nemovcs.forge import forge_by_id
from nemovcs.ui import logger


def run(paths: Sequence[str], *, forge_id: str) -> int:
    forge = forge_by_id(forge_id)
    if forge is None:
        print(f"unknown forge: {forge_id}", file=sys.stderr)
        return 1
    window = PublishDialog(paths or ["."], forge)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


def publish_root(paths: Sequence[str]) -> Path | None:
    root = git.repo_root(paths[0] if paths else ".")
    return Path(root) if root is not None else None


def default_repo_name(root: Path | None) -> str:
    if root is None:
        return ""
    return root.name


def validate_repo_name(name: str) -> str:
    value = name.strip()
    if not value:
        return "Enter a repository name."
    if re.search(r"\s", value):
        return "Repository name must not contain spaces."
    return ""


def active_account_name(accounts) -> str | None:
    return next((account.name for account in accounts if account.active), None)


def publish_phases(
    forge,
    root: Path,
    name: str,
    private: bool,
) -> list[logger.CommandPhase]:
    return [
        logger.CommandPhase(
            f"Publish to {forge.label}",
            root,
            tuple(forge.publish_command(str(root), name, private)),
        )
    ]


class PublishDialog(Gtk.Window):
    def __init__(self, paths: Sequence[str], forge):
        super().__init__(title=f"Publish to {forge.label}")
        self.forge = forge
        self.root = publish_root(paths)
        self.exit_code = 0
        self.active_logger: logger.LoggerWindow | None = None
        self.publish_completed = False
        self.accounts = forge.accounts()
        self.active_account = active_account_name(self.accounts)

        self.set_default_size(560, 220)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        location = self.root if self.root is not None else "(not a repository)"
        outer.pack_start(
            Gtk.Label(label=f"Publish: {location}", xalign=0), False, False, 0
        )

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        outer.pack_start(grid, True, True, 0)

        grid.attach(Gtk.Label(label="Repository name", xalign=0), 0, 0, 1, 1)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(default_repo_name(self.root))
        self.name_entry.set_hexpand(True)
        grid.attach(self.name_entry, 1, 0, 1, 1)

        self.private_check = Gtk.CheckButton(label="Private repository")
        self.private_check.set_active(True)
        grid.attach(self.private_check, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Account", xalign=0), 0, 2, 1, 1)
        account_label = Gtk.Label(
            label=self.active_account or "(gh not configured)", xalign=0
        )
        account_label.set_selectable(True)
        grid.attach(account_label, 1, 2, 1, 1)

        buttons = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_layout(Gtk.ButtonBoxStyle.END)
        buttons.set_spacing(8)
        outer.pack_start(buttons, False, False, 0)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        buttons.add(self.cancel_button)

        self.publish_button = Gtk.Button(label="Publish")
        self.publish_button.get_style_context().add_class("suggested-action")
        self.publish_button.connect("clicked", self.on_publish_clicked)
        buttons.add(self.publish_button)

    def repository_name(self) -> str:
        return self.name_entry.get_text().strip()

    def on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self.destroy()

    def on_publish_clicked(self, _button: Gtk.Button) -> None:
        if self.root is None:
            self.show_error("This directory is not a Git repository.")
            return
        error = validate_repo_name(self.repository_name())
        if error:
            self.show_error(error)
            return

        phases = publish_phases(
            self.forge,
            self.root,
            self.repository_name(),
            self.private_check.get_active(),
        )
        window = logger.LoggerWindow(
            f"Publish to {self.forge.label}",
            phases,
            on_complete=self.on_publish_logger_complete,
        )
        self.active_logger = window
        window.connect("destroy", self.on_publish_logger_destroyed)
        window.set_transient_for(self)
        window.show_all()
        self.publish_button.set_sensitive(False)
        self.cancel_button.set_sensitive(False)
        self.set_deletable(False)

    def on_publish_logger_complete(self, ok: bool, _returncodes: list[int]) -> None:
        if ok:
            self.publish_completed = True
            self.hide()
            return
        self.set_deletable(True)
        self.cancel_button.set_sensitive(True)
        self.publish_button.set_sensitive(True)

    def on_publish_logger_destroyed(self, _window: logger.LoggerWindow) -> None:
        self.active_logger = None
        if self.publish_completed:
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


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:], forge_id="github"))
