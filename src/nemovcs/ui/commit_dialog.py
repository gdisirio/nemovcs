"""GTK3 commit dialog."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
from gi.repository import GdkPixbuf  # noqa: E402
from gi.repository import Pango  # noqa: E402

from nemovcs import backends
from nemovcs.backends.base import BackendChangeItem, BackendCommandPhase
from nemovcs.ui import logger


COL_INCLUDED = 0
COL_STATUS_ICON = 1
COL_STATUS = 2
COL_ICON = 3
COL_PATH = 4
COL_OLD_PATH = 5
COL_ITEM = 6
ICON_SIZE = 20
RESOURCE_ROOT = Path(__file__).resolve().parents[3] / "rsc" / "icons" / "nemovcs"
STATUS_ICON_NAMES = {
    "added": "emblem-nemovcs-added.svg",
    "changed": "emblem-nemovcs-modified.svg",
    "conflicted": "emblem-nemovcs-conflicted.svg",
    "deleted": "emblem-nemovcs-deleted.svg",
    "modified": "emblem-nemovcs-modified.svg",
    "renamed": "emblem-nemovcs-modified.svg",
    "untracked": "emblem-nemovcs-unversioned.svg",
}


def run(paths: Sequence[str]) -> int:
    window = CommitDialog(paths or ["."])
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


class CommitDialog(Gtk.Window):
    def __init__(self, paths: Sequence[str]):
        super().__init__(title="Commit")
        self.paths = list(paths)
        self.exit_code = 0
        self.root: Path | None = None
        self.items: list[BackendChangeItem] = []
        self.active_logger: logger.LoggerWindow | None = None
        self.commit_completed = False
        self.icon_theme = Gtk.IconTheme.get_default()
        self.icon_cache: dict[str, GdkPixbuf.Pixbuf | None] = {}
        self.status_icon_cache: dict[str, GdkPixbuf.Pixbuf | None] = {}

        self.set_default_size(860, 660)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(header, False, False, 0)

        self.repo_label = Gtk.Label(xalign=0)
        self.repo_label.set_selectable(True)
        header.pack_start(self.repo_label, True, True, 0)

        refresh = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Refresh")
        refresh.connect("clicked", self.on_refresh_clicked)
        header.pack_start(refresh, False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        outer.pack_start(paned, True, True, 0)

        message_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        paned.pack1(message_box, resize=False, shrink=False)

        message_label = Gtk.Label(label="Commit Message", xalign=0)
        message_box.pack_start(message_label, False, False, 0)

        message_scroll = Gtk.ScrolledWindow()
        message_scroll.set_shadow_type(Gtk.ShadowType.IN)
        message_scroll.set_min_content_height(145)
        message_box.pack_start(message_scroll, True, True, 0)

        self.message_view = Gtk.TextView()
        self.message_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.message_view.set_accepts_tab(False)
        message_scroll.add(self.message_view)

        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        files_box.set_margin_top(14)
        paned.pack2(files_box, resize=True, shrink=False)

        files_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        files_box.pack_start(files_header, False, False, 0)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_selectable(True)
        files_header.pack_start(self.status_label, True, True, 0)

        select_all = Gtk.Button(label="Select All")
        select_all.connect("clicked", self.on_select_all_clicked)
        files_header.pack_start(select_all, False, False, 0)

        select_none = Gtk.Button(label="Select None")
        select_none.connect("clicked", self.on_select_none_clicked)
        files_header.pack_start(select_none, False, False, 0)

        self.store = Gtk.ListStore(
            bool,
            GdkPixbuf.Pixbuf,
            str,
            GdkPixbuf.Pixbuf,
            str,
            str,
            object,
        )
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.tree.connect("row-activated", self.on_row_activated)
        self.tree.connect("button-press-event", self.on_tree_button_press)

        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.on_include_toggled)
        include_col = Gtk.TreeViewColumn("Include", toggle, active=COL_INCLUDED)
        self.tree.append_column(include_col)

        status_col = Gtk.TreeViewColumn("Status")
        status_icon_renderer = Gtk.CellRendererPixbuf()
        status_col.pack_start(status_icon_renderer, False)
        status_col.add_attribute(status_icon_renderer, "pixbuf", COL_STATUS_ICON)
        status_renderer = Gtk.CellRendererText()
        status_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        status_col.pack_start(status_renderer, True)
        status_col.add_attribute(status_renderer, "text", COL_STATUS)
        status_col.set_resizable(True)
        status_col.set_min_width(130)
        status_col.set_sort_column_id(COL_STATUS)
        self.tree.append_column(status_col)

        path_col = Gtk.TreeViewColumn("Path")
        icon_renderer = Gtk.CellRendererPixbuf()
        path_col.pack_start(icon_renderer, False)
        path_col.add_attribute(icon_renderer, "pixbuf", COL_ICON)
        path_renderer = Gtk.CellRendererText()
        path_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        path_col.pack_start(path_renderer, True)
        path_col.add_attribute(path_renderer, "text", COL_PATH)
        path_col.set_resizable(True)
        path_col.set_min_width(460)
        path_col.set_sort_column_id(COL_PATH)
        self.tree.append_column(path_col)

        old_path_renderer = Gtk.CellRendererText()
        old_path_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        old_path_col = Gtk.TreeViewColumn(
            "Old Path",
            old_path_renderer,
            text=COL_OLD_PATH,
        )
        old_path_col.set_resizable(True)
        old_path_col.set_min_width(220)
        old_path_col.set_sort_column_id(COL_OLD_PATH)
        self.tree.append_column(old_path_col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        files_box.pack_start(scroll, True, True, 0)

        button_box = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_layout(Gtk.ButtonBoxStyle.END)
        button_box.set_spacing(8)
        outer.pack_start(button_box, False, False, 0)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        button_box.add(self.cancel_button)

        self.commit_button = Gtk.Button(label="Commit")
        self.commit_button.get_style_context().add_class("suggested-action")
        self.commit_button.connect("clicked", self.on_commit_clicked)
        button_box.add(self.commit_button)

        self.load_items()

    def load_items(self) -> None:
        self.store.clear()
        items_by_root = backends.commit_items(self.paths)
        roots = [root for root, items in items_by_root.items() if items]
        if not roots and items_by_root:
            roots = list(items_by_root)

        if len(roots) != 1:
            self.root = None
            self.repo_label.set_text("Select paths from one Git repository.")
            self.status_label.set_text("No commit-ready repository found.")
            self.commit_button.set_sensitive(False)
            return

        self.root = roots[0]
        self.items = items_by_root.get(self.root, [])
        self.repo_label.set_text(
            f"Repository: {self.root}    Branch: {backends.current_branch(self.root)}"
        )

        for item in self.items:
            self.store.append(
                [
                    item.default_selected,
                    self.status_icon(item.status),
                    item.status,
                    self.file_icon(item),
                    item.path,
                    item.old_path or "",
                    item,
                ]
            )

        changed = sum(1 for item in self.items if item.tracked)
        untracked = sum(1 for item in self.items if not item.tracked)
        conflicted = sum(1 for item in self.items if item.conflicted)
        self.status_label.set_text(
            f"{changed} changed, {untracked} untracked, {conflicted} conflicted"
        )
        self.commit_button.set_sensitive(bool(self.items))

    def selected_iters(self) -> list[Gtk.TreeIter]:
        selection = self.tree.get_selection()
        model, paths = selection.get_selected_rows()
        return [model.get_iter(path) for path in paths]

    def selected_items(self) -> list[BackendChangeItem]:
        return [self.store[iter_][COL_ITEM] for iter_ in self.selected_iters()]

    def get_message(self) -> str:
        buffer = self.message_view.get_buffer()
        start, end = buffer.get_bounds()
        return buffer.get_text(start, end, True).strip()

    def checked_stage_paths(self) -> list[str]:
        relpaths: list[str] = []
        for row in self.store:
            if not row[COL_INCLUDED]:
                continue
            item: BackendChangeItem = row[COL_ITEM]
            relpaths.extend(item.stage_paths)
        return list(dict.fromkeys(relpaths))

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

    def show_info(self, title: str, detail: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
        )
        if detail:
            dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    def on_refresh_clicked(self, _button: Gtk.Button) -> None:
        self.load_items()

    def on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self.destroy()

    def on_select_all_clicked(self, _button: Gtk.Button) -> None:
        for row in self.store:
            item: BackendChangeItem = row[COL_ITEM]
            row[COL_INCLUDED] = not item.conflicted

    def on_select_none_clicked(self, _button: Gtk.Button) -> None:
        for row in self.store:
            row[COL_INCLUDED] = False

    def on_include_toggled(self, _renderer: Gtk.CellRendererToggle, path: str) -> None:
        row = self.store[path]
        item: BackendChangeItem = row[COL_ITEM]
        if item.conflicted:
            return
        row[COL_INCLUDED] = not row[COL_INCLUDED]

    def on_commit_clicked(self, _button: Gtk.Button) -> None:
        if self.root is None:
            self.show_error("No Git repository selected.")
            return

        message = self.get_message()
        if not message:
            self.show_error("Enter a commit message.")
            return

        relpaths = self.checked_stage_paths()
        if not relpaths:
            self.show_error("Select at least one file to commit.")
            return

        window = logger.LoggerWindow(
            "Commit",
            self.commit_phases(relpaths, message),
            on_complete=self.on_commit_logger_complete,
        )
        self.active_logger = window
        window.connect("destroy", self.on_commit_logger_destroyed)
        window.set_transient_for(self)
        window.show_all()
        self.commit_button.set_sensitive(False)
        self.cancel_button.set_sensitive(False)
        self.set_deletable(False)

    def commit_phases(
        self,
        relpaths: Sequence[str],
        message: str,
    ) -> list[BackendCommandPhase]:
        if self.root is None:
            return []
        return backends.commit_phases(self.root, relpaths, message)

    def on_commit_logger_complete(self, ok: bool, _returncodes: list[int]) -> None:
        if ok:
            self.commit_completed = True
            self.hide()
            return
        self.set_deletable(True)
        self.cancel_button.set_sensitive(True)
        self.commit_button.set_sensitive(True)
        self.load_items()

    def on_commit_logger_destroyed(self, _window: logger.LoggerWindow) -> None:
        self.active_logger = None
        if self.commit_completed:
            self.destroy()

    def on_row_activated(
        self,
        _tree: Gtk.TreeView,
        path: Gtk.TreePath,
        _column: Gtk.TreeViewColumn,
    ) -> None:
        iter_ = self.store.get_iter(path)
        self.open_diff(self.store[iter_][COL_ITEM])

    def on_tree_button_press(self, tree: Gtk.TreeView, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False

        hit = tree.get_path_at_pos(int(event.x), int(event.y))
        if hit is not None:
            path, _column, _cell_x, _cell_y = hit
            selection = tree.get_selection()
            if not selection.path_is_selected(path):
                selection.unselect_all()
                selection.select_path(path)

        menu = self.build_context_menu()
        menu.popup_at_pointer(event)
        return True

    def build_context_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()
        for label, callback, icon_name, icon_path in (
            (
                "Include / Exclude",
                self.on_context_toggle,
                "object-select-symbolic",
                None,
            ),
            (
                "Diff with Meld",
                self.on_context_diff,
                None,
                RESOURCE_ROOT / "actions" / "nemovcs-diff.svg",
            ),
            ("Open File", self.on_context_open, "document-open-symbolic", None),
            (
                "Show in Nemo",
                self.on_context_show_in_nemo,
                "folder-open-symbolic",
                None,
            ),
            (
                "Copy Relative Path",
                self.on_context_copy_path,
                "edit-copy-symbolic",
                None,
            ),
        ):
            item = Gtk.ImageMenuItem(label=label)
            item.set_always_show_image(True)
            item.set_image(self.menu_image(icon_name=icon_name, icon_path=icon_path))
            item.connect("activate", callback)
            menu.append(item)
        menu.show_all()
        return menu

    def menu_image(
        self,
        *,
        icon_name: str | None = None,
        icon_path: Path | None = None,
    ) -> Gtk.Image:
        if icon_path is not None:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    str(icon_path),
                    ICON_SIZE,
                    ICON_SIZE,
                )
                return Gtk.Image.new_from_pixbuf(pixbuf)
            except GLib.Error:
                pass

        if icon_name is not None:
            return Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)

        return Gtk.Image.new_from_icon_name("image-missing", Gtk.IconSize.MENU)

    def on_context_toggle(self, _item: Gtk.MenuItem) -> None:
        for iter_ in self.selected_iters():
            item: BackendChangeItem = self.store[iter_][COL_ITEM]
            if not item.conflicted:
                self.store[iter_][COL_INCLUDED] = not self.store[iter_][COL_INCLUDED]

    def on_context_diff(self, _item: Gtk.MenuItem) -> None:
        items = self.selected_items()
        if items:
            self.open_diff(items[0])

    def on_context_open(self, _item: Gtk.MenuItem) -> None:
        for item in self.selected_items():
            self.spawn(["xdg-open", str(self.absolute_path(item))])

    def on_context_show_in_nemo(self, _item: Gtk.MenuItem) -> None:
        for item in self.selected_items():
            self.spawn(["nemo", str(self.absolute_path(item).parent)])

    def on_context_copy_path(self, _item: Gtk.MenuItem) -> None:
        paths = "\n".join(item.path for item in self.selected_items())
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(paths, -1)

    def open_diff(self, item: BackendChangeItem) -> None:
        if item.status == "untracked":
            self.show_error("Untracked files do not have a Git diff yet.")
            return
        if self.root is None:
            return
        self.spawn(self.file_diff_command(item))

    def file_diff_command(self, item: BackendChangeItem) -> list[str]:
        if self.root is None:
            return []
        return [
            "git",
            "-C",
            str(self.root),
            "difftool",
            "--tool=meld",
            "--no-prompt",
            "HEAD",
            "--",
            item.path,
        ]

    def absolute_path(self, item: BackendChangeItem) -> Path:
        return item.root / item.path

    def file_icon(self, item: BackendChangeItem) -> GdkPixbuf.Pixbuf | None:
        path = self.absolute_path(item)
        try:
            info = Gio.File.new_for_path(str(path)).query_info(
                "standard::icon",
                Gio.FileQueryInfoFlags.NONE,
                None,
            )
            icon = info.get_icon()
            if isinstance(icon, Gio.ThemedIcon):
                icon_names = icon.get_names()
            else:
                icon_names = ["text-x-generic", "application-x-executable"]
        except GLib.Error:
            icon_names = ["text-x-generic", "unknown"]

        for icon_name in icon_names:
            if icon_name not in self.icon_cache:
                try:
                    self.icon_cache[icon_name] = self.icon_theme.load_icon(
                        icon_name,
                        ICON_SIZE,
                        Gtk.IconLookupFlags.FORCE_SIZE,
                    )
                except GLib.Error:
                    self.icon_cache[icon_name] = None
            icon_pixbuf = self.icon_cache[icon_name]
            if icon_pixbuf is not None:
                return icon_pixbuf
        return None

    def status_icon(self, status: str) -> GdkPixbuf.Pixbuf | None:
        if status not in self.status_icon_cache:
            icon_name = STATUS_ICON_NAMES.get(status, "emblem-nemovcs-modified.svg")
            icon_path = RESOURCE_ROOT / "emblems" / icon_name
            try:
                self.status_icon_cache[status] = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    str(icon_path),
                    ICON_SIZE,
                    ICON_SIZE,
                )
            except GLib.Error:
                self.status_icon_cache[status] = None
        return self.status_icon_cache[status]

    def spawn(self, command: Sequence[str]) -> None:
        try:
            subprocess.Popen(command)
        except OSError as exc:
            self.show_error(str(exc))


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
