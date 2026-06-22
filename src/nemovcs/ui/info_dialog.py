"""Small GTK information dialogs."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nemovcs import __version__


def show_error(message: str, detail: str = "") -> None:
    dialog = Gtk.MessageDialog(
        flags=Gtk.DialogFlags.MODAL,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text=message,
    )
    if detail:
        dialog.format_secondary_text(detail)
    dialog.run()
    dialog.destroy()


def run_about() -> int:
    dialog = Gtk.AboutDialog()
    dialog.set_program_name("NemoVCS")
    dialog.set_version(__version__)
    dialog.set_comments("Git integration for the Nemo file manager.")
    dialog.set_website("https://github.com/gdisirio/nemovcs")
    dialog.set_license_type(Gtk.License.GPL_2_0)
    dialog.run()
    dialog.destroy()
    return 0


def run_settings_placeholder() -> int:
    dialog = Gtk.MessageDialog(
        flags=Gtk.DialogFlags.MODAL,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.CLOSE,
        text="NemoVCS settings are not implemented yet.",
    )
    dialog.format_secondary_text(
        "This placeholder is installed to validate the Nemo menu layout."
    )
    dialog.run()
    dialog.destroy()
    return 0

