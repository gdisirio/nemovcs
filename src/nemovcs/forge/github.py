"""GitHub forge adapter, driven through the `gh` CLI."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Sequence

from nemovcs.forge.base import (
    FORGE_ACTION_DIALOG,
    FORGE_ACTION_LAUNCH,
    FORGE_ACTION_OUTPUT,
    ChangeRequestTemplate,
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
CR_LIST_ICON = "nemovcs-show-log"
CR_CREATE_ICON = "nemovcs-add"


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


PR_TEMPLATE_STEM = "pull_request_template"
PR_TEMPLATE_SUFFIXES = {"", ".md", ".markdown", ".txt"}


def _read_template(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def find_pr_templates(root: str | Path) -> list[ChangeRequestTemplate]:
    """Discover GitHub pull-request templates under a working tree.

    GitHub looks in the repository root, `.github/`, and `docs/`, accepting
    either a single `pull_request_template` file or a `PULL_REQUEST_TEMPLATE/`
    directory holding several named templates. Matching is case-insensitive on
    the conventional stem. All discovered directory templates are returned, plus
    a single-file template last as "Default" when one exists.
    """
    base = Path(root)
    search_dirs = [base, base / ".github", base / "docs"]
    dir_templates: list[ChangeRequestTemplate] = []
    single: ChangeRequestTemplate | None = None

    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_dir() and entry.name.lower() == PR_TEMPLATE_STEM:
                for item in sorted(entry.iterdir(), key=lambda p: p.name.lower()):
                    if item.is_file() and item.suffix.lower() in {
                        ".md", ".markdown", ".txt"
                    }:
                        body = _read_template(item)
                        if body is not None:
                            dir_templates.append(
                                ChangeRequestTemplate(item.stem, body)
                            )
            elif (
                single is None
                and entry.is_file()
                and entry.stem.lower() == PR_TEMPLATE_STEM
                and entry.suffix.lower() in PR_TEMPLATE_SUFFIXES
            ):
                body = _read_template(entry)
                if body is not None:
                    single = ChangeRequestTemplate("Default", body)

    return dir_templates + ([single] if single is not None else [])


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
        cr = self.change_request_label
        return [
            ForgeAction(
                id="open",
                label=f"Open on {self.label}",
                kind=FORGE_ACTION_LAUNCH,
                icon=OPEN_ICON,
            ),
            ForgeAction(
                id="cr-list",
                label=f"List {cr}s",
                kind=FORGE_ACTION_OUTPUT,
                icon=CR_LIST_ICON,
            ),
            ForgeAction(
                id="cr-create",
                label=f"Create {cr}...",
                kind=FORGE_ACTION_DIALOG,
                icon=CR_CREATE_ICON,
                **self._create_availability(context),
            ),
        ]

    def _create_availability(self, context: ForgeContext) -> dict:
        """Disable 'create' when the current branch cannot open a change request.

        A change request compares a feature branch against the default branch,
        so being on the default branch (when we can tell) makes it impossible.
        """
        if (
            context.branch is not None
            and context.default_branch is not None
            and context.branch == context.default_branch
        ):
            return {
                "enabled": False,
                "disabled_reason": (
                    f"Switch to a feature branch to open a {self.change_request_label}"
                ),
            }
        return {}

    def run(self, action_id: str, root: str) -> list[str]:
        if action_id == "open":
            return [self.cli, "browse"]
        if action_id == "cr-list":
            return [self.cli, "pr", "list"]
        return []

    def change_request_create_command(
        self, root: str, *, title: str, body: str, base: str | None = None
    ) -> list[str]:
        command = [self.cli, "pr", "create", "--title", title, "--body", body]
        if base:
            command += ["--base", base]
        return command

    def change_request_templates(self, root: str) -> list[ChangeRequestTemplate]:
        return find_pr_templates(root)

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
