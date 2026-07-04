from pathlib import Path
import unittest
from unittest import mock

from nemovcs.backends.base import BackendLog, LogChange, LogEntry
from nemovcs.ui import log_dialog
from nemovcs.ui.log_dialog import (
    LogDialog,
    changed_path_label,
    changed_row,
    format_date,
    git_revision_diff_command,
    git_revision_file_diff_command,
    log_filter_paths,
    message_text,
    revision_row,
    short_revision,
)


class FakeStore:
    def __init__(self):
        self.rows: list = []
        self.cleared = 0

    def clear(self):
        self.cleared += 1
        self.rows = []

    def append(self, row):
        self.rows.append(row)

    def get_iter_first(self):
        return None


class FakeBuffer:
    def __init__(self):
        self.text = None

    def set_text(self, text):
        self.text = text


class FakeLabel:
    def __init__(self):
        self.text = None

    def set_text(self, text):
        self.text = text


class FakeButton:
    def __init__(self):
        self.sensitive = True

    def set_sensitive(self, value):
        self.sensitive = value


class FakeBackend:
    id = "git"

    def __init__(self, result):
        self._result = result
        self.limit = None
        self.paths = None

    def scan_log(self, root, *, limit, paths=()):
        self.limit = limit
        self.paths = paths
        return self._result


def make_dialog() -> LogDialog:
    dialog = LogDialog.__new__(LogDialog)
    dialog.paths = ["."]
    dialog.path = "."
    dialog.limit = 50
    dialog.exit_code = 0
    dialog.backend_id = ""
    dialog.root = None
    dialog.store = FakeStore()
    dialog.changes_store = FakeStore()
    dialog.message_buffer = FakeBuffer()
    dialog.header_label = FakeLabel()
    dialog.show_more_button = FakeButton()
    dialog.tree = None
    return dialog


class LogDialogHelpersTest(unittest.TestCase):
    def test_short_revision_truncates_git_hashes_only(self):
        self.assertEqual(short_revision("abcdef0123456789"), "abcdef0123")
        self.assertEqual(short_revision("42"), "42")

    def test_format_date_normalizes_git_and_svn_timestamps(self):
        self.assertEqual(format_date("2024-01-02T03:04:05+00:00"), "2024-01-02 03:04")
        self.assertEqual(
            format_date("2024-01-02T03:04:05.000000Z"), "2024-01-02 03:04"
        )
        self.assertEqual(format_date(""), "")
        self.assertEqual(format_date("not a date"), "not a date")

    def test_message_text_appends_body_when_present(self):
        with_body = LogEntry(
            revision="r",
            author="a",
            date="",
            summary="Subject",
            body="Line one\nLine two",
        )
        without_body = LogEntry(
            revision="r", author="a", date="", summary="Subject", body=""
        )

        self.assertEqual(message_text(with_body), "Subject\n\nLine one\nLine two")
        self.assertEqual(message_text(without_body), "Subject")

    def test_changed_path_label_shows_rename_source(self):
        self.assertEqual(
            changed_path_label(
                LogChange(action="renamed", path="new.py", old_path="old.py")
            ),
            "new.py (from old.py)",
        )
        self.assertEqual(
            changed_path_label(LogChange(action="modified", path="a.py")),
            "a.py",
        )

    def test_revision_and_changed_rows(self):
        entry = LogEntry(
            revision="abcdef0123456789",
            author="Alice",
            date="2024-01-02T03:04:05+00:00",
            summary="Add",
            body="",
        )
        self.assertEqual(
            revision_row(entry),
            ["abcdef0123", "Alice", "2024-01-02 03:04", "Add", entry],
        )

        change = LogChange(action="added", path="x.py")
        self.assertEqual(changed_row(change), ["added", "x.py", change])

    def test_git_diff_commands(self):
        root = Path("/tmp/repo")
        self.assertEqual(
            git_revision_diff_command(root, "abc123"),
            [
                "git",
                "-C",
                "/tmp/repo",
                "difftool",
                "-d",
                "--tool=meld",
                "--no-prompt",
                "abc123~1",
                "abc123",
            ],
        )
        self.assertEqual(
            git_revision_file_diff_command(root, "abc123", "src/a.py"),
            [
                "git",
                "-C",
                "/tmp/repo",
                "difftool",
                "--tool=meld",
                "--no-prompt",
                "abc123~1",
                "abc123",
                "--",
                "src/a.py",
            ],
        )

    def test_log_filter_paths_returns_relative_selected_paths(self):
        self.assertEqual(
            log_filter_paths(
                ["/tmp/repo/src/a.py", "/tmp/repo/docs"],
                Path("/tmp/repo"),
            ),
            ("src/a.py", "docs"),
        )

    def test_log_filter_paths_root_selection_means_whole_worktree(self):
        self.assertEqual(log_filter_paths(["/tmp/repo"], Path("/tmp/repo")), ())

    def test_log_filter_paths_deduplicates_and_skips_other_roots(self):
        self.assertEqual(
            log_filter_paths(
                ["/tmp/repo/src/a.py", "/tmp/repo/src/a.py", "/tmp/other/a.py"],
                Path("/tmp/repo"),
            ),
            ("src/a.py",),
        )


