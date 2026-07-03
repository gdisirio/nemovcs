import subprocess
import unittest
from unittest import mock

from nemovcs.ui import settings_dialog


class SettingsDialogTest(unittest.TestCase):
    def test_navigation_model_contains_statusd_status_and_settings(self):
        model = settings_dialog.navigation_model()
        root = model.get_iter_first()
        assert root is not None

        first = model.iter_children(root)
        assert first is not None
        second = model.iter_next(first)
        assert second is not None

        self.assertEqual(model[root][settings_dialog.NAV_LABEL], "Statusd")
        self.assertEqual(model[first][settings_dialog.NAV_LABEL], "Status")
        self.assertEqual(model[first][settings_dialog.NAV_PAGE], "statusd-status")
        self.assertEqual(model[first][settings_dialog.NAV_ICON], "nemovcs-normal")
        self.assertEqual(model[second][settings_dialog.NAV_LABEL], "Settings")
        self.assertEqual(model[second][settings_dialog.NAV_PAGE], "statusd-settings")
        self.assertEqual(model[second][settings_dialog.NAV_ICON], "nemovcs-settings")

    def test_cache_record_sort_key_groups_by_worktree_then_path(self):
        records = [
            {"worktree_id": "git:/tmp/b", "path": "/tmp/b/z.txt"},
            {"worktree_id": "git:/tmp/a", "path": "/tmp/a/z.txt"},
            {"worktree_id": "git:/tmp/a", "path": "/tmp/a/a.txt"},
        ]

        self.assertEqual(
            sorted(records, key=settings_dialog.cache_record_sort_key),
            [
                {"worktree_id": "git:/tmp/a", "path": "/tmp/a/a.txt"},
                {"worktree_id": "git:/tmp/a", "path": "/tmp/a/z.txt"},
                {"worktree_id": "git:/tmp/b", "path": "/tmp/b/z.txt"},
            ],
        )

    def test_status_icon_names_cover_daemon_statuses(self):
        for status in (
            "conflicted",
            "error",
            "loading",
            "modified",
            "ok",
            "stale",
            "unversioned",
        ):
            with self.subTest(status=status):
                self.assertIn(status, settings_dialog.STATUS_ICON_NAMES)

    def test_statusd_pids_uses_pgrep_and_skips_current_process(self):
        result = subprocess.CompletedProcess(
            ["pgrep"],
            0,
            stdout="123\n456\nnot-a-pid\n",
            stderr="",
        )

        with mock.patch("nemovcs.ui.settings_dialog.subprocess.run", return_value=result), (
            mock.patch("nemovcs.ui.settings_dialog.os.getpid", return_value=456)
        ):
            self.assertEqual(settings_dialog.statusd_pids(), [123])

    def test_statusd_pids_returns_empty_when_pgrep_is_missing(self):
        with mock.patch(
            "nemovcs.ui.settings_dialog.subprocess.run",
            side_effect=OSError("missing"),
        ):
            self.assertEqual(settings_dialog.statusd_pids(), [])

    def test_restart_status_process_terminates_statusd_pids(self):
        with mock.patch(
            "nemovcs.ui.settings_dialog.statusd_pids",
            return_value=[111, 222],
        ), mock.patch("nemovcs.ui.settings_dialog.os.kill") as kill:
            self.assertEqual(settings_dialog.restart_status_process(), 2)

        self.assertEqual(
            kill.mock_calls,
            [
                mock.call(111, settings_dialog.signal.SIGTERM),
                mock.call(222, settings_dialog.signal.SIGTERM),
            ],
        )

    def test_restart_status_process_ignores_exited_processes(self):
        with mock.patch(
            "nemovcs.ui.settings_dialog.statusd_pids",
            return_value=[111],
        ), mock.patch(
            "nemovcs.ui.settings_dialog.os.kill",
            side_effect=ProcessLookupError,
        ):
            self.assertEqual(settings_dialog.restart_status_process(), 0)

    def test_format_seconds_formats_numeric_values(self):
        self.assertEqual(settings_dialog.format_seconds("0.75"), "0.75 seconds")
        self.assertEqual(settings_dialog.format_seconds("1.0"), "1 seconds")

    def test_format_seconds_handles_unknown_values(self):
        self.assertEqual(settings_dialog.format_seconds(""), "unknown")
        self.assertEqual(settings_dialog.format_seconds("soon"), "unknown")

    def test_parse_setting_values_use_fallbacks_for_invalid_input(self):
        self.assertEqual(settings_dialog.parse_int("12", fallback=3), 12)
        self.assertEqual(settings_dialog.parse_int("bad", fallback=3), 3)
        self.assertEqual(settings_dialog.parse_float("0.5", fallback=1.0), 0.5)
        self.assertEqual(settings_dialog.parse_float("bad", fallback=1.0), 1.0)

    def test_statusd_settings_payload_reads_spin_values(self):
        class FakeSpin:
            def __init__(self, value):
                self.value = value

            def get_value_as_int(self):
                return int(self.value)

            def get_value(self):
                return float(self.value)

        class FakePage:
            cache_size_spin = FakeSpin(24)
            debounce_spin = FakeSpin(1.5)
            scan_ttl_spin = FakeSpin(30)

        self.assertEqual(
            settings_dialog.StatusdSettingsPage.settings_payload(FakePage()),
            {
                "max_worktrees": "24",
                "debounce_seconds": "1.5",
                "scan_ttl_seconds": "30",
            },
        )

    def test_statusd_settings_save_applies_saved_values(self):
        class FakeLabel:
            def __init__(self):
                self.text = ""

            def set_text(self, text):
                self.text = text

        class FakePage:
            def __init__(self):
                self.status_label = FakeLabel()
                self.applied = None

            def settings_payload(self):
                return {
                    "max_worktrees": "24",
                    "debounce_seconds": "1.5",
                    "scan_ttl_seconds": "30",
                }

            def save_settings(self, settings):
                self.saved = settings
                return {**settings, "config_path": "/tmp/nemovcs/settings.json"}

            def apply_status_settings(self, settings):
                self.applied = settings

        page = FakePage()

        settings_dialog.StatusdSettingsPage.on_save_clicked(page, object())

        self.assertEqual(
            page.saved,
            {
                "max_worktrees": "24",
                "debounce_seconds": "1.5",
                "scan_ttl_seconds": "30",
            },
        )
        self.assertEqual(page.applied["config_path"], "/tmp/nemovcs/settings.json")
        self.assertEqual(
            page.status_label.text,
            "Saved settings to /tmp/nemovcs/settings.json",
        )

    def test_statusd_settings_restart_schedules_delayed_reload(self):
        class FakeLabel:
            def __init__(self):
                self.text = ""

            def set_text(self, text):
                self.text = text

        class FakePage:
            def __init__(self):
                self.status_label = FakeLabel()
                self.reloaded = False

            def restart_status(self):
                return 1

            def reload_after_restart(self):
                self.reloaded = True
                return False

        page = FakePage()

        with mock.patch("nemovcs.ui.settings_dialog.GLib.timeout_add") as timeout_add:
            settings_dialog.StatusdSettingsPage.on_restart_clicked(page, object())

        self.assertEqual(page.status_label.text, "Restarted status process; stopped 1.")
        timeout_add.assert_called_once_with(750, page.reload_after_restart)
        self.assertFalse(page.reloaded)


if __name__ == "__main__":
    unittest.main()
