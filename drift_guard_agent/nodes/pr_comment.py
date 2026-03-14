"""PR comment node: post a summary comment on the provider PR with links to opened consumer issues."""

from __future__ import annotations

import os

import httpx

from drift_guard_agent.state import DriftState

_GITHUB_API = "https://api.github.com"
_COMMENT_MARKER = "<!-- drift-guard-pr-comment -->"
_MARKETPLACE_URL = "https://github.com/marketplace/actions/api-drift-agent"


def pr_comment(state: DriftState) -> dict:
    issue_urls = state.get("issue_urls", {})
    pr_number = state.get("pr_number", 0)
    provider_repo = state.get("provider_repo", "") or os.environ.get("GITHUB_REPOSITORY", "")
    github_token = state.get("github_token", "") or os.environ.get("GITHUB_TOKEN", "")
    dry_run = state.get("dry_run", False)

    if not issue_urls or not pr_number or not provider_repo:
        return {}

    diff = state.get("diff")
    breaking = [c for c in diff.changes if c.severity == "breaking"] if diff else []
    body = _build_comment(issue_urls, breaking, provider_repo)

    if dry_run:
        print(f"\n[pr_comment] DRY RUN — PR comment for {provider_repo}#{pr_number}:\n{body}\n")
        return {}

    if not github_token:
        print("[pr_comment] No GITHUB_TOKEN — skipping PR comment")
        return {}

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers, timeout=30) as client:
        _upsert_pr_comment(client, provider_repo, pr_number, body)

    return {}


def _build_comment(issue_urls: dict[str, str], breaking: list, provider_repo: str) -> str:
    n = len(issue_urls)
    noun = "repo" if n == 1 else "repos"
    count = len(breaking)

    lines = [
        _COMMENT_MARKER,
        f"## ⚠️ API <a href=\"{_MARKETPLACE_URL}\" target=\"_blank\">DriftAgent</a> Report — {count} breaking change{\"s\" if count != 1 else \"\"} detected",
        "",
        "### Breaking changes",
        "",
        "| Method | Path | Description |",
        "| ------ | ---- | ----------- |",
    ]
    for c in breaking:
        lines.append(f"| `{c.method}` | `{c.path}` | {c.description} |")

    lines += [
        "",
        f"### Affected consumer {noun}",
        "",
        f"Issues have been opened in **{n}** affected consumer {noun}:",
        "",
        "| Consumer | Issue |",
        "| -------- | ----- |",
    ]
    for repo, url in sorted(issue_urls.items()):
        repo_url = f"https://github.com/{repo}"
        lines.append(f"| [{repo}]({repo_url}) | {url} |")

    lines += [
        "",
        "_Update consumer repos before merging this PR._",
    ]
    return "\n".join(lines)


def _upsert_pr_comment(client: httpx.Client, provider_repo: str, pr_number: int, body: str):
    try:
        # Search for existing drift-guard comment on this PR
        resp = client.get(
            f"{_GITHUB_API}/repos/{provider_repo}/issues/{pr_number}/comments",
            params={"per_page": 100},
        )
        resp.raise_for_status()
        existing = [c for c in resp.json() if _COMMENT_MARKER in c.get("body", "")]

        if existing:
            comment_id = existing[0]["id"]
            client.patch(
                f"{_GITHUB_API}/repos/{provider_repo}/issues/{pr_number}/comments/{comment_id}",
                json={"body": body},
            ).raise_for_status()
            print(f"[pr_comment] Updated drift-guard comment on {provider_repo}#{pr_number}")
        else:
            client.post(
                f"{_GITHUB_API}/repos/{provider_repo}/issues/{pr_number}/comments",
                json={"body": body},
            ).raise_for_status()
            print(f"[pr_comment] Posted drift-guard comment on {provider_repo}#{pr_number}")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            print(f"::warning::drift-guard-agent: missing 'issues: write' permission — PR comment not posted on {provider_repo}#{pr_number}")
        else:
            print(f"[pr_comment] Failed to post PR comment: {e}")
    except httpx.HTTPError as e:
        print(f"[pr_comment] Failed to post PR comment: {e}")
