"""Forge interfaces.

A "forge" is a hosting service layered on top of a VCS backend -- GitHub,
GitLab, and so on -- driven through its own command-line tool (`gh`, `glab`,
`tea`). Forges are detected from a worktree's remote URL: each adapter decides
whether it recognizes a remote, so dispatch never needs a central host table.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Protocol
from urllib.parse import urlsplit


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


class Forge(Protocol):
    id: str
    label: str
    cli: str
    change_request_label: str

    def match_remote(self, remote_url: str) -> ForgeMatch: ...

    def is_available(self) -> bool: ...

    def open_in_browser_command(self, root: str) -> list[str]: ...
