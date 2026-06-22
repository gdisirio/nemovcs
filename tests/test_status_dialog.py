from pathlib import Path
import unittest
from unittest import mock

from nemovcs import git
from nemovcs.backends.base import BackendChangeItem
from nemovcs.ui.status_dialog import StatusDialog, format_status_output


class StatusDialogTest(unittest.TestCase):
    def test_format_status_output_preserves_raw_single_repo_output(self):
        result = git.GitResult(
            ("git",),
            Path("/tmp/example"),
            0,
            "## main...origin/main\n M src/app.py\n",
            "",
        )

        self.assertEqual(format_status_output([result]), result.stdout)

    def test_format_status_output_labels_multiple_repositories(self):
        results = [
            git.GitResult(("git",), Path("/tmp/one"), 0, " M one.py\n", ""),
            git.GitResult(("git",), Path("/tmp/two"), 0, " M two.py\n", ""),
        ]

        self.assertEqual(
            format_status_output(results),
            "# /tmp/one\n M one.py\n\n# /tmp/two\n M two.py\n",
        )

    def test_file_diff_command_compares_path_against_head_without_dir_diff(self):
        root = Path("/tmp/example")
        item = BackendChangeItem(
            backend_id="git",
            root=root,
            path="src/app.py",
            status="modified",
        )
        dialog = StatusDialog.__new__(StatusDialog)

        command = dialog.file_diff_command(item)

        self.assertEqual(
            command,
            [
                "git",
                "-C",
                str(root),
                "difftool",
                "--tool=meld",
                "--no-prompt",
                "HEAD",
                "--",
                "src/app.py",
            ],
        )
        self.assertNotIn("--dir-diff", command)

    def test_load_status_uses_backend_raw_status_for_output_tab(self):
        class FakeStore:
            def __init__(self):
                self.cleared = False

            def clear(self):
                self.cleared = True

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

        dialog = StatusDialog.__new__(StatusDialog)
        dialog.paths = ["/tmp/example"]
        dialog.exit_code = 0
        dialog.store = FakeStore()
        dialog.output_buffer = FakeBuffer()
        dialog.status_label = FakeLabel()
        result = git.GitResult(("git",), Path("/tmp/example"), 0, " M src/app.py\n", "")

        with mock.patch("nemovcs.ui.status_dialog.backends.commit_items", return_value={}), (
            mock.patch("nemovcs.ui.status_dialog.backends.raw_status", return_value=[result])
        ) as raw_status:
            StatusDialog.load_status(dialog)

        raw_status.assert_called_once_with(["/tmp/example"])
        self.assertEqual(dialog.output_buffer.text, " M src/app.py\n")


if __name__ == "__main__":
    unittest.main()
