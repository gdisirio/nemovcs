#!/usr/bin/env python3
"""Install DBus activation for the NemoVCS status daemon."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex


BUS_NAME = "io.github.gdisirio.NemoVCS.Statusd"
WRAPPER_NAME = "nemovcs-statusd"


@dataclass(frozen=True)
class StatusdActivationInstall:
    wrapper_path: Path
    service_path: Path


def wrapper_source(repo_root: Path) -> str:
    src_path = shlex.quote(str(repo_root / "src"))
    return f"""#!/bin/sh
set -eu

PYTHONPATH={src_path}${{PYTHONPATH:+":$PYTHONPATH"}}
export PYTHONPATH

exec python3 -m nemovcs statusd
"""


def service_source(wrapper_path: Path) -> str:
    return f"""[D-BUS Service]
Name={BUS_NAME}
Exec={shlex.quote(str(wrapper_path))}
"""


def default_bin_home() -> Path:
    return Path.home() / ".local" / "bin"


def default_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def service_dir(data_home: Path | None = None) -> Path:
    if data_home is None:
        data_home = default_data_home()
    return data_home / "dbus-1" / "services"


def install(
    repo_root: Path,
    *,
    bin_home: Path | None = None,
    data_home: Path | None = None,
) -> StatusdActivationInstall:
    if bin_home is None:
        bin_home = default_bin_home()

    bin_home.mkdir(parents=True, exist_ok=True)
    wrapper_path = bin_home / WRAPPER_NAME
    wrapper_path.write_text(wrapper_source(repo_root), encoding="utf-8")
    wrapper_path.chmod(0o755)

    services = service_dir(data_home)
    services.mkdir(parents=True, exist_ok=True)
    service_path = services / f"{BUS_NAME}.service"
    service_path.write_text(service_source(wrapper_path), encoding="utf-8")
    service_path.chmod(0o644)

    return StatusdActivationInstall(wrapper_path, service_path)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    installed = install(repo_root)
    print(f"Installed NemoVCS status daemon wrapper to {installed.wrapper_path}")
    print(f"Installed NemoVCS DBus service to {installed.service_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
