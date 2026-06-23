"""Small GTK information dialogs."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gtk  # noqa: E402

from nemovcs import __version__


RESOURCE_ROOT = Path(__file__).resolve().parents[3] / "rsc" / "icons" / "nemovcs"
ABOUT_ICON_NAME = "nemovcs"
ABOUT_ICON_PATH = RESOURCE_ROOT / "apps" / "nemovcs.svg"


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
    dialog.set_logo_icon_name(ABOUT_ICON_NAME)
    logo = about_logo_pixbuf()
    if logo is not None:
        dialog.set_logo(logo)
    dialog.run()
    dialog.destroy()
    return 0


def about_logo_pixbuf() -> GdkPixbuf.Pixbuf | None:
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(str(ABOUT_ICON_PATH), 96, 96)
    except Exception:
        return None


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
