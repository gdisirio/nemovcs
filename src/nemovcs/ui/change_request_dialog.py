"""GTK3 dialog: open a change request (pull/merge request) via a forge CLI."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nemovcs import git
from nemovcs.forge import forge_by_id
from nemovcs.ui import logger


def run(paths: Sequence[str], *, forge_id: str, action: str) -> int:
    forge = forge_by_id(forge_id)
    if forge is None:
        print(f"unknown forge: {forge_id}", file=sys.stderr)
        return 1
    if action != "cr-create":
        print(f"unknown forge dialog action: {action}", file=sys.stderr)
        return 1
    window = ChangeRequestDialog(paths or ["."], forge)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


def change_request_root(paths: Sequence[str]) -> Path | None:
    root = git.repo_root(paths[0] if paths else ".")
    return Path(root) if root is not None else None


NO_TEMPLATE = "(none)"


def validate_title(title: str) -> str:
    return "" if title.strip() else "Enter a title."


def template_body(templates, name: str | None) -> str:
    """Return the body of the named template, or "" for none/unknown."""
    if not name or name == NO_TEMPLATE:
        return ""
    return next((t.body for t in templates if t.name == name), "")


def create_phases(
    forge,
    root: Path,
    *,
    title: str,
    body: str,
    base: str | None,
) -> list[logger.CommandPhase]:
    return [
        logger.CommandPhase(
            f"Create {forge.change_request_label}",
            root,
            tuple(
                forge.change_request_create_command(
                    str(root), title=title, body=body, base=base or None
                )
            ),
        )
    ]


class ChangeRequestDialog(Gtk.Window):
    def __init__(self, paths: Sequence[str], forge):
        self.forge = forge
        self.cr_label = forge.change_request_label
        super().__init__(title=f"Create {self.cr_label}")
        self.root = change_request_root(paths)
        self.exit_code = 0
        self.active_logger: logger.LoggerWindow | None = None
        self.create_completed = False

        self.branch = git.current_branch_name(self.root) if self.root else None
        self.base = git.default_branch_name(self.root) if self.root else None
        self.templates = (
            forge.change_request_templates(str(self.root)) if self.root else []
        )

        self.set_default_size(600, 380)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        summary = self.branch or "(unknown branch)"
        into = f" into {self.base}" if self.base else ""
        outer.pack_start(
            Gtk.Label(label=f"{self.cr_label} from {summary}{into}", xalign=0),
            False,
            False,
            0,
        )

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        outer.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label="Title", xalign=0), 0, 0, 1, 1)
        self.title_entry = Gtk.Entry()
        self.title_entry.set_hexpand(True)
        grid.attach(self.title_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Base", xalign=0), 0, 1, 1, 1)
        self.base_entry = Gtk.Entry()
        self.base_entry.set_text(self.base or "")
        self.base_entry.set_placeholder_text("default branch")
        grid.attach(self.base_entry, 1, 1, 1, 1)

        self.template_combo = None
        if self.templates:
            grid.attach(Gtk.Label(label="Template", xalign=0), 0, 2, 1, 1)
            self.template_combo = Gtk.ComboBoxText()
            self.template_combo.append_text(NO_TEMPLATE)
            for template in self.templates:
                self.template_combo.append_text(template.name)
            self.template_combo.set_active(1)  # first real template
            self.template_combo.connect("changed", self.on_template_changed)
            grid.attach(self.template_combo, 1, 2, 1, 1)

        outer.pack_start(Gtk.Label(label="Description", xalign=0), False, False, 0)
        self.body_view = Gtk.TextView()
        self.body_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        body_scroll = Gtk.ScrolledWindow()
        body_scroll.set_shadow_type(Gtk.ShadowType.IN)
        body_scroll.add(self.body_view)
        outer.pack_start(body_scroll, True, True, 0)

        if self.templates:
            self.set_body_text(self.templates[0].body)

        buttons = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_layout(Gtk.ButtonBoxStyle.END)
        buttons.set_spacing(8)
        outer.pack_start(buttons, False, False, 0)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        buttons.add(self.cancel_button)

        self.create_button = Gtk.Button(label="Create")
        self.create_button.get_style_context().add_class("suggested-action")
        self.create_button.connect("clicked", self.on_create_clicked)
        buttons.add(self.create_button)

    def title_text(self) -> str:
        return self.title_entry.get_text().strip()

    def body_text(self) -> str:
        buffer = self.body_view.get_buffer()
        return buffer.get_text(
            buffer.get_start_iter(), buffer.get_end_iter(), True
        )

    def set_body_text(self, text: str) -> None:
        self.body_view.get_buffer().set_text(text)

    def on_template_changed(self, combo: Gtk.ComboBoxText) -> None:
        self.set_body_text(template_body(self.templates, combo.get_active_text()))

    def on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self.destroy()

    def on_create_clicked(self, _button: Gtk.Button) -> None:
        if self.root is None:
            self.show_error("This directory is not a Git repository.")
            return
        error = validate_title(self.title_text())
        if error:
            self.show_error(error)
            return

        phases = create_phases(
            self.forge,
            self.root,
            title=self.title_text(),
            body=self.body_text(),
            base=self.base_entry.get_text().strip(),
        )
        window = logger.LoggerWindow(
            f"Create {self.cr_label}",
            phases,
            on_complete=self.on_create_logger_complete,
        )
        self.active_logger = window
        window.connect("destroy", self.on_create_logger_destroyed)
        window.set_transient_for(self)
        window.show_all()
        self.create_button.set_sensitive(False)
        self.cancel_button.set_sensitive(False)
        self.set_deletable(False)

    def on_create_logger_complete(self, ok: bool, _returncodes: list[int]) -> None:
        if ok:
            self.create_completed = True
            self.hide()
            return
        self.set_deletable(True)
        self.cancel_button.set_sensitive(True)
        self.create_button.set_sensitive(True)

    def on_create_logger_destroyed(self, _window: logger.LoggerWindow) -> None:
        self.active_logger = None
        if self.create_completed:
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
    raise SystemExit(run(sys.argv[1:], forge_id="github", action="cr-create"))
