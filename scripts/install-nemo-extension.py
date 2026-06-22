#!/usr/bin/env python3
"""Install the NemoVCS nemo-python extension for source-tree testing."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


EXTENSION_NAME = "NemoVCS.py"
EMBLEM_ICON_NAMES = [
    "emblem-rabbitvcs-conflicted.svg",
    "emblem-rabbitvcs-modified.svg",
]


def extension_source(repo_root: Path) -> str:
    src_path = repo_root / "src"
    return f'''"""NemoVCS nemo-python entry point."""

from __future__ import annotations

import sys

sys.path.insert(0, {str(src_path)!r})

import gi

gi.require_version("Nemo", "3.0")
from gi.repository import GObject, Nemo

from nemovcs.nemo_plugin import NemoVCSInfoProviderMixin


class NemoVCS(NemoVCSInfoProviderMixin, Nemo.InfoProvider, GObject.GObject):
    """InfoProvider for daemon-backed NemoVCS status emblems."""

    pass
'''


def target_dir(data_home: Path | None = None) -> Path:
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "nemo-python" / "extensions"


def icon_target_dir(data_home: Path | None = None) -> Path:
    if data_home is None:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "icons" / "hicolor" / "scalable" / "emblems"


def install_icons(repo_root: Path, data_home: Path | None = None) -> list[Path]:
    source_dir = repo_root / "rsc" / "icons" / "rabbitvcs" / "emblems"
    target = icon_target_dir(data_home)
    target.mkdir(parents=True, exist_ok=True)

    installed: list[Path] = []
    for name in EMBLEM_ICON_NAMES:
        destination = target / name
        shutil.copy2(source_dir / name, destination)
        installed.append(destination)
    return installed


def install(repo_root: Path, data_home: Path | None = None) -> Path:
    target = target_dir(data_home)
    target.mkdir(parents=True, exist_ok=True)
    extension_path = target / EXTENSION_NAME
    extension_path.write_text(extension_source(repo_root), encoding="utf-8")
    install_icons(repo_root, data_home=data_home)
    return extension_path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    extension_path = install(repo_root)
    print(f"Installed NemoVCS nemo-python extension to {extension_path}")
    print("Restart Nemo with: nemo --quit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
