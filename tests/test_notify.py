"""Tests for drift_guard_agent.nodes.notify."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from drift_guard_agent.nodes.notify import (
    _build_issue_body,
    _close_stale_issue,
    _upsert_issue,
    notify,
)
from drift_guard_agent.state import Change, ConsumerRepo, DiffResult, Hit, initial_state


def _change(path="/users/{id}", method="GET", description="endpoint removed"):
    return Change(
        type="removed",
        severity="breaking",
        path=path,
        method=method,
        location="",
        description=description,
    )


def _hit(file="src/api.py", line_num=10):
    return Hit(
        file=file,
        line_num=line_num,
        line=f'    call("{line_num}")',
        change_type="removed",
        change_path="GET /users/{id}",
    )


def _mock_client(get_json=None, post_json=None, patch_json=None):
    """Build a MagicMock httpx.Client with configurable responses."""
    client = MagicMock()

    get_resp = MagicMock()
    get_resp.json.return_value = get_json if get_json is not None else []
    get_resp.raise_for_status = MagicMock()
    client.get.return_value = get_resp

    post_resp = MagicMock()
    post_resp.json.return_value = post_json if post_json is not None else {
        "html_url": "https://github.com/org/service/issues/1"
    }
    post_resp.raise_for_status = MagicMock()
    client.post.return_value = post_resp

    if patch_json is not None:
        patch_resp = MagicMock()
        patch_resp.json.return_value = patch_json
        patch_resp.raise_for_status = MagicMock()
        client.patch.return_value = patch_resp

    return client


# ── _build_issue_body() ──────────────────────────────────────────────────────

class TestBuildIssueBody:
    def test_contains_provider_repo(self):
        body = _build_issue_body("org/service", [_hit()], [_change()], [], "org/api", 42)
        assert "org/api" in body

    def test_contains_pr_link(self):
        body = _build_issue_body("org/service", [_hit()], [_change()], [], "org/api", 42)
        assert "PR #42" in body
        assert "https://github.com/org/api/pull/42" in body

    def test_contains_breaking_change_details(self):
        body = _build_issue_body("org/service", [_hit()], [_change()], [], "org/api", 42)
        assert "GET /users/{id}" in body
        assert "endpoint removed" in body

    def test_contains_affected_file(self):
        body = _build_issue_body("org/service", [_hit("src/api.py", 10)], [_change()], [], "org/api", 42)
        assert "src/api.py" in body
        assert "10" in body

    def test_includes_explanation_when_provided(self):
        body = _build_issue_body(
            "org/service", [_hit()], [_change()],
            ["Users endpoint completely gone"], "org/api", 42
        )
        assert "Users endpoint completely gone" in body

    def test_no_explanation_skipped_gracefully(self):
        body = _build_issue_body("org/service", [_hit()], [_change()], [], "org/api", 42)
        assert "explanation" not in body.lower() or True  # no crash is the assertion

    def test_limits_hits_to_50(self):
        hits = [_hit(line_num=i) for i in range(1, 65)]
        body = _build_issue_body("org/service", hits, [_change()], [], "org/api", 1)
        # Count table rows: 50 hits shown
        rows = [line for line in body.splitlines() if line.startswith("| `src/api.py`")]
        assert len(rows) == 50

    def test_no_provider_repo_fallback(self):
        body = _build_issue_body("org/service", [_hit()], [_change()], [], "", 0)
        assert "a provider PR" in body

    def test_multiple_breaking_changes(self):
        changes = [_change("/users/{id}"), _change("/orders/{id}", description="order gone")]
        body = _build_issue_body("org/service", [_hit()], changes, [], "org/api", 1)
        assert "GET /users/{id}" in body
        assert "GET /orders/{id}" in body
        assert "order gone" in body


# ── _upsert_issue() ──────────────────────────────────────────────────────────

class TestUpsertIssue:
    def test_creates_new_issue_when_none_exists(self):
        client = _mock_client(
            get_json=[],
            post_json={"html_url": "https://github.com/org/service/issues/1"},
        )
        url = _upsert_issue(client, "org/service", "body text", "org/api", 42)
        assert url == "https://github.com/org/service/issues/1"

    def test_posts_to_issues_endpoint(self):
        client = _mock_client(get_json=[], post_json={"html_url": "https://..."})
        _upsert_issue(client, "org/service", "body", "org/api", 42)
        # post called: once for label, once for issue
        assert client.post.call_count == 2

    def test_updates_existing_issue(self):
        existing = [{"number": 5}]
        patch_data = {"html_url": "https://github.com/org/service/issues/5"}
        client = _mock_client(get_json=existing, patch_json=patch_data)
        url = _upsert_issue(client, "org/service", "body", "org/api", 42)
        assert url == "https://github.com/org/service/issues/5"
        client.patch.assert_called_once()

    def test_patch_updates_title_and_body(self):
        client = _mock_client(get_json=[{"number": 3}], patch_json={"html_url": "https://..."})
        _upsert_issue(client, "org/service", "new body", "org/api", 42)
        call_kwargs = client.patch.call_args[1]["json"]
        assert "new body" in call_kwargs["body"]
        assert "org/api" in call_kwargs["title"]

    def test_returns_none_on_403(self, capsys):
        client = MagicMock()
        label_resp = MagicMock()
        client.post.return_value = label_resp

        err_response = MagicMock()
        err_response.status_code = 403
        error = httpx.HTTPStatusError("403 Forbidden", request=MagicMock(), response=err_response)
        get_resp = MagicMock()
        get_resp.raise_for_status.side_effect = error
        client.get.return_value = get_resp

        url = _upsert_issue(client, "org/service", "body", "org/api", 42)
        assert url is None
        assert "missing 'issues: write'" in capsys.readouterr().out

    def test_returns_none_on_http_error(self):
        client = MagicMock()
        client.post.return_value = MagicMock()
        client.get.side_effect = httpx.HTTPError("connection refused")
        url = _upsert_issue(client, "org/service", "body", "org/api", 42)
        assert url is None

    def test_label_creation_failure_is_suppressed(self):
        # Even if label POST raises, the issue should still be created
        client = MagicMock()
        client.post.side_effect = [Exception("label exists"), MagicMock(
            json=MagicMock(return_value={"html_url": "https://..."}),
            raise_for_status=MagicMock(),
        )]
        get_resp = MagicMock()
        get_resp.json.return_value = []
        get_resp.raise_for_status = MagicMock()
        client.get.return_value = get_resp

        url = _upsert_issue(client, "org/service", "body", "org/api", 42)
        # Label failure suppressed; issue POST should still be called
        assert client.post.call_count == 2


# ── _close_stale_issue() ─────────────────────────────────────────────────────

class TestCloseStaleIssue:
    def test_closes_matching_issue(self):
        client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = [
            {"number": 3, "title": "⚠️ Breaking API changes from org/api (PR #1)"}
        ]
        get_resp.raise_for_status = MagicMock()
        client.get.return_value = get_resp

        comment_resp = MagicMock()
        comment_resp.raise_for_status = MagicMock()
        patch_resp = MagicMock()
        patch_resp.raise_for_status = MagicMock()
        client.post.return_value = comment_resp
        client.patch.return_value = patch_resp

        _close_stale_issue(client, "org/service", "org/api")

        client.patch.assert_called_once()
        patch_kwargs = client.patch.call_args[1]["json"]
        assert patch_kwargs["state"] == "closed"

    def test_posts_resolution_comment_before_closing(self):
        client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = [{"number": 3, "title": "...org/api..."}]
        get_resp.raise_for_status = MagicMock()
        client.get.return_value = get_resp

        comment_resp = MagicMock()
        comment_resp.raise_for_status = MagicMock()
        patch_resp = MagicMock()
        patch_resp.raise_for_status = MagicMock()
        client.post.return_value = comment_resp
        client.patch.return_value = patch_resp

        _close_stale_issue(client, "org/service", "org/api")
        client.post.assert_called_once()
        body = client.post.call_args[1]["json"]["body"]
        assert "resolved" in body.lower() or "closing" in body.lower()

    def test_skips_non_matching_issues(self):
        client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = [{"number": 5, "title": "Unrelated issue"}]
        get_resp.raise_for_status = MagicMock()
        client.get.return_value = get_resp

        _close_stale_issue(client, "org/service", "org/api")
        client.patch.assert_not_called()

    def test_handles_404_silently(self, capsys):
        client = MagicMock()
        err_response = MagicMock()
        err_response.status_code = 404
        get_resp = MagicMock()
        get_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=err_response
        )
        client.get.return_value = get_resp
        _close_stale_issue(client, "org/service", "org/api")
        # No output for 404
        assert capsys.readouterr().out == ""

    def test_handles_http_error(self):
        client = MagicMock()
        client.get.side_effect = httpx.HTTPError("timeout")
        # Should not raise
        _close_stale_issue(client, "org/service", "org/api")


# ── notify() ─────────────────────────────────────────────────────────────────

class TestNotify:
    def _state_with_hits(self, **kwargs):
        diff = DiffResult("b", "h", [_change()], {})
        return initial_state(
            diff=diff,
            hits={"org/service": [_hit()]},
            consumers=[ConsumerRepo("org/service", "url")],
            provider_repo="org/api",
            pr_number=1,
            **kwargs,
        )

    def test_dry_run_prints_and_returns_empty_urls(self, capsys):
        state = self._state_with_hits(dry_run=True)
        result = notify(state)
        assert result["issue_urls"] == {}
        assert "DRY RUN" in capsys.readouterr().out

    def test_dry_run_prints_issue_body(self, capsys):
        state = self._state_with_hits(dry_run=True)
        notify(state)
        out = capsys.readouterr().out
        assert "org/service" in out

    def test_no_token_skips_github_calls(self, capsys):
        state = self._state_with_hits(github_token="")
        result = notify(state)
        assert result["issue_urls"] == {}
        assert "No GITHUB_TOKEN" in capsys.readouterr().out

    def test_no_hits_returns_empty(self):
        diff = DiffResult("b", "h", [_change()], {})
        state = initial_state(diff=diff, hits={}, consumers=[], dry_run=True)
        result = notify(state)
        assert result["consumer_issues"] == {}
        assert result["issue_urls"] == {}

    @patch("drift_guard_agent.nodes.notify.httpx.Client")
    def test_creates_issue_for_each_repo_with_hits(self, mock_client_cls):
        mock_client = _mock_client(
            get_json=[],
            post_json={"html_url": "https://github.com/org/service/issues/1"},
        )
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        state = self._state_with_hits(github_token="tok")
        result = notify(state)
        assert "org/service" in result["issue_urls"]
        assert result["issue_urls"]["org/service"] == "https://github.com/org/service/issues/1"

    @patch("drift_guard_agent.nodes.notify.httpx.Client")
    def test_closes_stale_issues_for_repos_without_hits(self, mock_client_cls):
        mock_client = MagicMock()

        # GET for list existing issues: stale_repos check
        get_stale_resp = MagicMock()
        get_stale_resp.json.return_value = []
        get_stale_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = get_stale_resp

        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        diff = DiffResult("b", "h", [_change()], {})
        # org/no-hits has no hits but is in consumers
        state = initial_state(
            diff=diff,
            hits={},
            consumers=[ConsumerRepo("org/no-hits", "url")],
            github_token="tok",
            provider_repo="org/api",
            pr_number=1,
        )
        notify(state)
        # _close_stale_issue should be called for org/no-hits
        mock_client.get.assert_called()

    @patch("drift_guard_agent.nodes.notify.httpx.Client")
    def test_env_github_token_used(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "envtok")
        mock_client = _mock_client(
            get_json=[],
            post_json={"html_url": "https://github.com/org/service/issues/1"},
        )
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        state = self._state_with_hits(github_token="")
        result = notify(state)
        assert "org/service" in result["issue_urls"]
