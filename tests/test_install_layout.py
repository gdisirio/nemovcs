import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install-layout.py"
SPEC = importlib.util.spec_from_file_location("install_layout", MODULE_PATH)
install_layout = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(install_layout)


class InstallLayoutTest(unittest.TestCase):
    def test_build_layout_has_top_level_and_submenu_actions(self):
        layout = install_layout.build_nemovcs_layout()

        self.assertEqual(layout[0]["uuid"], "nemovcs-commit.nemo_action")
        self.assertEqual(layout[1]["uuid"], "nemovcs-stage.nemo_action")
        self.assertEqual(layout[2]["uuid"], "nemovcs-update.nemo_action")
        self.assertEqual(layout[3]["uuid"], "nemovcs-background-update.nemo_action")
        self.assertEqual(layout[4]["uuid"], "NemoVCS")
        self.assertEqual(layout[4]["type"], "submenu")
        self.assertEqual(layout[4]["user-label"], "NemoVCS")

        child_uuids = [child["uuid"] for child in layout[4]["children"]]
        self.assertIn("nemovcs-status.nemo_action", child_uuids)
        self.assertIn("nemovcs-settings.nemo_action", child_uuids)
        self.assertIn("nemovcs-about.nemo_action", child_uuids)

    def test_prune_removes_nested_nemovcs_nodes(self):
        nodes = [
            {"uuid": "other.nemo_action", "type": "action"},
            {
                "uuid": "Tools",
                "type": "submenu",
                "children": [{"uuid": "nemovcs-status.nemo_action", "type": "action"}],
            },
            {"uuid": "nemovcs-commit.nemo_action", "type": "action"},
        ]

        kept = install_layout.prune_nemovcs(nodes)

        self.assertEqual(kept, [{"uuid": "other.nemo_action", "type": "action"}])


if __name__ == "__main__":
    unittest.main()
