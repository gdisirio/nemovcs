"""Forge registry and detection."""

from __future__ import annotations

from .base import Forge, ForgeMatch, parse_remote_host
from .github import GitHubForge


FORGES: tuple[Forge, ...] = (GitHubForge(),)


def registered_forges() -> tuple[Forge, ...]:
    return FORGES


def forge_by_id(forge_id: str) -> Forge | None:
    for forge in FORGES:
        if forge.id == forge_id:
            return forge
    return None


def detect_forge(remote_url: str) -> Forge | None:
    """Return the forge that most confidently recognizes `remote_url`.

    Asks each adapter for its match strength and picks the strongest, so a
    known/authenticated host wins over a name-only heuristic. Returns None when
    no forge recognizes the remote.
    """
    best: Forge | None = None
    best_strength = ForgeMatch.NONE
    for forge in FORGES:
        strength = forge.match_remote(remote_url)
        if strength > best_strength:
            best, best_strength = forge, strength
    return best if best_strength is not ForgeMatch.NONE else None
