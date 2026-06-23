import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install-layout.py"
SPEC = importlib.util.spec_from_file_location("install_layout", MODULE_PATH)
install_layout = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(install_layout)


class InstallLayoutTest(unittest.TestCase):
    def test_build_layout_installs_no_static_nemovcs_actions(self):
        layout = install_layout.build_nemovcs_layout()

        self.assertEqual(layout, [])

    def test_normalize_separators_removes_duplicates_and_edges(self):
        nodes = [
            {"uuid": "separator", "type": "separator"},
            {"uuid": "nemovcs-commit.nemo_action", "type": "action"},
            {"uuid": "separator", "type": "separator"},
            {"uuid": "separator", "type": "separator"},
            {"uuid": "other.nemo_action", "type": "action"},
            {"uuid": "separator", "type": "separator"},
        ]

        normalized = install_layout.normalize_separators(nodes)

        self.assertEqual(
            [node["uuid"] for node in normalized],
            [
                "nemovcs-commit.nemo_action",
                "separator",
                "other.nemo_action",
            ],
        )

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
