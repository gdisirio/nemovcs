"""Reusable GTK3 command logger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import threading
from typing import Callable, Sequence

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


CompleteCallback = Callable[[bool, list[int]], None]


@dataclass(frozen=True)
class CommandPhase:
    title: str
    cwd: Path
    command: tuple[str, ...]

    @classmethod
    def git(cls, title: str, cwd: str | Path, args: Sequence[str]) -> "CommandPhase":
        cwd_path = Path(cwd)
        return cls(title, cwd_path, ("git", "-C", str(cwd_path), *args))


def run(title: str, phases: Sequence[CommandPhase]) -> int:
    exit_code = 1

    def on_complete(ok: bool, returncodes: list[int]) -> None:
        nonlocal exit_code
        if ok:
            exit_code = 0
            return
        exit_code = next((returncode for returncode in returncodes if returncode), 1)

    window = LoggerWindow(title, phases, on_complete=on_complete)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return exit_code


class LoggerWindow(Gtk.Window):
    def __init__(
        self,
        title: str,
        phases: Sequence[CommandPhase],
        *,
        on_complete: CompleteCallback | None = None,
    ):
        super().__init__(title=title)
        self.phases = list(phases)
        self.on_complete = on_complete
        self.returncodes: list[int] = []
        self.current_process: subprocess.Popen[str] | None = None
        self.cancel_requested = False
        self.completed = False

        self.set_default_size(760, 520)
        self.set_border_width(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(outer)

        self.status_label = Gtk.Label(label="Starting...", xalign=0)
        self.status_label.set_selectable(True)
        outer.pack_start(self.status_label, False, False, 0)

        notebook = Gtk.Notebook()
        outer.pack_start(notebook, True, True, 0)

        self.summary_view = self.text_view()
        notebook.append_page(
            self.scrolled(self.summary_view),
            Gtk.Label(label="Summary"),
        )

        self.output_view = self.text_view(monospace=True)
        self.output_buffer = self.output_view.get_buffer()
        self.output_buffer.create_tag("stderr", foreground="#b00020")
        self.output_buffer.create_tag("command", foreground="#555555")
        notebook.append_page(
            self.scrolled(self.output_view),
            Gtk.Label(label="Output"),
        )

        buttons = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        buttons.set_layout(Gtk.ButtonBoxStyle.END)
        buttons.set_spacing(8)
        outer.pack_start(buttons, False, False, 0)

        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        buttons.add(self.cancel_button)

        self.close_button = Gtk.Button(label="Close")
        self.close_button.set_sensitive(False)
        self.close_button.connect("clicked", self.on_close_clicked)
        buttons.add(self.close_button)

        self.connect("delete-event", self.on_delete_event)
        GLib.idle_add(self.start)

    @staticmethod
    def text_view(*, monospace: bool = False) -> Gtk.TextView:
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_monospace(monospace)
        return view

    @staticmethod
    def scrolled(view: Gtk.TextView) -> Gtk.ScrolledWindow:
        scroll = Gtk.ScrolledWindow()
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(view)
        return scroll

    def start(self) -> bool:
        thread = threading.Thread(target=self.run_phases, daemon=True)
        thread.start()
        return False

    def run_phases(self) -> None:
        ok = True
        for phase in self.phases:
            if self.cancel_requested:
                ok = False
                break
            returncode = self.run_phase(phase)
            self.returncodes.append(returncode)
            if returncode != 0:
                ok = False
                break

        if self.cancel_requested:
            ok = False
        GLib.idle_add(self.finish, ok)

    def run_phase(self, phase: CommandPhase) -> int:
        GLib.idle_add(self.phase_started, phase)
        try:
            process = subprocess.Popen(
                phase.command,
                cwd=str(phase.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            GLib.idle_add(self.append_summary, f"{phase.title}: failed to start\n")
            GLib.idle_add(self.append_output, f"{exc}\n", "stderr")
            return 127

        self.current_process = process
        if self.cancel_requested and process.poll() is None:
            process.terminate()
        threads = [
            threading.Thread(
                target=self.read_pipe,
                args=(process.stdout, "stdout"),
                daemon=True,
            ),
            threading.Thread(
                target=self.read_pipe,
                args=(process.stderr, "stderr"),
                daemon=True,
            ),
        ]
        for thread in threads:
            thread.start()

        returncode = process.wait()
        for thread in threads:
            thread.join()

        self.current_process = None
        GLib.idle_add(self.phase_finished, phase, returncode)
        return returncode

    def read_pipe(self, pipe, stream_name: str) -> None:
        if pipe is None:
            return
        with pipe:
            for line in pipe:
                GLib.idle_add(self.append_output, line, stream_name)

    def phase_started(self, phase: CommandPhase) -> bool:
        self.status_label.set_text(phase.title)
        self.append_summary(f"{phase.title}\n")
        self.append_summary(f"  cwd: {phase.cwd}\n")
        command = shlex.join(phase.command)
        self.append_summary(f"  command: {command}\n")
        self.append_output(f"$ {command}\n", "command")
        return False

    def phase_finished(self, phase: CommandPhase, returncode: int) -> bool:
        self.append_summary(f"  exit: {returncode}\n\n")
        self.append_output(f"\n[{phase.title} exited with {returncode}]\n", "command")
        return False

    def finish(self, ok: bool) -> bool:
        self.completed = True
        self.cancel_button.set_sensitive(False)
        self.close_button.set_sensitive(True)
        self.status_label.set_text("Completed" if ok else "Failed")
        self.append_summary(
            "Completed successfully.\n" if ok else "Stopped with errors.\n"
        )
        if self.on_complete is not None:
            self.on_complete(ok, self.returncodes)
        return False

    def append_summary(self, text: str) -> bool:
        buffer = self.summary_view.get_buffer()
        self.append_to_view(self.summary_view, buffer, text)
        return False

    def append_output(self, text: str, stream_name: str) -> bool:
        tag = stream_name if stream_name in {"stderr", "command"} else None
        self.append_to_view(self.output_view, self.output_buffer, text, tag)
        return False

    @staticmethod
    def append_to_view(
        view: Gtk.TextView,
        buffer: Gtk.TextBuffer,
        text: str,
        tag: str | None = None,
    ) -> None:
        end = buffer.get_end_iter()
        if tag is None:
            buffer.insert(end, text)
        else:
            buffer.insert_with_tags_by_name(end, text, tag)
        end = buffer.get_end_iter()
        view.scroll_to_iter(end, 0.0, False, 0.0, 1.0)

    def on_cancel_clicked(self, _button: Gtk.Button) -> None:
        self.request_cancel()

    def on_delete_event(self, *_args: object) -> bool:
        if self.completed:
            return False
        self.request_cancel()
        return True

    def request_cancel(self) -> None:
        if self.cancel_requested:
            return
        self.cancel_requested = True
        process = self.current_process
        if process is not None and process.poll() is None:
            process.terminate()
        self.status_label.set_text("Canceling...")
        self.append_summary("Cancel requested.\n")

    def on_close_clicked(self, _button: Gtk.Button) -> None:
        self.destroy()
