import importlib.util
from pathlib import Path
import stat
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install-statusd-service.py"
SPEC = importlib.util.spec_from_file_location("install_statusd_service", MODULE_PATH)
install_statusd_service = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = install_statusd_service
SPEC.loader.exec_module(install_statusd_service)


class InstallStatusdServiceTest(unittest.TestCase):
    def test_wrapper_source_points_to_repo_src_and_runs_statusd(self):
        repo_root = Path("/tmp/nemovcs source")

        source = install_statusd_service.wrapper_source(repo_root)

        self.assertIn("PYTHONPATH='/tmp/nemovcs source/src'", source)
        self.assertIn("exec python3 -m nemovcs statusd", source)

    def test_service_source_uses_statusd_bus_name_and_wrapper(self):
        wrapper = Path("/tmp/bin/nemovcs-statusd")

        source = install_statusd_service.service_source(wrapper)

        self.assertIn("[D-BUS Service]", source)
        self.assertIn(
            "Name=io.github.gdisirio.NemoVCS.Statusd",
            source,
        )
        self.assertIn("Exec=/tmp/bin/nemovcs-statusd", source)

    def test_install_writes_executable_wrapper_and_service_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            repo_root.mkdir()
            bin_home = root / "bin"
            data_home = root / "share"

            installed = install_statusd_service.install(
                repo_root,
                bin_home=bin_home,
                data_home=data_home,
            )

            self.assertEqual(installed.wrapper_path, bin_home / "nemovcs-statusd")
            self.assertEqual(
                installed.service_path,
                data_home
                / "dbus-1"
                / "services"
                / "io.github.gdisirio.NemoVCS.Statusd.service",
            )
            self.assertIn(
                str(repo_root / "src"),
                installed.wrapper_path.read_text(encoding="utf-8"),
            )
            self.assertIn(
                str(installed.wrapper_path),
                installed.service_path.read_text(encoding="utf-8"),
            )
            self.assertTrue(
                installed.wrapper_path.stat().st_mode & stat.S_IXUSR,
            )


if __name__ == "__main__":
    unittest.main()
