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


if __name__ == "__main__":
    unittest.main()

