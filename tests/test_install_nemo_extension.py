import importlib.util
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


if __name__ == "__main__":
    unittest.main()
