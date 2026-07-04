"""NemoVCS configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping


CONFIG_DIR_NAME = "nemovcs"
SETTINGS_FILE_NAME = "settings.json"
DEFAULT_MAX_WORKTREES = 12
DEFAULT_DEBOUNCE_SECONDS = 0.75
DEFAULT_SCAN_TTL_SECONDS = 15.0
DEFAULT_DBUS_TIMEOUT_SECONDS = 1.0
DBUS_TIMEOUT_KEY = "dbus_timeout_seconds"


@dataclass(frozen=True)
class StatusdSettings:
    max_worktrees: int = DEFAULT_MAX_WORKTREES
    debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS
    scan_ttl_seconds: float = DEFAULT_SCAN_TTL_SECONDS

    def __post_init__(self) -> None:
        if self.max_worktrees < 1:
            raise ValueError("cache size must be at least 1")
        if self.debounce_seconds < 0:
            raise ValueError("status refresh delay must not be negative")
        if self.scan_ttl_seconds < 0:
            raise ValueError("scan TTL must not be negative")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "StatusdSettings":
        return cls(
            max_worktrees=parse_int(
                values.get("max_worktrees", DEFAULT_MAX_WORKTREES),
                "cache size",
            ),
            debounce_seconds=parse_float(
                values.get("debounce_seconds", DEFAULT_DEBOUNCE_SECONDS),
                "status refresh delay",
            ),
            scan_ttl_seconds=parse_float(
                values.get("scan_ttl_seconds", DEFAULT_SCAN_TTL_SECONDS),
                "scan TTL",
            ),
        )

    def to_mapping(self) -> dict[str, str]:
        return {
            "max_worktrees": str(self.max_worktrees),
            "debounce_seconds": f"{self.debounce_seconds:g}",
            "scan_ttl_seconds": f"{self.scan_ttl_seconds:g}",
        }


def config_home() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config"


def config_dir() -> Path:
    return config_home() / CONFIG_DIR_NAME


def settings_path(path: Path | None = None) -> Path:
    return path if path is not None else config_dir() / SETTINGS_FILE_NAME


def load_statusd_settings(path: Path | None = None) -> StatusdSettings:
    target = settings_path(path)
    if not target.exists():
        settings = StatusdSettings()
        save_statusd_settings(settings, target)
        return settings

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return StatusdSettings()

    if not isinstance(data, dict):
        return StatusdSettings()

    try:
        return StatusdSettings.from_mapping(data)
    except ValueError:
        return StatusdSettings()


def load_dbus_timeout_seconds(path: Path | None = None) -> float:
    target = settings_path(path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return DEFAULT_DBUS_TIMEOUT_SECONDS

    if not isinstance(data, dict):
        return DEFAULT_DBUS_TIMEOUT_SECONDS

    try:
        timeout = parse_float(
            data.get(DBUS_TIMEOUT_KEY, DEFAULT_DBUS_TIMEOUT_SECONDS),
            "DBus timeout",
        )
    except ValueError:
        return DEFAULT_DBUS_TIMEOUT_SECONDS

    if timeout <= 0:
        return DEFAULT_DBUS_TIMEOUT_SECONDS
    return timeout


def save_statusd_settings(
    settings: StatusdSettings,
    path: Path | None = None,
) -> Path:
    target = settings_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = existing_settings_mapping(target)
    data.update(settings.to_mapping())
    if DBUS_TIMEOUT_KEY not in data:
        data[DBUS_TIMEOUT_KEY] = f"{DEFAULT_DBUS_TIMEOUT_SECONDS:g}"
    target.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def existing_settings_mapping(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def parse_int(value: object, label: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a whole number") from exc


def parse_float(value: object, label: str) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