class LogDialogLoadTest(unittest.TestCase):
    def test_load_log_populates_revisions(self):
        dialog = make_dialog()
        entry = LogEntry(
            revision="abc123def456",
            author="Alice",
            date="2024-01-02T03:04:05+00:00",
            summary="Only commit",
            body="",
        )
        backend = FakeBackend(BackendLog(ok=True, entries=(entry,)))

        with mock.patch.object(
            log_dialog.backends,
            "detect_root",
            return_value=(backend, Path("/tmp/repo")),
        ):
            dialog.load_log()

        self.assertEqual(dialog.exit_code, 0)
        self.assertEqual(dialog.store.rows, [revision_row(entry)])
        self.assertEqual(dialog.backend_id, "git")
        self.assertEqual(dialog.root, Path("/tmp/repo"))
        self.assertIn("1 revision", dialog.header_label.text)
        self.assertFalse(dialog.show_more_button.sensitive)
        self.assertEqual(backend.limit, 50)
        self.assertEqual(backend.paths, ())

    def test_load_log_passes_selected_path_filter(self):
        dialog = make_dialog()
        dialog.paths = ["/tmp/repo/src/a.py"]
        dialog.path = dialog.paths[0]
        backend = FakeBackend(BackendLog(ok=True, entries=()))

        with mock.patch.object(
            log_dialog.backends,
            "detect_root",
            return_value=(backend, Path("/tmp/repo")),
        ):
            dialog.load_log()

        self.assertEqual(backend.paths, ("src/a.py",))

    def test_load_log_reports_missing_worktree(self):
        dialog = make_dialog()

        with mock.patch.object(
            log_dialog.backends, "detect_root", return_value=None
        ):
            dialog.load_log()

        self.assertEqual(dialog.exit_code, 1)
        self.assertIn("Not inside", dialog.header_label.text)
        self.assertFalse(dialog.show_more_button.sensitive)

    def test_load_log_reports_command_error(self):
        dialog = make_dialog()
        backend = FakeBackend(BackendLog(ok=False, error="boom"))

        with mock.patch.object(
            log_dialog.backends,
            "detect_root",
            return_value=(backend, Path("/tmp/repo")),
        ):
            dialog.load_log()

        self.assertEqual(dialog.exit_code, 1)
        self.assertEqual(dialog.message_buffer.text, "boom")
        self.assertIn("Failed", dialog.header_label.text)

    def test_revision_selection_fills_message_and_changes(self):
        dialog = make_dialog()
        entry = LogEntry(
            revision="r1",
            author="Alice",
            date="",
            summary="Subject",
            body="Body text",
            changes=(
                LogChange(action="modified", path="a.py"),
                LogChange(action="renamed", path="new.py", old_path="old.py"),
            ),
        )
        dialog.selected_entry = lambda: entry

        dialog.on_revision_selected(None)

        self.assertEqual(dialog.message_buffer.text, "Subject\n\nBody text")
        self.assertEqual(
            dialog.changes_store.rows,
            [changed_row(change) for change in entry.changes],
        )


if __name__ == "__main__":
    unittest.main()
