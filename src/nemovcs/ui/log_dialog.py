"""GTK3 revision log dialog.

Replaces the plain text `git log` dump with a revision browser: a table of
revisions, the selected revision's message, and its changed paths, backed by
the structured `backends.scan_log` model.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
import sys
from typing import Sequence

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from gi.repository import Pango  # noqa: E402

from nemovcs import backends
from nemovcs.backends.base import LogChange, LogEntry


COL_REVISION = 0
COL_AUTHOR = 1
COL_DATE = 2
COL_SUMMARY = 3
COL_ENTRY = 4

CH_ACTION = 0
CH_PATH = 1
CH_CHANGE = 2

DEFAULT_LIMIT = 50
PAGE_SIZE = 50
SHORT_REVISION_LENGTH = 10


def run(paths: Sequence[str], limit: int = DEFAULT_LIMIT) -> int:
    window = LogDialog(paths or ["."], limit=limit)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


def short_revision(revision: str, length: int = SHORT_REVISION_LENGTH) -> str:
    return revision[:length]


def format_date(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    return parsed.strftime("%Y-%m-%d %H:%M")


def message_text(entry: LogEntry) -> str:
    if entry.body.strip():
        return f"{entry.summary}\n\n{entry.body.strip()}"
    return entry.summary


def changed_path_label(change: LogChange) -> str:
    if change.old_path:
        return f"{change.path} (from {change.old_path})"
    return change.path


def revision_row(entry: LogEntry) -> list[object]:
    return [
        short_revision(entry.revision),
        entry.author,
        format_date(entry.date),
        entry.summary,
        entry,
    ]


def changed_row(change: LogChange) -> list[object]:
    return [change.action, changed_path_label(change), change]


def log_filter_paths(paths: Sequence[str], root: str | Path) -> tuple[str, ...]:
    root_path = Path(root).resolve(strict=False)
    relpaths: list[str] = []
    seen: set[str] = set()

    for path in paths:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve(strict=False)

        try:
            relpath = candidate.relative_to(root_path)
        except ValueError:
            continue

        reltext = "." if str(relpath) == "." else relpath.as_posix()
        if reltext == ".":
            return ()
        if reltext not in seen:
            seen.add(reltext)
            relpaths.append(reltext)

    return tuple(relpaths)


def git_revision_diff_command(root: Path, revision: str) -> list[str]:
    return [
        "git",
        "-C",
        str(root),
        "difftool",
        "-d",
        "--tool=meld",
        "--no-prompt",
        f"{revision}~1",
        revision,
    ]


def git_revision_file_diff_command(root: Path, revision: str, path: str) -> list[str]:
    return [
        "git",
        "-C",
        str(root),
        "difftool",
        "--tool=meld",
        "--no-prompt",
        f"{revision}~1",
        revision,
        "--",
        path,
    ]


class LogDialog(Gtk.Window):
    def __init__(self, paths: Sequence[str], *, limit: int = DEFAULT_LIMIT):
        super().__init__(title="Log")
        self.paths = list(paths)
        self.path = self.paths[0] if self.paths else "."
        self.limit = limit
        self.exit_code = 0
        self.backend_id = ""
        self.root: Path | None = None

        self.set_default_size(940, 660)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        outer.pack_start(header, False, False, 0)

        self.header_label = Gtk.Label(label="Loading...", xalign=0)
        self.header_label.set_selectable(True)
        header.pack_start(self.header_label, True, True, 0)

        self.show_more_button = Gtk.Button(label="Show more")
        self.show_more_button.set_tooltip_text("Load more revisions")
        self.show_more_button.connect("clicked", self.on_show_more_clicked)
        header.pack_start(self.show_more_button, False, False, 0)

        refresh = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Refresh")
        refresh.connect("clicked", self.on_refresh_clicked)
        header.pack_start(refresh, False, False, 0)

        vsplit = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        vsplit.set_position(340)
        outer.pack_start(vsplit, True, True, 0)

        self.store = Gtk.ListStore(str, str, str, str, object)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.tree.connect("row-activated", self.on_revision_activated)
        self.tree.get_selection().connect("changed", self.on_revision_selected)

        for title, column_id, min_width in (
            ("Revision", COL_REVISION, 110),
            ("Author", COL_AUTHOR, 150),
            ("Date", COL_DATE, 140),
            ("Summary", COL_SUMMARY, 420),
        ):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(title, renderer, text=column_id)
            column.set_resizable(True)
            column.set_min_width(min_width)
            column.set_sort_column_id(column_id)
            self.tree.append_column(column)

        revisions_scroll = Gtk.ScrolledWindow()
        revisions_scroll.set_shadow_type(Gtk.ShadowType.IN)
        revisions_scroll.add(self.tree)
        vsplit.pack1(revisions_scroll, resize=True, shrink=False)

        hsplit = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        hsplit.set_position(520)
        vsplit.pack2(hsplit, resize=True, shrink=False)

        self.message_view = Gtk.TextView()
        self.message_view.set_editable(False)
        self.message_view.set_cursor_visible(False)
        self.message_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.message_view.set_left_margin(6)
        self.message_view.set_right_margin(6)
        self.message_buffer = self.message_view.get_buffer()

        message_scroll = Gtk.ScrolledWindow()
        message_scroll.set_shadow_type(Gtk.ShadowType.IN)
        message_scroll.add(self.message_view)
        hsplit.pack1(message_scroll, resize=True, shrink=False)

        self.changes_store = Gtk.ListStore(str, str, object)
        self.changes_tree = Gtk.TreeView(model=self.changes_store)
        self.changes_tree.set_headers_visible(True)
        self.changes_tree.connect("row-activated", self.on_change_activated)

        for title, column_id, min_width in (
            ("Action", CH_ACTION, 90),
            ("Path", CH_PATH, 320),
        ):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(title, renderer, text=column_id)
            column.set_resizable(True)
            column.set_min_width(min_width)
            self.changes_tree.append_column(column)

        changes_scroll = Gtk.ScrolledWindow()
        changes_scroll.set_shadow_type(Gtk.ShadowType.IN)
        changes_scroll.add(self.changes_tree)
        hsplit.pack2(changes_scroll, resize=True, shrink=False)

        buttons = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_layout(Gtk.ButtonBoxStyle.END)
        buttons.set_spacing(8)
        outer.pack_start(buttons, False, False, 0)

        close = Gtk.Button(label="Close")
        close.connect("clicked", self.on_close_clicked)
        buttons.add(close)

        self.load_log()

    def load_log(self) -> None:
        self.store.clear()
        self.changes_store.clear()
        self.message_buffer.set_text("")

        detected = backends.detect_root(self.path)
        if detected is None:
            self.header_label.set_text("Not inside a versioned working tree.")
            self.show_more_button.set_sensitive(False)
            self.exit_code = 1
            return

        backend, root = detected
        self.backend_id = backend.id
        self.root = root

        result = backend.scan_log(
            root,
            limit=self.limit,
            paths=log_filter_paths(self.paths, root),
        )
        if not result.ok:
            self.header_label.set_text("Failed to read log.")
            self.message_buffer.set_text(result.error)
            self.exit_code = 1
            return

        for entry in result.entries:
            self.store.append(revision_row(entry))

        count = len(result.entries)
        self.header_label.set_text(f"{count} revision(s) — {root.name or str(root)}")
        self.show_more_button.set_sensitive(count >= self.limit)
        self.exit_code = 0

        first = self.store.get_iter_first()
        if first is not None:
            self.tree.get_selection().select_iter(first)

    def selected_entry(self) -> LogEntry | None:
        model, tree_iter = self.tree.get_selection().get_selected()
        if tree_iter is None:
            return None
        return model[tree_iter][COL_ENTRY]

    def on_revision_selected(self, _selection: Gtk.TreeSelection) -> None:
        self.changes_store.clear()
        entry = self.selected_entry()
        if entry is None:
            self.message_buffer.set_text("")
            return
        self.message_buffer.set_text(message_text(entry))
        for change in entry.changes:
            self.changes_store.append(changed_row(change))

    def on_revision_activated(
        self,
        _tree: Gtk.TreeView,
        path: Gtk.TreePath,
        _column: Gtk.TreeViewColumn,
    ) -> None:
        entry = self.store[self.store.get_iter(path)][COL_ENTRY]
        self.open_revision_diff(entry)

    def on_change_activated(
        self,
        _tree: Gtk.TreeView,
        path: Gtk.TreePath,
        _column: Gtk.TreeViewColumn,
    ) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        change = self.changes_store[self.changes_store.get_iter(path)][CH_CHANGE]
        self.open_file_diff(entry, change)

    def open_revision_diff(self, entry: LogEntry) -> None:
        if self.backend_id != "git" or self.root is None:
            self.show_error("Per-revision diff is only available for Git so far.")
            return
        self.spawn(git_revision_diff_command(self.root, entry.revision))

    def open_file_diff(self, entry: LogEntry, change: LogChange) -> None:
        if self.backend_id != "git" or self.root is None:
            self.show_error("Per-revision diff is only available for Git so far.")
            return
        if change.action == "deleted":
            self.show_error("Deleted paths do not have a diff at this revision.")
            return
        self.spawn(
            git_revision_file_diff_command(self.root, entry.revision, change.path)
        )

    def on_show_more_clicked(self, _button: Gtk.Button) -> None:
        self.limit += PAGE_SIZE
        self.load_log()

    def on_refresh_clicked(self, _button: Gtk.Button) -> None:
        self.load_log()

    def on_close_clicked(self, _button: Gtk.Button) -> None:
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

    def spawn(self, command: Sequence[str]) -> None:
        try:
            subprocess.Popen(command)
        except OSError as exc:
            self.show_error(str(exc))


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
