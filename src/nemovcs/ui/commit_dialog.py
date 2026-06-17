"""GTK3 commit dialog."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402
from gi.repository import Pango  # noqa: E402

from nemovcs import git


COL_INCLUDED = 0
COL_STATUS = 1
COL_INDEX = 2
COL_WORKTREE = 3
COL_PATH = 4
COL_OLD_PATH = 5
COL_ITEM = 6


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
        self.items: list[git.CommitItem] = []

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

        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        paned.pack2(files_box, resize=True, shrink=False)

        files_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
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

        self.store = Gtk.ListStore(bool, str, str, str, str, str, object)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.tree.connect("row-activated", self.on_row_activated)
        self.tree.connect("button-press-event", self.on_tree_button_press)

        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.on_include_toggled)
        include_col = Gtk.TreeViewColumn("Include", toggle, active=COL_INCLUDED)
        self.tree.append_column(include_col)

        for title, column, width in (
            ("Status", COL_STATUS, 110),
            ("Staged", COL_INDEX, 70),
            ("Unstaged", COL_WORKTREE, 80),
            ("Path", COL_PATH, 360),
            ("Old Path", COL_OLD_PATH, 220),
        ):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            tree_col = Gtk.TreeViewColumn(title, renderer, text=column)
            tree_col.set_resizable(True)
            tree_col.set_min_width(width)
            tree_col.set_sort_column_id(column)
            self.tree.append_column(tree_col)

        scroll = Gtk.ScrolledWindow()
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        files_box.pack_start(scroll, True, True, 0)

        button_box = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_layout(Gtk.ButtonBoxStyle.END)
        button_box.set_spacing(8)
        outer.pack_start(button_box, False, False, 0)

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self.on_cancel_clicked)
        button_box.add(cancel)

        self.commit_button = Gtk.Button(label="Commit")
        self.commit_button.get_style_context().add_class("suggested-action")
        self.commit_button.connect("clicked", self.on_commit_clicked)
        button_box.add(self.commit_button)

        self.load_items()

    def load_items(self) -> None:
        self.store.clear()
        items_by_root = git.commit_items(self.paths)
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
            f"Repository: {self.root}    Branch: {git.current_branch(self.root)}"
        )

        for item in self.items:
            self.store.append(
                [
                    item.default_selected,
                    item.status,
                    self._status_char(item.index_status),
                    self._status_char(item.worktree_status),
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

    def selected_items(self) -> list[git.CommitItem]:
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
            item: git.CommitItem = row[COL_ITEM]
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
            item: git.CommitItem = row[COL_ITEM]
            row[COL_INCLUDED] = not item.conflicted

    def on_select_none_clicked(self, _button: Gtk.Button) -> None:
        for row in self.store:
            row[COL_INCLUDED] = False

    def on_include_toggled(self, _renderer: Gtk.CellRendererToggle, path: str) -> None:
        row = self.store[path]
        item: git.CommitItem = row[COL_ITEM]
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

        results = git.commit_paths(self.root, relpaths, message)
        failed = [result for result in results if not result.ok]
        if failed:
            result = failed[-1]
            self.show_error(result.stderr.strip() or result.stdout.strip())
            return

        detail = results[-1].stdout.strip() if results else ""
        self.show_info("Commit completed.", detail)
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
        for label, callback in (
            ("Include / Exclude", self.on_context_toggle),
            ("Diff with Meld", self.on_context_diff),
            ("Open File", self.on_context_open),
            ("Show in Nemo", self.on_context_show_in_nemo),
            ("Copy Relative Path", self.on_context_copy_path),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", callback)
            menu.append(item)
        menu.show_all()
        return menu

    def on_context_toggle(self, _item: Gtk.MenuItem) -> None:
        for iter_ in self.selected_iters():
            item: git.CommitItem = self.store[iter_][COL_ITEM]
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

    def open_diff(self, item: git.CommitItem) -> None:
        if item.status == "untracked":
            self.show_error("Untracked files do not have a Git diff yet.")
            return
        if self.root is None:
            return
        self.spawn(
            [
                "git",
                "-C",
                str(self.root),
                "difftool",
                "--tool=meld",
                "--dir-diff",
                "--no-prompt",
                "--",
                item.path,
            ]
        )

    def absolute_path(self, item: git.CommitItem) -> Path:
        return item.root / item.path

    def spawn(self, command: Sequence[str]) -> None:
        try:
            subprocess.Popen(command)
        except OSError as exc:
            self.show_error(str(exc))

    @staticmethod
    def _status_char(value: str) -> str:
        return "" if value == "." else value


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
