#!/usr/bin/env python3
"""Install the NemoVCS nemo-python extension for source-tree testing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


EXTENSION_NAME = "NemoVCS.py"
LEGACY_ACTION_FILES = {
    "nemovcs-about.nemo_action",
    "nemovcs-background-about.nemo_action",
    "nemovcs-background-clone.nemo_action",
    "nemovcs-background-push.nemo_action",
    "nemovcs-background-settings.nemo_action",
    "nemovcs-background-status.nemo_action",
    "nemovcs-background-svn-about.nemo_action",
    "nemovcs-background-svn-checkout.nemo_action",
    "nemovcs-background-svn-settings.nemo_action",
    "nemovcs-background-svn-status.nemo_action",
    "nemovcs-background-svn-update.nemo_action",
    "nemovcs-background-update.nemo_action",
    "nemovcs-clone.nemo_action",
    "nemovcs-commit.nemo_action",
    "nemovcs-diff.nemo_action",
    "nemovcs-log.nemo_action",
    "nemovcs-push.nemo_action",
    "nemovcs-revert.nemo_action",
    "nemovcs-settings.nemo_action",
    "nemovcs-stage.nemo_action",
    "nemovcs-status.nemo_action",
    "nemovcs-svn-about.nemo_action",
    "nemovcs-svn-add.nemo_action",
    "nemovcs-svn-checkout.nemo_action",
    "nemovcs-svn-commit.nemo_action",
    "nemovcs-svn-diff.nemo_action",
    "nemovcs-svn-log.nemo_action",
    "nemovcs-svn-revert.nemo_action",
    "nemovcs-svn-settings.nemo_action",
    "nemovcs-svn-status.nemo_action",
    "nemovcs-svn-update.nemo_action",
    "nemovcs-update.nemo_action",
}
EMBLEM_ICON_NAMES = [
    "emblem-nemovcs-conflicted.svg",
    "emblem-nemovcs-modified.svg",
    "emblem-nemovcs-normal.svg",
    "emblem-nemovcs-unversioned.svg",
]
ACTION_ICON_NAMES = [
    "nemovcs-about.svg",
    "nemovcs-add.svg",
    "nemovcs-checkout.svg",
    "nemovcs-commit.svg",
    "nemovcs-diff.svg",
    "nemovcs-git.svg",
    "nemovcs-push.svg",
    "nemovcs-rename.svg",
    "nemovcs-revert.svg",
    "nemovcs-settings.svg",
    "nemovcs-show-log.svg",
    "nemovcs-status.svg",
    "nemovcs-svn.svg",
    "nemovcs-update.svg",
]
APP_ICON_NAMES = [
    "nemovcs-small.svg",
    "nemovcs.svg",
]


def extension_source(repo_root: Path) -> str:
    src_path = repo_root / "src"
    return f'''"""NemoVCS nemo-python entry point."""

from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, {str(src_path)!r})

if os.environ.get("NEMOVCS_PLUGIN_LOG"):
    try:
        Path(os.environ["NEMOVCS_PLUGIN_LOG"]).write_text(
            '{{"event":"extension-import"}}\\n',
            encoding="utf-8",
        )
    except OSError:
        pass

import gi

gi.require_version("Nemo", "3.0")
from gi.repository import GObject, Nemo

from nemovcs.nemo_plugin import NemoVCSInfoProviderMixin


class NemoVCS(
    NemoVCSInfoProviderMixin,
    GObject.GObject,
    Nemo.InfoProvider,
    Nemo.LocationWidgetProvider,
    Nemo.MenuProvider,
    Nemo.NameAndDescProvider,
):
    """Nemo provider for NemoVCS status emblems and context menus."""

    def __init__(self):
        GObject.GObject.__init__(self)
        NemoVCSInfoProviderMixin.__init__(self)

    def get_name_and_desc(self):
        return ["NemoVCS:::Version control integration for Nemo"]
'''


def target_dir(data_home: Path | None = None) -> Path:
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "nemo-python" / "extensions"


def icon_target_dir(data_home: Path | None = None) -> Path:
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "icons" / "hicolor" / "scalable" / "emblems"


def hicolor_target_dir(subdir: str, data_home: Path | None = None) -> Path:
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "icons" / "hicolor" / "scalable" / subdir


def hicolor_theme_dir(data_home: Path | None = None) -> Path:
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "icons" / "hicolor"


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def remove_tree(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_dir():
        path.unlink()
        return True
    shutil.rmtree(path)
    return True


def is_legacy_action_node(node: dict[str, object]) -> bool:
    uuid = node.get("uuid")
    if isinstance(uuid, str) and (
        uuid == "NemoVCS"
        or uuid.startswith("nemovcs-")
        or uuid in LEGACY_ACTION_FILES
    ):
        return True

    children = node.get("children")
    return isinstance(children, list) and any(
        isinstance(child, dict) and is_legacy_action_node(child)
        for child in children
    )


def prune_legacy_action_layout(config_dir: Path | None = None) -> bool:
    config_dir = config_dir or config_home()
    layout_path = config_dir / "nemo" / "actions-tree.json"
    try:
        data = json.loads(layout_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    if not isinstance(data, dict) or not isinstance(data.get("toplevel"), list):
        return False

    original = data["toplevel"]
    pruned = [
        node
        for node in original
        if not (isinstance(node, dict) and is_legacy_action_node(node))
    ]
    if pruned == original:
        return False

    data["toplevel"] = pruned
    layout_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def remove_legacy_actions(
    data_home: Path | None = None,
    config_dir: Path | None = None,
) -> list[Path]:
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))

    removed: list[Path] = []
    actions_dir = data_home / "nemo" / "actions"
    for name in sorted(LEGACY_ACTION_FILES):
        path = actions_dir / name
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(path)

    icons_dir = actions_dir / "nemovcs-icons"
    if remove_tree(icons_dir):
        removed.append(icons_dir)

    layout_path = (config_dir or config_home()) / "nemo" / "actions-tree.json"
    if prune_legacy_action_layout(config_dir):
        removed.append(layout_path)

    return removed


def copy_icon_set(
    source_dir: Path,
    target_dir: Path,
    names: list[str],
) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    for name in names:
        destination = target_dir / name
        shutil.copy2(source_dir / name, destination)
        installed.append(destination)
    return installed


def install_icons(repo_root: Path, data_home: Path | None = None) -> list[Path]:
    source_root = repo_root / "rsc" / "icons" / "nemovcs"
    installed = copy_icon_set(
        source_root / "emblems",
        icon_target_dir(data_home),
        EMBLEM_ICON_NAMES,
    )
    installed.extend(
        copy_icon_set(
            source_root / "actions",
            hicolor_target_dir("actions", data_home),
            ACTION_ICON_NAMES,
        )
    )
    installed.extend(
        copy_icon_set(
            source_root / "apps",
            hicolor_target_dir("apps", data_home),
            APP_ICON_NAMES,
        )
    )
    return installed


def install(repo_root: Path, data_home: Path | None = None) -> Path:
    remove_legacy_actions(data_home=data_home)
    target = target_dir(data_home)
    target.mkdir(parents=True, exist_ok=True)
    extension_path = target / EXTENSION_NAME
    extension_path.write_text(extension_source(repo_root), encoding="utf-8")
    install_icons(repo_root, data_home=data_home)
    return extension_path


def update_icon_cache(data_home: Path | None = None) -> bool:
    updater = shutil.which("gtk-update-icon-cache")
    if updater is None:
        return False

    subprocess.run(
        [updater, "-f", "-t", str(hicolor_theme_dir(data_home))],
        check=False,
    )
    return True


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    extension_path = install(repo_root)
    update_icon_cache()
    print(f"Installed NemoVCS nemo-python extension to {extension_path}")
    print("Restart Nemo with: nemo --quit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
