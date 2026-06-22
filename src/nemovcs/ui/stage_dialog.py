"""GTK3 stage dialog."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Literal, Sequence

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
COL_REPOSITORY = 4
COL_PATH = 5
COL_OLD_PATH = 6
COL_ITEM = 7
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
Operation = Literal["stage", "add"]


def run(paths: Sequence[str], *, operation: Operation = "stage") -> int:
    window = StageDialog(paths or ["."], operation=operation)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return window.exit_code


class StageDialog(Gtk.Window):
    def __init__(self, paths: Sequence[str], *, operation: Operation = "stage"):
        super().__init__(title=operation_title(operation))
        self.operation = operation
        self.paths = list(paths)
        self.exit_code = 0
        self.items_by_root: dict[Path, list[BackendChangeItem]] = {}
        self.active_logger: logger.LoggerWindow | None = None
        self.stage_completed = False
        self.icon_theme = Gtk.IconTheme.get_default()
        self.icon_cache: dict[str, GdkPixbuf.Pixbuf | None] = {}
        self.status_icon_cache: dict[str, GdkPixbuf.Pixbuf | None] = {}

        self.set_default_size(860, 560)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(header, False, False, 0)

        self.status_label = Gtk.Label(label="Loading...", xalign=0)
        self.status_label.set_selectable(True)
        header.pack_start(self.status_label, True, True, 0)

        refresh = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Refresh")
        refresh.connect("clicked", self.on_refresh_clicked)
        header.pack_start(refresh, False, False, 0)

        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.pack_start(files_box, True, True, 0)

        files_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        files_box.pack_start(files_header, False, False, 0)

        select_all = Gtk.Button(label="Select All")
        select_all.connect("clicked", self.on_select_all_clicked)
        files_header.pack_end(select_all, False, False, 0)

        select_none = Gtk.Button(label="Select None")
        select_none.connect("clicked", self.on_select_none_clicked)
        files_header.pack_end(select_none, False, False, 0)

        self.store = Gtk.ListStore(
            bool,
            GdkPixbuf.Pixbuf,
            str,
            GdkPixbuf.Pixbuf,
            str,
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

        repo_renderer = Gtk.CellRendererText()
        repo_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        repo_col = Gtk.TreeViewColumn("Repository", repo_renderer, text=COL_REPOSITORY)
        repo_col.set_resizable(True)
        repo_col.set_min_width(150)
        repo_col.set_sort_column_id(COL_REPOSITORY)
        self.tree.append_column(repo_col)

        path_col = Gtk.TreeViewColumn("Path")
        icon_renderer = Gtk.CellRendererPixbuf()
        path_col.pack_start(icon_renderer, False)
        path_col.add_attribute(icon_renderer, "pixbuf", COL_ICON)
        path_renderer = Gtk.CellRendererText()
        path_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        path_col.pack_start(path_renderer, True)
        path_col.add_attribute(path_renderer, "text", COL_PATH)
        path_col.set_resizable(True)
        path_col.set_min_width(430)
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

        buttons = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_layout(Gtk.ButtonBoxStyle.END)
        buttons.set_spacing(8)
        outer.pack_start(buttons, False, False, 0)

        self.close_button = Gtk.Button(label="Close")
        self.close_button.connect("clicked", self.on_close_clicked)
        buttons.add(self.close_button)

        self.stage_button = Gtk.Button(label=f"{operation_title(operation)} Selected")
        self.stage_button.get_style_context().add_class("suggested-action")
        self.stage_button.connect("clicked", self.on_stage_clicked)
        buttons.add(self.stage_button)

        self.load_items()

    def load_items(self) -> None:
        self.store.clear()
        self.items_by_root = backends.commit_items(self.paths)

        total = 0
        changed = 0
        untracked = 0
        conflicted = 0
        for root, items in self.items_by_root.items():
            for item in items:
                total += 1
                changed += 1 if item.tracked else 0
                untracked += 1 if not item.tracked else 0
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
                f"{changed} changed, {untracked} untracked, {conflicted} conflicted"
            )
        elif repo_count:
            self.status_label.set_text(f"No changed files in {repo_count} repository(s).")
        else:
            self.status_label.set_text("No versioned repository selected.")
            self.exit_code = 1

        self.stage_button.set_sensitive(total > 0)

    def selected_iters(self) -> list[Gtk.TreeIter]:
        selection = self.tree.get_selection()
        model, paths = selection.get_selected_rows()
        return [model.get_iter(path) for path in paths]

    def selected_items(self) -> list[BackendChangeItem]:
        return [self.store[iter_][COL_ITEM] for iter_ in self.selected_iters()]

    def checked_stage_paths_by_root(self) -> dict[Path, list[str]]:
        paths_by_root: dict[Path, list[str]] = {}
        for row in self.store:
            if not row[COL_INCLUDED]:
                continue
            item: BackendChangeItem = row[COL_ITEM]
            relpaths = paths_by_root.setdefault(item.root, [])
            for relpath in item.stage_paths:
                if relpath not in relpaths:
                    relpaths.append(relpath)
        return paths_by_root

    def stage_phases(
        self,
        paths_by_root: dict[Path, Sequence[str]],
    ) -> list[BackendCommandPhase]:
        return stage_phases(paths_by_root)

    @staticmethod
    def default_selected(item: BackendChangeItem) -> bool:
        return not item.conflicted

    def on_refresh_clicked(self, _button: Gtk.Button) -> None:
        self.load_items()

    def on_close_clicked(self, _button: Gtk.Button) -> None:
        self.destroy()

    def on_select_all_clicked(self, _button: Gtk.Button) -> None:
        for row in self.store:
            item: BackendChangeItem = row[COL_ITEM]
            row[COL_INCLUDED] = self.default_selected(item)

    def on_select_none_clicked(self, _button: Gtk.Button) -> None:
        for row in self.store:
            row[COL_INCLUDED] = False

    def on_include_toggled(self, _renderer: Gtk.CellRendererToggle, path: str) -> None:
        row = self.store[path]
        item: BackendChangeItem = row[COL_ITEM]
        if item.conflicted:
            return
        row[COL_INCLUDED] = not row[COL_INCLUDED]

    def on_stage_clicked(self, _button: Gtk.Button) -> None:
        paths_by_root = self.checked_stage_paths_by_root()
        phases = self.stage_phases(paths_by_root)
        if not phases:
            self.show_error(f"Select at least one file to {operation_verb(self.operation)}.")
            return

        window = logger.LoggerWindow(
            operation_title(self.operation),
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

    def on_stage_logger_complete(self, ok: bool, _returncodes: list[int]) -> None:
        if ok:
            self.stage_completed = True
            self.hide()
            return

        self.set_deletable(True)
        self.close_button.set_sensitive(True)
        self.stage_button.set_sensitive(True)
        self.load_items()

    def on_stage_logger_destroyed(self, _window: logger.LoggerWindow) -> None:
        self.active_logger = None
        if self.stage_completed:
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
            self.show_error("Untracked files do not have a diff yet.")
            return
        self.spawn(self.file_diff_command(item))

    def file_diff_command(self, item: BackendChangeItem) -> list[str]:
        return backends.file_diff_command(item)

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


def stage_phases(
    paths_by_root: dict[Path, Sequence[str]],
) -> list[BackendCommandPhase]:
    return backends.stage_phases(paths_by_root)


def operation_title(operation: Operation) -> str:
    return "Add" if operation == "add" else "Stage"


def operation_verb(operation: Operation) -> str:
    return "add" if operation == "add" else "stage"


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
