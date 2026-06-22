#!/usr/bin/env python3
"""Remove per-user NemoVCS development install artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess


ACTION_FILES = {
    "nemovcs-about.nemo_action",
    "nemovcs-background-about.nemo_action",
    "nemovcs-background-settings.nemo_action",
    "nemovcs-background-status.nemo_action",
    "nemovcs-background-update.nemo_action",
    "nemovcs-commit.nemo_action",
    "nemovcs-diff.nemo_action",
    "nemovcs-log.nemo_action",
    "nemovcs-settings.nemo_action",
    "nemovcs-stage.nemo_action",
    "nemovcs-status.nemo_action",
    "nemovcs-update.nemo_action",
}
BUS_NAME = "io.github.gdisirio.NemoVCS.Statusd"
EMBLEM_ICONS = {
    "emblem-rabbitvcs-conflicted.svg",
    "emblem-rabbitvcs-modified.svg",
    "emblem-rabbitvcs-normal.svg",
}


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def bin_home() -> Path:
    return Path.home() / ".local" / "bin"


def remove_file(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def remove_tree(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_dir():
        return remove_file(path)

    for child in path.iterdir():
        if child.is_dir():
            remove_tree(child)
        else:
            remove_file(child)
    path.rmdir()
    return True


def is_nemovcs_layout_node(node: dict[str, object]) -> bool:
    uuid = node.get("uuid")
    if isinstance(uuid, str) and (
        uuid == "NemoVCS" or uuid.startswith("nemovcs-") or uuid in ACTION_FILES
    ):
        return True
    children = node.get("children")
    return isinstance(children, list) and any(
        isinstance(child, dict) and is_nemovcs_layout_node(child)
        for child in children
    )


def prune_layout(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    if not isinstance(data, dict) or not isinstance(data.get("toplevel"), list):
        return False

    original = data["toplevel"]
    pruned = [
        node
        for node in original
        if not (isinstance(node, dict) and is_nemovcs_layout_node(node))
    ]
    if pruned == original:
        return False

    data["toplevel"] = pruned
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def remove_install_files(
    *,
    data_dir: Path | None = None,
    config_dir: Path | None = None,
    bin_dir: Path | None = None,
) -> list[Path]:
    data_dir = data_dir or data_home()
    config_dir = config_dir or config_home()
    bin_dir = bin_dir or bin_home()
    removed: list[Path] = []

    actions_dir = data_dir / "nemo" / "actions"
    for name in sorted(ACTION_FILES):
        path = actions_dir / name
        if remove_file(path):
            removed.append(path)

    icons_dir = actions_dir / "nemovcs-icons"
    if remove_tree(icons_dir):
        removed.append(icons_dir)

    extension_path = data_dir / "nemo-python" / "extensions" / "NemoVCS.py"
    if remove_file(extension_path):
        removed.append(extension_path)

    for name in sorted(EMBLEM_ICONS):
        path = data_dir / "icons" / "hicolor" / "scalable" / "emblems" / name
        if remove_file(path):
            removed.append(path)

    service_path = data_dir / "dbus-1" / "services" / f"{BUS_NAME}.service"
    if remove_file(service_path):
        removed.append(service_path)

    wrapper_path = bin_dir / "nemovcs-statusd"
    if remove_file(wrapper_path):
        removed.append(wrapper_path)

    layout_path = config_dir / "nemo" / "actions-tree.json"
    if prune_layout(layout_path):
        removed.append(layout_path)

    return removed


def stop_statusd() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python3 -m nemovcs statusd"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False

    stopped = False
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        stopped = True
    return stopped


def main() -> int:
    stopped = stop_statusd()
    removed = remove_install_files()
    if stopped:
        print("Stopped running NemoVCS status daemon.")
    for path in removed:
        print(f"Removed {path}")
    if not removed and not stopped:
        print("No NemoVCS install artifacts found.")
    print("Restart Nemo with: nemo --quit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
