import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install-nemo-extension.py"
SPEC = importlib.util.spec_from_file_location("install_nemo_extension", MODULE_PATH)
install_nemo_extension = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(install_nemo_extension)


class InstallNemoExtensionTest(unittest.TestCase):
    def test_extension_source_points_to_repo_src(self):
        repo_root = Path("/tmp/nemovcs")

        source = install_nemo_extension.extension_source(repo_root)

        self.assertIn("gi.require_version(\"Nemo\", \"3.0\")", source)
        self.assertIn("NemoVCSInfoProviderMixin", source)
        self.assertIn("Nemo.MenuProvider", source)
        self.assertIn("Nemo.NameAndDescProvider", source)
        self.assertIn(
            'return ["NemoVCS:::Version control integration for Nemo"]',
            source,
        )
        self.assertIn("sys.path.insert(0, '/tmp/nemovcs/src')", source)

    def test_install_writes_user_extension_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(__file__).resolve().parents[1]

            path = install_nemo_extension.install(repo_root, data_home=Path(tmp))

            self.assertEqual(
                path,
                Path(tmp) / "nemo-python" / "extensions" / "NemoVCS.py",
            )
            self.assertIn(
                "class NemoVCS",
                path.read_text(encoding="utf-8"),
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "emblems"
                    / "emblem-nemovcs-modified.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "emblems"
                    / "emblem-nemovcs-conflicted.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "emblems"
                    / "emblem-nemovcs-unversioned.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "emblems"
                    / "emblem-nemovcs-normal.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "actions"
                    / "nemovcs-commit.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "actions"
                    / "nemovcs-diff.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "actions"
                    / "nemovcs-git.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "actions"
                    / "nemovcs-svn.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "actions"
                    / "nemovcs-revert.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "actions"
                    / "nemovcs-rename.svg"
                ).exists()
            )
            self.assertTrue(
                (
                    Path(tmp)
                    / "icons"
                    / "hicolor"
                    / "scalable"
                    / "apps"
                    / "nemovcs.svg"
                ).exists()
            )

    def test_install_removes_legacy_actions_and_layout_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_home = root / "share"
            config_home = root / "config"
            actions_dir = data_home / "nemo" / "actions"
            actions_dir.mkdir(parents=True)
            legacy_action = actions_dir / "nemovcs-status.nemo_action"
            legacy_action.write_text("[Nemo Action]\n", encoding="utf-8")
            other_action = actions_dir / "other.nemo_action"
            other_action.write_text("[Nemo Action]\n", encoding="utf-8")
            legacy_icon = actions_dir / "nemovcs-icons" / "icon.svg"
            legacy_icon.parent.mkdir(parents=True)
            legacy_icon.write_text("icon\n", encoding="utf-8")
            layout = config_home / "nemo" / "actions-tree.json"
            layout.parent.mkdir(parents=True)
            layout.write_text(
                json.dumps(
                    {
                        "toplevel": [
                            {"uuid": "nemovcs-status.nemo_action", "type": "action"},
                            {"uuid": "other.nemo_action", "type": "action"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            removed = install_nemo_extension.remove_legacy_actions(
                data_home=data_home,
                config_dir=config_home,
            )

            self.assertIn(legacy_action, removed)
            self.assertFalse(legacy_action.exists())
            self.assertFalse(legacy_icon.parent.exists())
            self.assertTrue(other_action.exists())
            self.assertEqual(
                json.loads(layout.read_text(encoding="utf-8"))["toplevel"],
                [{"uuid": "other.nemo_action", "type": "action"}],
            )


if __name__ == "__main__":
    unittest.main()
