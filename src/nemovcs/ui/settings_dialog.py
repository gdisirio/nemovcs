"""GTK3 settings panel."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
from typing import Callable, Sequence

import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402


COL_STATUS_ICON = 0
COL_STATUS = 1
COL_PATH = 2
COL_BACKEND = 3
COL_WORKTREE = 4
NAV_LABEL = 0
NAV_PAGE = 1
NAV_ICON = 2
ICON_SIZE = 20
RESOURCE_ROOT = Path(__file__).resolve().parents[3] / "rsc" / "icons" / "nemovcs"
STATUS_ICON_NAMES = {
    "conflicted": "emblem-nemovcs-conflicted-small.svg",
    "error": "emblem-nemovcs-conflicted-small.svg",
    "loading": "emblem-nemovcs-normal-small.svg",
    "modified": "emblem-nemovcs-modified-small.svg",
    "ok": "emblem-nemovcs-normal-small.svg",
    "stale": "emblem-nemovcs-modified-small.svg",
    "unversioned": "emblem-nemovcs-unversioned-small.svg",
}


StatusRecord = dict[str, str]
SettingsRecord = dict[str, str]
CacheEntriesFunc = Callable[[], Sequence[StatusRecord]]
SettingsFunc = Callable[[], SettingsRecord]
SaveSettingsFunc = Callable[[SettingsRecord], SettingsRecord]


def run() -> int:
    window = SettingsDialog()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return 0


class SettingsDialog(Gtk.Window):
    def __init__(self):
        super().__init__(title="NemoVCS Settings")
        self.set_default_size(920, 560)
        self.set_border_width(12)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        self.nav_store = navigation_model()
        self.nav_tree = Gtk.TreeView(model=self.nav_store)
        self.nav_tree.set_headers_visible(False)
        self.nav_tree.set_size_request(270, -1)
        column = Gtk.TreeViewColumn("Group")
        icon_renderer = Gtk.CellRendererPixbuf()
        column.pack_start(icon_renderer, False)
        column.add_attribute(icon_renderer, "icon-name", NAV_ICON)
        text_renderer = Gtk.CellRendererText()
        column.pack_start(text_renderer, True)
        column.add_attribute(text_renderer, "text", NAV_LABEL)
        self.nav_tree.append_column(column)
        self.nav_tree.expand_all()
        self.nav_tree.get_selection().connect("changed", self.on_nav_selected)
        paned.pack1(self.nav_tree, resize=False, shrink=False)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(StatusdStatusPage(), "statusd-status")
        self.stack.add_named(StatusdSettingsPage(), "statusd-settings")
        paned.pack2(self.stack, resize=True, shrink=False)

        first_child = self.nav_store.iter_children(self.nav_store.get_iter_first())
        if first_child is not None:
            self.nav_tree.get_selection().select_iter(first_child)

    def on_nav_selected(self, selection: Gtk.TreeSelection) -> None:
        model, iter_ = selection.get_selected()
        if iter_ is None:
            return
        page_name = model[iter_][NAV_PAGE]
        if page_name:
            self.stack.set_visible_child_name(page_name)


class StatusdStatusPage(Gtk.Box):
    def __init__(
        self,
        *,
        cache_entries: CacheEntriesFunc | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_border_width(8)
        self.cache_entries = cache_entries or default_cache_entries
        self.status_icon_cache: dict[str, GdkPixbuf.Pixbuf | None] = {}

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.pack_start(header, False, False, 0)

        title = Gtk.Label(label="Status", xalign=0)
        title.get_style_context().add_class("title")
        header.pack_start(title, True, True, 0)

        refresh = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Refresh")
        refresh.connect("clicked", self.on_refresh_clicked)
        header.pack_start(refresh, False, False, 0)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.set_selectable(True)
        self.pack_start(self.status_label, False, False, 0)

        self.store = Gtk.ListStore(
            GdkPixbuf.Pixbuf,
            str,
            str,
            str,
            str,
        )
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.add_status_column()
        self.add_text_column("Path", COL_PATH, min_width=420, expand=True)
        self.add_text_column("Backend", COL_BACKEND, min_width=90)
        self.add_text_column("Worktree", COL_WORKTREE, min_width=220)

        scroll = Gtk.ScrolledWindow()
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        self.pack_start(scroll, True, True, 0)

        self.load_cache_entries()

    def add_status_column(self) -> None:
        column = Gtk.TreeViewColumn("Status")
        icon_renderer = Gtk.CellRendererPixbuf()
        column.pack_start(icon_renderer, False)
        column.add_attribute(icon_renderer, "pixbuf", COL_STATUS_ICON)
        text_renderer = Gtk.CellRendererText()
        column.pack_start(text_renderer, True)
        column.add_attribute(text_renderer, "text", COL_STATUS)
        column.set_resizable(True)
        column.set_min_width(140)
        column.set_sort_column_id(COL_STATUS)
        self.tree.append_column(column)

    def add_text_column(
        self,
        title: str,
        column_id: int,
        *,
        min_width: int,
        expand: bool = False,
    ) -> None:
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(title, renderer, text=column_id)
        column.set_resizable(True)
        column.set_min_width(min_width)
        column.set_expand(expand)
        column.set_sort_column_id(column_id)
        self.tree.append_column(column)

    def load_cache_entries(self) -> None:
        self.store.clear()
        try:
            records = list(self.cache_entries())
        except Exception as exc:
            self.status_label.set_text(f"Unable to read status cache: {exc}")
            return

        for record in sorted(records, key=cache_record_sort_key):
            status = record.get("status", "")
            self.store.append(
                [
                    self.status_icon(status),
                    status,
                    record.get("path", ""),
                    record.get("backend", ""),
                    record.get("worktree_id", ""),
                ]
            )

        count = len(records)
        self.status_label.set_text(
            f"{count} cached worktree(s)." if count else "No cached worktrees."
        )

    def on_refresh_clicked(self, _button: Gtk.Button) -> None:
        self.load_cache_entries()

    def status_icon(self, status: str) -> GdkPixbuf.Pixbuf | None:
        if status not in self.status_icon_cache:
            icon_name = STATUS_ICON_NAMES.get(
                status,
                "emblem-nemovcs-modified-small.svg",
            )
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


class StatusdSettingsPage(Gtk.Box):
    def __init__(
        self,
        *,
        status_settings: SettingsFunc | None = None,
        save_settings: SaveSettingsFunc | None = None,
        restart_status: Callable[[], int] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_border_width(8)
        self.set_size_request(560, -1)
        self.status_settings = status_settings or default_status_settings
        self.save_settings = save_settings or default_save_settings
        self.restart_status = restart_status or restart_status_process

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.pack_start(header, False, False, 0)

        title = Gtk.Label(label="Settings", xalign=0)
        title.get_style_context().add_class("title")
        header.pack_start(title, True, True, 0)

        button_box = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_layout(Gtk.ButtonBoxStyle.END)
        button_box.set_spacing(8)
        button_box.set_size_request(280, -1)
        header.pack_start(button_box, False, False, 0)

        restart = Gtk.Button(label="Restart Status Process")
        restart.set_size_request(170, -1)
        restart.connect("clicked", self.on_restart_clicked)
        button_box.add(restart)

        save = Gtk.Button(label="Save")
        save.set_size_request(90, -1)
        save.get_style_context().add_class("suggested-action")
        save.connect("clicked", self.on_save_clicked)
        button_box.add(save)

        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.pack_start(grid, False, False, 0)

        self.cache_size_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.cache_size_spin.set_numeric(True)
        self.cache_size_spin.set_digits(0)
        self.debounce_spin = Gtk.SpinButton.new_with_range(0, 60, 0.05)
        self.debounce_spin.set_numeric(True)
        self.debounce_spin.set_digits(2)
        self.scan_ttl_spin = Gtk.SpinButton.new_with_range(0, 3600, 1)
        self.scan_ttl_spin.set_numeric(True)
        self.scan_ttl_spin.set_digits(0)
        self.cache_size_spin.set_size_request(120, -1)
        self.debounce_spin.set_size_request(120, -1)
        self.scan_ttl_spin.set_size_request(120, -1)
        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.set_selectable(True)
        self.status_label.set_line_wrap(True)
        self.status_label.set_size_request(520, 44)

        grid.attach(Gtk.Label(label="Cache Size", xalign=0), 0, 0, 1, 1)
        grid.attach(self.cache_size_spin, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Status Refresh Delay", xalign=0), 0, 1, 1, 1)
        grid.attach(self.debounce_spin, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Scan TTL", xalign=0), 0, 2, 1, 1)
        grid.attach(self.scan_ttl_spin, 1, 2, 1, 1)
        grid.attach(self.status_label, 0, 3, 2, 1)

        self.load_status_settings()

    def load_status_settings(self) -> None:
        try:
            settings = self.status_settings()
        except Exception as exc:
            self.status_label.set_text(f"Unable to read status settings: {exc}")
            return

        self.apply_status_settings(settings)
        self.status_label.set_text("")

    def apply_status_settings(self, settings: SettingsRecord) -> None:
        self.cache_size_spin.set_value(
            parse_int(settings.get("max_worktrees", "12"), fallback=12)
        )
        self.debounce_spin.set_value(
            parse_float(settings.get("debounce_seconds", "0.75"), fallback=0.75)
        )
        self.scan_ttl_spin.set_value(
            parse_float(settings.get("scan_ttl_seconds", "15"), fallback=15)
        )

    def settings_payload(self) -> SettingsRecord:
        return {
            "max_worktrees": str(self.cache_size_spin.get_value_as_int()),
            "debounce_seconds": f"{self.debounce_spin.get_value():g}",
            "scan_ttl_seconds": f"{self.scan_ttl_spin.get_value():g}",
        }

    def on_save_clicked(self, _button: Gtk.Button) -> None:
        try:
            saved = self.save_settings(self.settings_payload())
        except Exception as exc:
            self.status_label.set_text(f"Unable to save status settings: {exc}")
            return

        self.apply_status_settings(saved)
        path = saved.get("config_path", "")
        self.status_label.set_text(f"Saved settings to {path}" if path else "Saved settings.")

    def on_restart_clicked(self, _button: Gtk.Button) -> None:
        stopped = self.restart_status()
        self.status_label.set_text(f"Restarted status process; stopped {stopped}.")
        GLib.timeout_add(750, self.reload_after_restart)

    def reload_after_restart(self) -> bool:
        self.load_status_settings()
        return False


def navigation_model() -> Gtk.TreeStore:
    store = Gtk.TreeStore(str, str, str)
    statusd_iter = store.append(None, ["Statusd", "", "nemovcs-status"])
    store.append(statusd_iter, ["Status", "statusd-status", "nemovcs-normal"])
    store.append(statusd_iter, ["Settings", "statusd-settings", "nemovcs-settings"])
    return store


def default_cache_entries() -> list[StatusRecord]:
    from nemovcs import statusd_dbus

    return statusd_dbus.call_cache_entries()


def default_status_settings() -> SettingsRecord:
    from nemovcs import statusd_dbus

    return statusd_dbus.call_settings()


def default_save_settings(settings: SettingsRecord) -> SettingsRecord:
    from nemovcs import statusd_dbus

    return statusd_dbus.call_set_settings(settings)


def restart_status_process() -> int:
    stopped = 0
    for pid in statusd_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        stopped += 1
    return stopped


def statusd_pids() -> list[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python3 -m nemovcs statusd"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return []

    current_pid = os.getpid()
    pids: list[int] = []
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != current_pid:
            pids.append(pid)
    return pids


def cache_record_sort_key(record: StatusRecord) -> tuple[str, str]:
    return (record.get("worktree_id", ""), record.get("path", ""))


def format_seconds(value: str) -> str:
    try:
        seconds = float(value)
    except ValueError:
        return "unknown"
    return f"{seconds:g} seconds"


def parse_int(value: str, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def parse_float(value: str, *, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


if __name__ == "__main__":
    raise SystemExit(run())
