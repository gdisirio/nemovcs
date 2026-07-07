"""GitHub forge adapter, driven through the `gh` CLI."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Sequence

from nemovcs.forge.base import ForgeMatch, parse_remote_host


GITHUB_CLI = "gh"
GITHUB_PUBLIC_HOST = "github.com"


def gh_hosts_config_path() -> Path:
    """Return the path to `gh`'s hosts config (network-free host source)."""
    config_dir = os.environ.get("GH_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / "hosts.yml"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "gh" / "hosts.yml"


def parse_gh_hosts_config(text: str) -> list[str]:
    """Extract the hosts `gh` is authenticated for from its hosts.yml.

    Hosts are the top-level YAML keys (`github.com:`), so we read the
    unindented `key:` lines without needing a YAML dependency.
    """
    hosts: list[str] = []
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.endswith(":"):
            host = stripped[:-1].strip().strip("\"'").lower()
            if host:
                hosts.append(host)
    return hosts


def classify_github_host(
    host: str | None,
    authenticated_hosts: Sequence[str],
) -> ForgeMatch:
    if not host:
        return ForgeMatch.NONE
    if host == GITHUB_PUBLIC_HOST or host in authenticated_hosts:
        return ForgeMatch.STRONG
    if host.startswith("github."):
        return ForgeMatch.WEAK
    return ForgeMatch.NONE


class GitHubForge:
    id = "github"
    label = "GitHub"
    cli = GITHUB_CLI
    change_request_label = "Pull Request"

    def authenticated_hosts(self) -> list[str]:
        try:
            text = gh_hosts_config_path().read_text(encoding="utf-8")
        except OSError:
            return []
        return parse_gh_hosts_config(text)

    def match_remote(self, remote_url: str) -> ForgeMatch:
        return classify_github_host(
            parse_remote_host(remote_url),
            self.authenticated_hosts(),
        )

    def is_available(self) -> bool:
        return shutil.which(self.cli) is not None
