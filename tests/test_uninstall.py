import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "uninstall.py"
SPEC = importlib.util.spec_from_file_location("uninstall", MODULE_PATH)
uninstall = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = uninstall
SPEC.loader.exec_module(uninstall)


class UninstallTest(unittest.TestCase):
    def test_remove_install_files_removes_only_nemovcs_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "share"
            config = root / "config"
            bin_dir = root / "bin"
            actions = data / "nemo" / "actions"
            actions.mkdir(parents=True)
            for name in uninstall.ACTION_FILES:
                (actions / name).write_text("[Nemo Action]\n", encoding="utf-8")
            (actions / "other.nemo_action").write_text("[Nemo Action]\n", encoding="utf-8")
            (actions / "nemovcs-icons" / "rabbitvcs").mkdir(parents=True)
            (actions / "nemovcs-icons" / "rabbitvcs" / "icon.svg").write_text(
                "icon",
                encoding="utf-8",
            )
            extension = data / "nemo-python" / "extensions" / "NemoVCS.py"
            extension.parent.mkdir(parents=True)
            extension.write_text("extension\n", encoding="utf-8")
            service = (
                data
                / "dbus-1"
                / "services"
                / "io.github.gdisirio.NemoVCS.Statusd.service"
            )
            service.parent.mkdir(parents=True)
            service.write_text("[D-BUS Service]\n", encoding="utf-8")
            bin_dir.mkdir()
            wrapper = bin_dir / "nemovcs-statusd"
            wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
            for name in uninstall.EMBLEM_ICONS:
                icon = data / "icons" / "hicolor" / "scalable" / "emblems" / name
                icon.parent.mkdir(parents=True, exist_ok=True)
                icon.write_text("icon\n", encoding="utf-8")

            removed = uninstall.remove_install_files(
                data_dir=data,
                config_dir=config,
                bin_dir=bin_dir,
            )

            self.assertTrue(removed)
            self.assertFalse(any((actions / name).exists() for name in uninstall.ACTION_FILES))
            self.assertFalse((actions / "nemovcs-icons").exists())
            self.assertFalse(extension.exists())
            self.assertFalse(service.exists())
            self.assertFalse(wrapper.exists())
            self.assertTrue((actions / "other.nemo_action").exists())

    def test_prune_layout_removes_nemovcs_nodes_and_keeps_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = Path(tmp) / "actions-tree.json"
            layout.write_text(
                json.dumps(
                    {
                        "toplevel": [
                            {"uuid": "nemovcs-commit.nemo_action", "type": "action"},
                            {
                                "uuid": "NemoVCS",
                                "type": "submenu",
                                "children": [
                                    {"uuid": "nemovcs-status.nemo_action", "type": "action"}
                                ],
                            },
                            {"uuid": "other.nemo_action", "type": "action"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(uninstall.prune_layout(layout))

            data = json.loads(layout.read_text(encoding="utf-8"))
            self.assertEqual(
                data["toplevel"],
                [{"uuid": "other.nemo_action", "type": "action"}],
            )

    def test_stop_statusd_terminates_matching_processes(self):
        result = mock.Mock(stdout="123\nnot-a-pid\n")
        with mock.patch("subprocess.run", return_value=result), mock.patch(
            "os.kill"
        ) as kill:
            self.assertTrue(uninstall.stop_statusd())

        kill.assert_called_once_with(123, uninstall.signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
