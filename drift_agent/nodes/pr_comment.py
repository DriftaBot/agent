"""PR comment node: post a summary comment on the provider PR with links to opened consumer issues."""

from __future__ import annotations

import os

import httpx

from drift_agent.state import DriftState

_GITHUB_API = "https://api.github.com"
_COMMENT_MARKER = "<!-- drift-guard-pr-comment -->"
_MARKETPLACE_URL = "https://github.com/marketplace/actions/driftabot-agent"
_AGENT_LINK = '<a href="{url}" target="_blank">DriftaBot</a>'.format(url=_MARKETPLACE_URL)


def pr_comment(state: DriftState) -> dict:
    issue_urls = state.get("issue_urls", {})
    pr_number = state.get("pr_number", 0)
    provider_repo = state.get("provider_repo", "") or os.environ.get("GITHUB_REPOSITORY", "")
    github_token = state.get("github_token", "") or os.environ.get("GITHUB_TOKEN", "")
    dry_run = state.get("dry_run", False)

    if not pr_number or not provider_repo:
        return {}

    diff = state.get("diff")
    breaking = [c for c in diff.changes if c.severity == "breaking"] if diff else []
    consumer_repos = state.get("consumer_repos", [])

    if issue_urls:
        body = _build_comment(issue_urls, breaking, provider_repo)
    elif not consumer_repos:
        body = _build_not_configured_comment(breaking)
    else:
        body = None  # repos were scanned but none affected; may update to "all clear"

    if dry_run:
        if body:
            print(f"\n[pr_comment] DRY RUN — PR comment for {provider_repo}#{pr_number}:\n{body}\n")
        else:
            print(f"\n[pr_comment] DRY RUN — no active issues; would clear stale comment on {provider_repo}#{pr_number} if present\n")
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
        existing_id = _find_existing_comment(client, provider_repo, pr_number)

        if body:
            _upsert_pr_comment(client, provider_repo, pr_number, body, existing_id)
        elif existing_id:
            # Breaking changes gone — update stale comment to "all clear"
            _upsert_pr_comment(client, provider_repo, pr_number, _build_clear_comment(), existing_id)
        # else: no previous comment and nothing to report — stay silent

    return {}


def _build_comment(issue_urls: dict[str, str], breaking: list, provider_repo: str) -> str:
    n = len(issue_urls)
    noun = "repo" if n == 1 else "repos"
    count = len(breaking)
    plural = "s" if count != 1 else ""

    lines = [
        _COMMENT_MARKER,
        f"## \u26a0\ufe0f API {_AGENT_LINK} Report \u2014 {count} breaking change{plural} detected",
        "",
        "### Breaking changes",
        "",
        "| Path | Description |",
        "| ---- | ----------- |",
    ]
    for c in breaking:
        lines.append(f"| `{c.path}` | {c.description} |")

    lines += [
        "",
        f"### Affected consumer {noun}",
        "",
        f"Issues have been opened in **{n}** affected consumer {noun}:",
        "",
        "| Issue |",
        "| ----- |",
    ]
    for repo, url in sorted(issue_urls.items()):
        issue_num = url.rstrip("/").split("/")[-1]
        issue_link = f'<a href="{url}" target="_blank">{repo} #{issue_num}</a>'
        lines.append(f"| {issue_link} |")

    lines += [
        "",
        "_Update consumer repos before merging this PR._",
    ]
    return "\n".join(lines)


def _build_not_configured_comment(breaking: list) -> str:
    count = len(breaking)
    plural = "s" if count != 1 else ""
    lines = [
        _COMMENT_MARKER,
        f"## \u26a0\ufe0f API {_AGENT_LINK} Report \u2014 {count} breaking change{plural} detected, no consumer scan conducted",
        "",
        "### Breaking changes",
        "",
        "| Path | Description |",
        "| ---- | ----------- |",
    ]
    for c in breaking:
        lines.append(f"| `{c.path}` | {c.description} |")
    lines += [
        "",
        "No consumer repos have been configured — scan skipped.",
        "",
        "Add the `consumer-repos` input to enable scanning:",
        "",
        "```yaml",
        "- uses: DriftaBot/agent@v1",
        "  with:",
        "    org-read-token: ${{ secrets.ORG_READ_TOKEN }}",
        "    consumer-repos: |",
        "      your-org/service-a",
        "      your-org/service-b",
        "```",
    ]
    return "\n".join(lines)


def _build_clear_comment() -> str:
    return "\n".join([
        _COMMENT_MARKER,
        f"## \u2705 API {_AGENT_LINK} Report \u2014 no breaking changes detected",
        "",
        "All previously affected consumer repos have been updated, or no breaking changes remain.",
        "",
        "_Update consumer repos before merging this PR._",
    ])


def _find_existing_comment(client: httpx.Client, provider_repo: str, pr_number: int) -> int | None:
    """Return the comment id of an existing drift-agent PR comment, or None."""
    try:
        resp = client.get(
            f"{_GITHUB_API}/repos/{provider_repo}/issues/{pr_number}/comments",
            params={"per_page": 100},
        )
        resp.raise_for_status()
        existing = [c for c in resp.json() if _COMMENT_MARKER in c.get("body", "")]
        return existing[0]["id"] if existing else None
    except httpx.HTTPError:
        return None


def _upsert_pr_comment(
    client: httpx.Client,
    provider_repo: str,
    pr_number: int,
    body: str,
    existing_id: int | None,
):
    try:
        if existing_id:
            client.patch(
                f"{_GITHUB_API}/repos/{provider_repo}/issues/{pr_number}/comments/{existing_id}",
                json={"body": body},
            ).raise_for_status()
            print(f"[pr_comment] Updated drift-agent comment on {provider_repo}#{pr_number}")
        else:
            client.post(
                f"{_GITHUB_API}/repos/{provider_repo}/issues/{pr_number}/comments",
                json={"body": body},
            ).raise_for_status()
            print(f"[pr_comment] Posted drift-agent comment on {provider_repo}#{pr_number}")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            print(f"::warning::drift-agent: missing 'issues: write' permission — PR comment not posted on {provider_repo}#{pr_number}")
        else:
            print(f"[pr_comment] Failed to post PR comment: {e}")
    except httpx.HTTPError as e:
        print(f"[pr_comment] Failed to post PR comment: {e}")
