from pathlib import Path
import unittest


ACTION_DIR = Path(__file__).resolve().parents[1] / "data" / "nemo" / "actions"


class NemoActionFilesTest(unittest.TestCase):
    def test_icon_paths_are_relative_to_action_dir(self):
        for path in ACTION_DIR.glob("*.nemo_action"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("/home/", text)
                icon_lines = [
                    line for line in text.splitlines() if line.startswith("Icon-Name=")
                ]
                self.assertEqual(len(icon_lines), 1)
                self.assertIn("<nemovcs-icons/", icon_lines[0])

    def test_status_actions_use_gtk_dialog(self):
        for name, placeholder in (
            ("nemovcs-status.nemo_action", "%F"),
            ("nemovcs-background-status.nemo_action", "%P"),
        ):
            with self.subTest(name=name):
                text = (ACTION_DIR / name).read_text(encoding="utf-8")

                self.assertIn(f"Exec=nemovcs status-dialog {placeholder}", text)
                self.assertIn("Terminal=false", text)
                self.assertNotIn("run-terminal status", text)

    def test_small_actions_use_gtk_dialogs(self):
        for name, command in (
            ("nemovcs-about.nemo_action", "about-dialog"),
            ("nemovcs-background-about.nemo_action", "about-dialog"),
            ("nemovcs-settings.nemo_action", "settings-dialog"),
            ("nemovcs-background-settings.nemo_action", "settings-dialog"),
        ):
            with self.subTest(name=name):
                text = (ACTION_DIR / name).read_text(encoding="utf-8")

                self.assertIn(f"Exec=nemovcs {command}", text)
                self.assertIn("Terminal=false", text)
                self.assertNotIn("run-terminal", text)

    def test_log_action_uses_gtk_logger(self):
        text = (ACTION_DIR / "nemovcs-log.nemo_action").read_text(encoding="utf-8")

        self.assertIn("Exec=nemovcs log-dialog %F", text)
        self.assertIn("Terminal=false", text)
        self.assertNotIn("run-terminal log", text)

    def test_stage_action_uses_gtk_dialog(self):
        text = (ACTION_DIR / "nemovcs-stage.nemo_action").read_text(encoding="utf-8")

        self.assertIn("Exec=nemovcs stage-dialog %F", text)
        self.assertIn("Terminal=false", text)
        self.assertNotIn("run-terminal", text)

    def test_diff_action_launches_without_terminal(self):
        text = (ACTION_DIR / "nemovcs-diff.nemo_action").read_text(encoding="utf-8")

        self.assertIn("Exec=nemovcs diff-dialog %F", text)
        self.assertIn("Terminal=false", text)
        self.assertNotIn("run-terminal diff", text)


if __name__ == "__main__":
    unittest.main()
