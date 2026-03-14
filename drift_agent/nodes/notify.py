"""Notify node: open / update a GitHub Issue in each affected consumer repo."""

from __future__ import annotations

import os

import httpx

from drift_agent.state import DriftState

_GITHUB_API = "https://api.github.com"
_ISSUE_LABEL = "drift-guard"


def notify(state: DriftState) -> dict:
    diff = state["diff"]
    hits_by_repo = state.get("hits", {})
    explanations = state.get("explanations", {})
    dry_run = state.get("dry_run", False)
    github_token = state.get("github_token", "") or os.environ.get("GITHUB_TOKEN", "")
    pr_number = state.get("pr_number", 0)
    provider_repo = state.get("provider_repo", "") or os.environ.get("GITHUB_REPOSITORY", "")

    breaking = [c for c in diff.changes if c.severity == "breaking"]
    consumer_issues: dict[str, str] = {}

    for repo, hits in hits_by_repo.items():
        body = _build_issue_body(
            repo=repo,
            hits=hits,
            breaking=breaking,
            explanations=explanations.get(repo, []),
            provider_repo=provider_repo,
            pr_number=pr_number,
        )
        consumer_issues[repo] = body

    if dry_run:
        print("\n[notify] DRY RUN — no GitHub requests sent\n")
        print("=" * 60)
        for repo, body in consumer_issues.items():
            print(f"\nISSUE [{repo}]:\n{body}\n")
        print("=" * 60)
        return {"consumer_issues": consumer_issues, "issue_urls": {}}

    if not github_token:
        print("[notify] No GITHUB_TOKEN — skipping issue creation")
        return {"consumer_issues": consumer_issues, "issue_urls": {}}

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    issue_urls: dict[str, str] = {}
    with httpx.Client(headers=headers, timeout=30) as client:
        for repo, body in consumer_issues.items():
            url = _upsert_issue(client, repo, body, provider_repo, pr_number)
            if url:
                issue_urls[repo] = url

        # Close stale issues in repos that were discovered but no longer have hits
        all_consumers = [c.full_name for c in state.get("consumers", [])]
        stale_repos = [r for r in all_consumers if r not in issue_urls]
        for repo in stale_repos:
            _close_stale_issue(client, repo, provider_repo)

    return {"consumer_issues": consumer_issues, "issue_urls": issue_urls}


def _build_issue_body(
    repo: str,
    hits,
    breaking: list,
    explanations: list[str],
    provider_repo: str,
    pr_number: int,
) -> str:
    pr_link = (
        f"[PR #{pr_number}](https://github.com/{provider_repo}/pull/{pr_number})"
        if provider_repo and pr_number
        else f"PR #{pr_number}" if pr_number else "a provider PR"
    )

    lines = [
        f"## ⚠️ Breaking API changes from `{provider_repo}` ({pr_link})",
        "",
        "Your repository references API endpoints that have been removed or changed.",
        "",
        "### Breaking changes",
        "",
    ]

    for i, c in enumerate(breaking):
        lines.append(f"- `{c.method} {c.path}` — {c.description}")
        if i < len(explanations) and explanations[i]:
            lines.append(f"  > {explanations[i]}")

    lines += [
        "",
        "### Affected files in this repo",
        "",
        "| File | Line | Referenced path |",
        "| ---- | ---- | --------------- |",
    ]
    for h in hits[:50]:
        lines.append(f"| `{h.file}` | {h.line_num} | `{h.change_path}` |")

    lines += [
        "",
        "**Action required:** Update these references before the provider PR is merged.",
        "",
        "---",
        f"_Opened by [Drift Agent](https://github.com/DriftaBot/agent) · {pr_link}_",
    ]
    return "\n".join(lines)


def _upsert_issue(
    client: httpx.Client,
    repo: str,
    body: str,
    provider_repo: str,
    pr_number: int,
) -> str | None:
    """Create or update a drift-agent issue in repo. Returns the issue HTML URL or None on failure."""
    title = f"⚠️ Breaking API changes from {provider_repo}" + (f" (PR #{pr_number})" if pr_number else "")

    # Ensure the label exists
    try:
        client.post(
            f"{_GITHUB_API}/repos/{repo}/labels",
            json={"name": _ISSUE_LABEL, "color": "e11d48", "description": "API drift impact"},
        )
    except Exception:
        pass

    try:
        # Check for an existing open issue with our label
        resp = client.get(
            f"{_GITHUB_API}/repos/{repo}/issues",
            params={"labels": _ISSUE_LABEL, "state": "open", "per_page": 1},
        )
        resp.raise_for_status()
        existing = resp.json()

        if existing:
            issue_number = existing[0]["number"]
            r = client.patch(
                f"{_GITHUB_API}/repos/{repo}/issues/{issue_number}",
                json={"title": title, "body": body},
            )
            r.raise_for_status()
            print(f"[notify] Updated issue #{issue_number} in {repo}")
            return r.json().get("html_url")
        else:
            r = client.post(
                f"{_GITHUB_API}/repos/{repo}/issues",
                json={"title": title, "body": body, "labels": [_ISSUE_LABEL]},
            )
            r.raise_for_status()
            print(f"[notify] Opened issue in {repo}")
            return r.json().get("html_url")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            print(f"::warning::drift-agent: missing 'issues: write' permission for {repo} — issue not created")
        else:
            print(f"[notify] Failed to upsert issue in {repo}: {e}")
    except httpx.HTTPError as e:
        print(f"[notify] Failed to upsert issue in {repo}: {e}")
    return None


def _close_stale_issue(client: httpx.Client, repo: str, provider_repo: str):
    """Close any open drift-agent issue in repo that references provider_repo."""
    try:
        resp = client.get(
            f"{_GITHUB_API}/repos/{repo}/issues",
            params={"labels": _ISSUE_LABEL, "state": "open", "per_page": 10},
        )
        resp.raise_for_status()
        matching = [i for i in resp.json() if provider_repo in i.get("title", "")]
        for issue in matching:
            n = issue["number"]
            client.post(
                f"{_GITHUB_API}/repos/{repo}/issues/{n}/comments",
                json={"body": "✅ Breaking changes resolved — closing this issue."},
            ).raise_for_status()
            client.patch(
                f"{_GITHUB_API}/repos/{repo}/issues/{n}",
                json={"state": "closed"},
            ).raise_for_status()
            print(f"[notify] Closed stale issue #{n} in {repo}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            print(f"[notify] Could not close stale issue in {repo}: {e}")
    except httpx.HTTPError as e:
        print(f"[notify] Could not close stale issue in {repo}: {e}")
