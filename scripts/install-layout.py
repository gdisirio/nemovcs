#!/usr/bin/env python3
"""Install a Nemo action layout for NemoVCS."""

from __future__ import annotations

import json
import os
from pathlib import Path


NEMOVCS_ACTIONS = {
    "nemovcs-about.nemo_action",
    "nemovcs-background-about.nemo_action",
    "nemovcs-background-settings.nemo_action",
    "nemovcs-background-status.nemo_action",
    "nemovcs-background-update.nemo_action",
    "nemovcs-commit.nemo_action",
    "nemovcs-diff.nemo_action",
    "nemovcs-log.nemo_action",
    "nemovcs-settings.nemo_action",
    "nemovcs-status.nemo_action",
    "nemovcs-update.nemo_action",
}

TOP_LEVEL_ACTIONS = [
    "nemovcs-commit.nemo_action",
    "nemovcs-update.nemo_action",
    "nemovcs-background-update.nemo_action",
]

SUBMENU_ACTIONS = [
    "nemovcs-status.nemo_action",
    "nemovcs-background-status.nemo_action",
    "nemovcs-diff.nemo_action",
    "nemovcs-log.nemo_action",
    "nemovcs-settings.nemo_action",
    "nemovcs-background-settings.nemo_action",
    "nemovcs-about.nemo_action",
    "nemovcs-background-about.nemo_action",
]


def action_node(filename: str) -> dict[str, object]:
    return {
        "uuid": filename,
        "type": "action",
        "user-label": None,
        "user-icon": None,
        "accelerator": None,
    }


def submenu_node(label: str, children: list[dict[str, object]]) -> dict[str, object]:
    return {
        "uuid": label,
        "type": "submenu",
        "user-label": label,
        "user-icon": None,
        "accelerator": None,
        "children": children,
    }


def separator_node() -> dict[str, object]:
    return {
        "uuid": "separator",
        "type": "separator",
        "user-label": None,
        "user-icon": None,
        "accelerator": None,
    }


def is_nemovcs_node(node: dict[str, object]) -> bool:
    uuid = node.get("uuid")
    if isinstance(uuid, str) and (
        uuid in NEMOVCS_ACTIONS or uuid == "NemoVCS" or uuid.startswith("nemovcs-")
    ):
        return True

    children = node.get("children")
    if isinstance(children, list):
        return any(isinstance(child, dict) and is_nemovcs_node(child) for child in children)

    return False


def prune_nemovcs(nodes: list[object]) -> list[dict[str, object]]:
    kept: list[dict[str, object]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if is_nemovcs_node(node):
            continue
        kept.append(node)
    return kept


def discover_non_nemovcs_actions() -> list[dict[str, object]]:
    data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    data_home = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    action_files: dict[str, Path] = {}

    for data_dir in [*data_dirs, data_home]:
        actions_dir = Path(data_dir) / "nemo/actions"
        if not actions_dir.is_dir():
            continue
        for path in actions_dir.glob("*.nemo_action"):
            action_files.setdefault(path.name, path)

    return [
        action_node(name)
        for name in sorted(action_files)
        if name not in NEMOVCS_ACTIONS
    ]


def load_layout(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"toplevel": discover_non_nemovcs_actions()}

    if not isinstance(data, dict) or not isinstance(data.get("toplevel"), list):
        return {"toplevel": discover_non_nemovcs_actions()}

    return data


def build_nemovcs_layout() -> list[dict[str, object]]:
    return [
        *(action_node(name) for name in TOP_LEVEL_ACTIONS),
        submenu_node("NemoVCS", [action_node(name) for name in SUBMENU_ACTIONS]),
        separator_node(),
    ]


def main() -> int:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    layout_path = config_home / "nemo/actions-tree.json"
    layout_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = layout_path.with_suffix(".json.bak")

    data = load_layout(layout_path)
    data["toplevel"] = [
        *build_nemovcs_layout(),
        *prune_nemovcs(data.get("toplevel", [])),
    ]

    if layout_path.exists() and not backup_path.exists():
        backup_path.write_bytes(layout_path.read_bytes())
        print(f"Backed up existing Nemo action layout to {backup_path}")

    tmp_path = layout_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    tmp_path.replace(layout_path)

    print(f"Installed NemoVCS action layout to {layout_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
