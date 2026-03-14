"""Tests for drift_guard_agent.nodes.pr_comment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from drift_guard_agent.nodes.pr_comment import (
    _COMMENT_MARKER,
    _build_clear_comment,
    _build_comment,
    _build_not_configured_comment,
    _find_existing_comment,
    _upsert_pr_comment,
    pr_comment,
)
from drift_guard_agent.state import Change, DiffResult, initial_state


def _change(path="/users/{id}", description="endpoint removed"):
    return Change(
        type="removed",
        severity="breaking",
        path=path,
        method="GET",
        location="",
        description=description,
    )


# ── _build_comment() ─────────────────────────────────────────────────────────

class TestBuildComment:
    def test_contains_marker(self):
        body = _build_comment({"org/svc": "https://..."}, [_change()], "org/api")
        assert _COMMENT_MARKER in body

    def test_contains_breaking_change_path(self):
        body = _build_comment({"org/svc": "https://..."}, [_change("/users/{id}")], "org/api")
        assert "/users/{id}" in body

    def test_contains_breaking_change_description(self):
        body = _build_comment({"org/svc": "https://..."}, [_change(description="gone")], "org/api")
        assert "gone" in body

    def test_contains_repo_link(self):
        body = _build_comment({"org/svc": "https://github.com/org/svc/issues/1"}, [_change()], "org/api")
        assert "https://github.com/org/svc" in body
        assert "org/svc" in body

    def test_contains_issue_url(self):
        url = "https://github.com/org/svc/issues/5"
        body = _build_comment({"org/svc": url}, [_change()], "org/api")
        assert url in body

    def test_singular_repo_noun(self):
        body = _build_comment({"org/a": "https://..."}, [_change()], "org/api")
        assert "1 affected consumer repo" in body or "**1** affected consumer repo" in body

    def test_plural_repo_noun(self):
        body = _build_comment(
            {"org/a": "https://a", "org/b": "https://b"},
            [_change()],
            "org/api",
        )
        assert "2" in body
        assert "repos" in body

    def test_breaking_count_in_header(self):
        changes = [_change("/a"), _change("/b"), _change("/c")]
        body = _build_comment({"org/svc": "https://..."}, changes, "org/api")
        assert "3 breaking change" in body

    def test_singular_breaking_change(self):
        body = _build_comment({"org/svc": "https://..."}, [_change()], "org/api")
        assert "1 breaking change" in body
        assert "1 breaking changes" not in body

    def test_repos_sorted_in_table(self):
        urls = {"org/z": "https://z", "org/a": "https://a", "org/m": "https://m"}
        body = _build_comment(urls, [_change()], "org/api")
        lines = body.splitlines()
        table_rows = [l for l in lines if l.startswith("| [org/")]
        names = [r.split("[")[1].split("]")[0] for r in table_rows]
        assert names == sorted(names)


# ── _build_not_configured_comment() ──────────────────────────────────────────

class TestBuildNotConfiguredComment:
    def test_contains_marker(self):
        body = _build_not_configured_comment([_change()])
        assert _COMMENT_MARKER in body

    def test_contains_breaking_change(self):
        body = _build_not_configured_comment([_change("/users/{id}")])
        assert "/users/{id}" in body

    def test_contains_no_scan_notice(self):
        body = _build_not_configured_comment([_change()])
        assert "No consumer repos" in body or "no consumer" in body.lower()

    def test_contains_setup_yaml(self):
        body = _build_not_configured_comment([_change()])
        assert "consumer-repos" in body
        assert "```yaml" in body

    def test_breaking_count_singular(self):
        body = _build_not_configured_comment([_change()])
        assert "1 breaking change" in body
        assert "1 breaking changes" not in body

    def test_breaking_count_plural(self):
        body = _build_not_configured_comment([_change("/a"), _change("/b")])
        assert "2 breaking changes" in body

    def test_empty_breaking_list(self):
        body = _build_not_configured_comment([])
        assert _COMMENT_MARKER in body
        assert "0 breaking changes" in body


# ── _build_clear_comment() ───────────────────────────────────────────────────

class TestBuildClearComment:
    def test_contains_marker(self):
        assert _COMMENT_MARKER in _build_clear_comment()

    def test_no_breaking_changes_message(self):
        body = _build_clear_comment()
        assert "no breaking changes" in body.lower()

    def test_contains_checkmark(self):
        assert "✅" in _build_clear_comment()


# ── _find_existing_comment() ─────────────────────────────────────────────────

class TestFindExistingComment:
    def test_returns_id_when_marker_found(self):
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = [
            {"id": 123, "body": f"{_COMMENT_MARKER}\n## Report"},
            {"id": 124, "body": "some other comment"},
        ]
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp

        result = _find_existing_comment(client, "org/api", 42)
        assert result == 123

    def test_returns_none_when_no_marker(self):
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = [{"id": 1, "body": "unrelated comment"}]
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp

        assert _find_existing_comment(client, "org/api", 42) is None

    def test_returns_none_on_empty_comments(self):
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = []
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp

        assert _find_existing_comment(client, "org/api", 42) is None

    def test_returns_none_on_http_error(self):
        client = MagicMock()
        client.get.side_effect = httpx.HTTPError("timeout")
        assert _find_existing_comment(client, "org/api", 42) is None

    def test_returns_first_matching_comment(self):
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = [
            {"id": 10, "body": f"{_COMMENT_MARKER}\nfirst"},
            {"id": 20, "body": f"{_COMMENT_MARKER}\nsecond"},
        ]
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp

        assert _find_existing_comment(client, "org/api", 42) == 10


# ── _upsert_pr_comment() ─────────────────────────────────────────────────────

class TestUpsertPrComment:
    def test_posts_new_when_no_existing(self):
        client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp

        _upsert_pr_comment(client, "org/api", 42, "body", None)
        client.post.assert_called_once()
        client.patch.assert_not_called()

    def test_patches_existing_comment(self):
        client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.patch.return_value = resp

        _upsert_pr_comment(client, "org/api", 42, "body", 123)
        client.patch.assert_called_once()
        client.post.assert_not_called()

    def test_patch_url_contains_comment_id(self):
        client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.patch.return_value = resp

        _upsert_pr_comment(client, "org/api", 42, "body", 999)
        url = client.patch.call_args[0][0]
        assert "999" in url

    def test_handles_403(self, capsys):
        client = MagicMock()
        err_response = MagicMock()
        err_response.status_code = 403
        error = httpx.HTTPStatusError("403", request=MagicMock(), response=err_response)
        post_resp = MagicMock()
        post_resp.raise_for_status.side_effect = error
        client.post.return_value = post_resp

        _upsert_pr_comment(client, "org/api", 42, "body", None)
        assert "missing 'issues: write'" in capsys.readouterr().out

    def test_handles_http_error(self):
        client = MagicMock()
        client.post.side_effect = httpx.HTTPError("network error")
        # Should not raise
        _upsert_pr_comment(client, "org/api", 42, "body", None)


# ── pr_comment() ─────────────────────────────────────────────────────────────

class TestPrComment:
    def _state(self, **kwargs):
        defaults = dict(
            pr_number=42,
            provider_repo="org/api",
            github_token="tok",
            diff=DiffResult("b", "h", [_change()], {}),
        )
        return initial_state(**{**defaults, **kwargs})

    def test_returns_empty_when_no_pr_number(self):
        state = self._state(pr_number=0)
        assert pr_comment(state) == {}

    def test_returns_empty_when_no_provider_repo(self):
        state = self._state(provider_repo="")
        assert pr_comment(state) == {}

    def test_dry_run_with_issues_prints_comment(self, capsys):
        state = self._state(
            dry_run=True,
            issue_urls={"org/svc": "https://github.com/org/svc/issues/1"},
        )
        pr_comment(state)
        out = capsys.readouterr().out
        assert "DRY RUN" in out

    def test_dry_run_no_body_prints_info(self, capsys):
        # consumer_repos set, no issue_urls → body=None
        state = self._state(dry_run=True, consumer_repos=["org/svc"], issue_urls={})
        pr_comment(state)
        out = capsys.readouterr().out
        assert "DRY RUN" in out or "clear" in out.lower() or "no active" in out.lower()

    def test_no_token_skips(self, capsys):
        state = self._state(github_token="")
        pr_comment(state)
        assert "No GITHUB_TOKEN" in capsys.readouterr().out

    def test_no_token_env_fallback(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_TOKEN", "envtok")
        # Can't easily test full flow without httpx mock, but verify it doesn't hit no-token path
        with patch("drift_guard_agent.nodes.pr_comment.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            get_resp = MagicMock()
            get_resp.json.return_value = []
            get_resp.raise_for_status = MagicMock()
            mock_client.get.return_value = get_resp
            post_resp = MagicMock()
            post_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = post_resp
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            state = self._state(github_token="", issue_urls={"org/svc": "https://..."})
            pr_comment(state)
            assert "No GITHUB_TOKEN" not in capsys.readouterr().out

    @patch("drift_guard_agent.nodes.pr_comment.httpx.Client")
    def test_posts_new_comment(self, mock_cls):
        mock_client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = []
        get_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = get_resp
        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = post_resp
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        state = self._state(issue_urls={"org/svc": "https://github.com/org/svc/issues/1"})
        pr_comment(state)
        mock_client.post.assert_called_once()

    @patch("drift_guard_agent.nodes.pr_comment.httpx.Client")
    def test_updates_existing_comment(self, mock_cls):
        mock_client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = [{"id": 77, "body": f"{_COMMENT_MARKER}\nold"}]
        get_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = get_resp
        patch_resp = MagicMock()
        patch_resp.raise_for_status = MagicMock()
        mock_client.patch.return_value = patch_resp
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        state = self._state(issue_urls={"org/svc": "https://..."})
        pr_comment(state)
        mock_client.patch.assert_called_once()
        assert "77" in mock_client.patch.call_args[0][0]

    @patch("drift_guard_agent.nodes.pr_comment.httpx.Client")
    def test_no_consumer_repos_posts_not_configured_comment(self, mock_cls):
        mock_client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = []
        get_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = get_resp
        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = post_resp
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        state = self._state(consumer_repos=[], issue_urls={})
        pr_comment(state)
        mock_client.post.assert_called_once()
        body = mock_client.post.call_args[1]["json"]["body"]
        assert "consumer-repos" in body

    @patch("drift_guard_agent.nodes.pr_comment.httpx.Client")
    def test_existing_comment_updated_to_clear_when_no_issues(self, mock_cls):
        mock_client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = [{"id": 55, "body": f"{_COMMENT_MARKER}\nold report"}]
        get_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = get_resp
        patch_resp = MagicMock()
        patch_resp.raise_for_status = MagicMock()
        mock_client.patch.return_value = patch_resp
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        # consumer_repos set, issue_urls empty → body=None → should clear stale comment
        state = self._state(consumer_repos=["org/svc"], issue_urls={})
        pr_comment(state)
        mock_client.patch.assert_called_once()
        body = mock_client.patch.call_args[1]["json"]["body"]
        assert "no breaking changes" in body.lower() or "✅" in body

    @patch("drift_guard_agent.nodes.pr_comment.httpx.Client")
    def test_no_existing_comment_and_no_body_stays_silent(self, mock_cls):
        mock_client = MagicMock()
        get_resp = MagicMock()
        get_resp.json.return_value = []  # no existing comment
        get_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = get_resp
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        # consumer_repos set, no issue_urls → body=None, no existing comment → silent
        state = self._state(consumer_repos=["org/svc"], issue_urls={})
        pr_comment(state)
        mock_client.post.assert_not_called()
        mock_client.patch.assert_not_called()
