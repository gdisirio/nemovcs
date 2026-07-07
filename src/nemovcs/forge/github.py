"""GitHub forge adapter, driven through the `gh` CLI."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Sequence

from nemovcs.forge.base import (
    FORGE_ACTION_LAUNCH,
    ForgeAccount,
    ForgeAction,
    ForgeContext,
    ForgeMatch,
    parse_remote_host,
)


GITHUB_CLI = "gh"
GITHUB_PUBLIC_HOST = "github.com"
GITHUB_ICON = "nemovcs-git"
OPEN_ICON = "web-browser"


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


def parse_gh_accounts(text: str, host: str = GITHUB_PUBLIC_HOST) -> list[ForgeAccount]:
    """Parse the accounts `gh` is logged in as for `host` from its hosts.yml.

    Multi-account hosts.yml nests account names under a `users:` map and names
    the active one in a host-level `user:` key. Single-account configs only have
    the host-level `user:`. Parsed by indentation to avoid a YAML dependency.
    """
    block: list[tuple[int, str]] = []
    in_block = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            key = line.strip()
            in_block = (
                key.endswith(":")
                and key[:-1].strip().strip("\"'").lower() == host
            )
            continue
        if in_block:
            block.append((indent, line.strip()))

    if not block:
        return []

    base_indent = min(indent for indent, _ in block)
    active: str | None = None
    names: list[str] = []
    in_users = False
    users_child_indent: int | None = None
    for indent, stripped in block:
        if indent == base_indent:
            in_users = stripped == "users:"
            users_child_indent = None
            if stripped.startswith("user:"):
                active = stripped.split(":", 1)[1].strip().strip("\"'") or None
            continue
        if in_users:
            if users_child_indent is None:
                users_child_indent = indent
            if indent == users_child_indent and stripped.endswith(":"):
                names.append(stripped[:-1].strip().strip("\"'"))

    if not names and active:
        names = [active]
    return [ForgeAccount(name=name, active=(name == active)) for name in names]


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
    icon = GITHUB_ICON
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

    def actions(self, context: ForgeContext) -> list[ForgeAction]:
        return [
            ForgeAction(
                id="open",
                label=f"Open on {self.label}",
                kind=FORGE_ACTION_LAUNCH,
                icon=OPEN_ICON,
            ),
        ]

    def run(self, action_id: str, root: str) -> list[str]:
        if action_id == "open":
            return [self.cli, "browse"]
        return []

    def publish_command(self, root: str, name: str, private: bool) -> list[str]:
        visibility = "--private" if private else "--public"
        return [
            self.cli,
            "repo",
            "create",
            name,
            "--source",
            str(root),
            "--push",
            visibility,
        ]

    def accounts(self) -> list[ForgeAccount]:
        try:
            text = gh_hosts_config_path().read_text(encoding="utf-8")
        except OSError:
            return []
        return parse_gh_accounts(text)

    def switch_account_command(self, name: str) -> list[str]:
        return [self.cli, "auth", "switch", "--hostname", GITHUB_PUBLIC_HOST, "--user", name]
