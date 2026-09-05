from pathlib import Path
import unittest
from unittest import mock

from nemovcs.backends.base import BackendCommandPhase
from nemovcs.ui import delete_dialog


class DeleteDialogTest(unittest.TestCase):
    def test_rejects_selection_without_delete_phases(self):
        with mock.patch(
            "nemovcs.ui.delete_dialog.delete_phases",
            return_value=[],
        ), mock.patch("nemovcs.ui.delete_dialog.info_dialog.show_error") as show_error:
            self.assertEqual(delete_dialog.run(["/tmp/repo"]), 1)

        show_error.assert_called_once()

    def test_cancel_does_not_start_logger(self):
        phase = BackendCommandPhase(
            "Delete from repo",
            Path("/tmp/repo"),
            ("git", "rm", "file.txt"),
        )
        with mock.patch(
            "nemovcs.ui.delete_dialog.delete_phases",
            return_value=[phase],
        ), mock.patch(
            "nemovcs.ui.delete_dialog.confirm.confirm",
            return_value=False,
        ) as confirm, mock.patch("nemovcs.ui.delete_dialog.logger.run") as run_logger:
            self.assertEqual(delete_dialog.run(["/tmp/repo/file.txt"]), 0)

        self.assertEqual(confirm.call_args.kwargs["ok_label"], "Delete")
        self.assertEqual(
            confirm.call_args.kwargs["action_style"],
            "destructive-action",
        )
        run_logger.assert_not_called()

    def test_confirm_runs_delete_phases_in_logger(self):
        phase = BackendCommandPhase(
            "Delete from repo",
            Path("/tmp/repo"),
            ("git", "rm", "file.txt"),
        )
        with mock.patch(
            "nemovcs.ui.delete_dialog.delete_phases",
            return_value=[phase],
        ), mock.patch(
            "nemovcs.ui.delete_dialog.confirm.confirm",
            return_value=True,
        ), mock.patch(
            "nemovcs.ui.delete_dialog.logger.run",
            return_value=0,
        ) as run_logger:
            self.assertEqual(delete_dialog.run(["/tmp/repo/file.txt"]), 0)

        run_logger.assert_called_once_with("Delete", [phase])

    def test_confirmation_detail_limits_long_selections(self):
        paths = [f"/tmp/repo/file-{index}" for index in range(12)]

        detail = delete_dialog.confirmation_detail(paths)

        self.assertIn("Selected: /tmp/repo/file-0", detail)
        self.assertNotIn("Selected: /tmp/repo/file-10", detail)
        self.assertIn("... and 2 more", detail)


if __name__ == "__main__":
    unittest.main()
