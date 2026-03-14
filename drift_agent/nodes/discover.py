"""Discover node: resolve consumer repos to scan.

Requires an explicit consumer-repos list — no org-wide code search is performed.
"""

from __future__ import annotations

import os
import re

from drift_agent.state import ConsumerRepo, DriftState

_REPO_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*/[a-zA-Z0-9][a-zA-Z0-9_.-]*$')
_GITHUB_URL_RE = re.compile(r'^https?://github\.com/([^/]+/[^/]+?)(?:\.git)?$')


def _normalize_repo(name: str) -> str:
    """Strip a full GitHub URL down to owner/repo if needed."""
    m = _GITHUB_URL_RE.match(name)
    return m.group(1) if m else name


def discover_consumers(state: DriftState) -> dict:
    token = state.get("token", "") or os.environ.get("ORG_READ_TOKEN", "")
    provider_repo = state.get("provider_repo", "")

    raw = [_normalize_repo(r.strip()) for r in state.get("consumer_repos", []) if r.strip()]
    invalid = [r for r in raw if not _REPO_RE.match(r)]
    for r in invalid:
        print(f"[discover] Skipping invalid repo name: {r!r}")
    explicit = [r for r in raw if _REPO_RE.match(r)]
    if not explicit:
        print("[discover] No consumer-repos specified — skipping consumer scan")
        return {"consumers": []}

    if not token:
        print("[discover] No token — skipping consumer scan")
        return {"consumers": []}

    consumers = [
        ConsumerRepo(
            full_name=name,
            clone_url=f"https://x-access-token:{token}@github.com/{name}.git",
        )
        for name in explicit
        if name != provider_repo
    ]
    print(f"[discover] Scanning {len(consumers)} explicit consumer repo(s): {[c.full_name for c in consumers]}")
    return {"consumers": consumers}
