"""Forge interfaces.

A "forge" is a hosting service layered on top of a VCS backend -- GitHub,
GitLab, and so on -- driven through its own command-line tool (`gh`, `glab`,
`tea`). Forges are detected from a worktree's remote URL: each adapter decides
whether it recognizes a remote, so dispatch never needs a central host table.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol
from urllib.parse import urlsplit


# How the plugin should surface a forge action.
FORGE_ACTION_LAUNCH = "launch"   # spawn the command (e.g. open a browser)
FORGE_ACTION_OUTPUT = "output"   # run the command, show output in the logger
FORGE_ACTION_DIALOG = "dialog"   # hand off to a GTK dialog in ui/


class ForgeMatch(IntEnum):
    """How confidently a forge recognizes a remote.

    Ordered so `detect_forge` can pick the strongest match: a host known to a
    forge (public host or one its CLI is authenticated for) beats a name-only
    heuristic, which lets self-hosted instances resolve without a central
    arbiter.
    """

    NONE = 0
    WEAK = 1
    STRONG = 2


def parse_remote_host(remote_url: str) -> str | None:
    """Return the lowercased host of a git remote URL, or None.

    Handles the three shapes git remotes come in -- `https://host/path`,
    `ssh://user@host:port/path`, and the scp-like `user@host:path` (which is not
    a valid URL and needs special handling).
    """
    text = (remote_url or "").strip()
    if not text:
        return None

    if "://" in text:
        netloc = urlsplit(text).netloc
        if "@" in netloc:
            netloc = netloc.rsplit("@", 1)[1]
        if netloc.startswith("[") and "]" in netloc:
            host = netloc[1 : netloc.index("]")]
        else:
            host = netloc.split(":", 1)[0]
        return host.lower() or None

    # scp-like: [user@]host:path -- the part before the first colon is the
    # host (optionally prefixed with user@) and must not contain a slash.
    if ":" in text:
        left = text.split(":", 1)[0]
        if "/" in left:
            return None
        host = left.rsplit("@", 1)[-1] if "@" in left else left
        return host.lower() or None

    return None


@dataclass(frozen=True)
class ForgeContext:
    """Cheap, network-free signals gathered once per menu build.

    Passed to `Forge.actions` so an adapter can decide which actions to show and
    whether each is enabled without doing any I/O of its own.
    """

    root: str
    remote_url: str = ""
    branch: str | None = None
    default_branch: str | None = None
    worktree_dirty: bool = False
    selection: tuple[str, ...] = ()


@dataclass(frozen=True)
class ForgeAction:
    """A menu action a forge advertises for a given context."""

    id: str
    label: str
    kind: str = FORGE_ACTION_LAUNCH
    icon: str | None = None
    enabled: bool = True
    disabled_reason: str = ""


@dataclass(frozen=True)
class ForgeAccount:
    """An account the forge CLI is logged in as."""

    name: str
    active: bool = False


class Forge(Protocol):
    id: str
    label: str
    cli: str
    icon: str
    change_request_label: str

    def match_remote(self, remote_url: str) -> ForgeMatch: ...

    def is_available(self) -> bool: ...

    def actions(self, context: ForgeContext) -> list[ForgeAction]: ...

    def run(self, action_id: str, root: str) -> list[str]: ...

    def publish_command(self, root: str, name: str, private: bool) -> list[str]: ...

    def change_request_create_command(
        self, root: str, *, title: str, body: str, base: str | None = None
    ) -> list[str]: ...

    def accounts(self) -> list[ForgeAccount]: ...

    def switch_account_command(self, name: str) -> list[str]: ...
