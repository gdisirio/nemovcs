"""Reusable modal confirmation dialog."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


def confirm(
    title: str,
    message: str,
    *,
    detail: str = "",
    ok_label: str = "Continue",
) -> bool:
    """Show a modal warning and return True only if the user accepts.

    Uses the dialog's own nested run() loop, so it works standalone before a
    Gtk.main() (e.g. from a CLI subcommand) without a parent window.
    """
    dialog = Gtk.MessageDialog(
        transient_for=None,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.NONE,
        text=title,
    )
    if detail:
        dialog.format_secondary_text(f"{message}\n\n{detail}")
    else:
        dialog.format_secondary_text(message)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    ok_button = dialog.add_button(ok_label, Gtk.ResponseType.OK)
    ok_button.get_style_context().add_class("suggested-action")
    dialog.set_default_response(Gtk.ResponseType.CANCEL)

    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK
