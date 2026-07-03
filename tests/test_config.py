from pathlib import Path
import tempfile
import unittest

from nemovcs import config


class ConfigTest(unittest.TestCase):
    def test_load_statusd_settings_creates_default_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"

            settings = config.load_statusd_settings(path)

            self.assertEqual(settings.max_worktrees, config.DEFAULT_MAX_WORKTREES)
            self.assertEqual(settings.debounce_seconds, config.DEFAULT_DEBOUNCE_SECONDS)
            self.assertEqual(
                settings.scan_ttl_seconds,
                config.DEFAULT_SCAN_TTL_SECONDS,
            )
            self.assertTrue(path.exists())

    def test_save_and_load_statusd_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            saved = config.StatusdSettings(
                max_worktrees=24,
                debounce_seconds=1.5,
                scan_ttl_seconds=30.0,
            )

            config.save_statusd_settings(saved, path)

            self.assertEqual(config.load_statusd_settings(path), saved)

    def test_invalid_statusd_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"max_worktrees": "0"}\n', encoding="utf-8")

            settings = config.load_statusd_settings(path)

            self.assertEqual(settings, config.StatusdSettings())

    def test_settings_path_uses_xdg_config_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = config.os.environ.get("XDG_CONFIG_HOME")
            config.os.environ["XDG_CONFIG_HOME"] = tmp
            try:
                self.assertEqual(
                    config.settings_path(),
                    Path(tmp) / "nemovcs" / "settings.json",
                )
            finally:
                if old is None:
                    config.os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    config.os.environ["XDG_CONFIG_HOME"] = old


if __name__ == "__main__":
    unittest.main()
