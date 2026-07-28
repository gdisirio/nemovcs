"""Helpers for launching NemoVCS child commands."""

from __future__ import annotations

import sys
from typing import Sequence


def resolved_command(command: Sequence[str]) -> list[str]:
    """Run internal commands through the current Python environment."""

    if command and command[0] == "nemovcs":
        return [sys.executable, "-m", *command]
    return list(command)
