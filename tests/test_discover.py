"""Tests for drift_agent.nodes.discover."""

from __future__ import annotations

import pytest

from drift_agent.nodes.discover import discover_consumers
from drift_agent.state import ConsumerRepo, initial_state


class TestDiscoverConsumers:
    # ── empty / skip cases ───────────────────────────────────────────────────

    def test_no_consumer_repos_returns_empty(self):
        state = initial_state(token="tok", consumer_repos=[])
        assert discover_consumers(state) == {"consumers": []}

    def test_no_token_returns_empty(self, capsys):
        state = initial_state(token="", consumer_repos=["org/repo"])
        result = discover_consumers(state)
        assert result == {"consumers": []}
        assert "No token" in capsys.readouterr().out

    def test_no_token_no_env_var(self, monkeypatch, capsys):
        monkeypatch.delenv("ORG_READ_TOKEN", raising=False)
        state = initial_state(token="", consumer_repos=["org/repo"])
        result = discover_consumers(state)
        assert result["consumers"] == []

    def test_empty_strings_filtered(self):
        state = initial_state(token="tok", consumer_repos=["", "  ", "org/service"])
        result = discover_consumers(state)
        assert len(result["consumers"]) == 1
        assert result["consumers"][0].full_name == "org/service"

    # ── repo name validation ─────────────────────────────────────────────────

    def test_invalid_repo_no_slash_skipped(self, capsys):
        state = initial_state(token="tok", consumer_repos=["justname", "org/repo"])
        result = discover_consumers(state)
        out = capsys.readouterr().out
        assert "justname" in out
        assert len(result["consumers"]) == 1
        assert result["consumers"][0].full_name == "org/repo"

    def test_invalid_repo_double_slash_skipped(self, capsys):
        state = initial_state(token="tok", consumer_repos=["org//repo"])
        result = discover_consumers(state)
        assert result["consumers"] == []

    def test_invalid_repo_path_traversal_skipped(self, capsys):
        state = initial_state(token="tok", consumer_repos=["../evil/repo"])
        result = discover_consumers(state)
        assert result["consumers"] == []

    def test_valid_repo_with_hyphens_and_dots(self):
        state = initial_state(token="tok", consumer_repos=["my-org/my.repo"])
        result = discover_consumers(state)
        assert len(result["consumers"]) == 1
        assert result["consumers"][0].full_name == "my-org/my.repo"

    def test_valid_repo_with_underscores(self):
        state = initial_state(token="tok", consumer_repos=["my_org/my_repo_123"])
        result = discover_consumers(state)
        assert len(result["consumers"]) == 1

    def test_whitespace_stripped_from_repo_names(self):
        state = initial_state(token="tok", consumer_repos=["  org/service  "])
        result = discover_consumers(state)
        assert result["consumers"][0].full_name == "org/service"

    def test_all_invalid_returns_empty(self, capsys):
        state = initial_state(token="tok", consumer_repos=["bad", "also-bad", "still/bad/too"])
        result = discover_consumers(state)
        assert result["consumers"] == []

    # ── provider repo exclusion ──────────────────────────────────────────────

    def test_provider_repo_excluded(self):
        state = initial_state(
            token="tok",
            consumer_repos=["org/api", "org/service"],
            provider_repo="org/api",
        )
        result = discover_consumers(state)
        names = [c.full_name for c in result["consumers"]]
        assert "org/api" not in names
        assert "org/service" in names

    def test_provider_repo_not_in_list_does_not_affect_others(self):
        state = initial_state(
            token="tok",
            consumer_repos=["org/a", "org/b"],
            provider_repo="org/other",
        )
        result = discover_consumers(state)
        assert len(result["consumers"]) == 2

    # ── clone URL building ───────────────────────────────────────────────────

    def test_clone_url_includes_token(self):
        state = initial_state(token="mytoken", consumer_repos=["org/service"])
        result = discover_consumers(state)
        assert result["consumers"][0].clone_url == (
            "https://x-access-token:mytoken@github.com/org/service.git"
        )

    def test_clone_url_correct_format_for_multiple_repos(self):
        state = initial_state(token="tok", consumer_repos=["org/a", "org/b"])
        result = discover_consumers(state)
        urls = {c.full_name: c.clone_url for c in result["consumers"]}
        assert "org/a" in urls["org/a"]
        assert "org/b" in urls["org/b"]
        assert urls["org/a"] != urls["org/b"]

    # ── token fallback from env ──────────────────────────────────────────────

    def test_env_token_fallback(self, monkeypatch):
        monkeypatch.setenv("ORG_READ_TOKEN", "envtoken")
        state = initial_state(token="", consumer_repos=["org/service"])
        result = discover_consumers(state)
        assert len(result["consumers"]) == 1
        assert "envtoken" in result["consumers"][0].clone_url

    def test_state_token_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv("ORG_READ_TOKEN", "envtoken")
        state = initial_state(token="statetoken", consumer_repos=["org/service"])
        result = discover_consumers(state)
        assert "statetoken" in result["consumers"][0].clone_url
        assert "envtoken" not in result["consumers"][0].clone_url

    # ── multiple repos ───────────────────────────────────────────────────────

    def test_multiple_valid_repos(self):
        repos = ["org/a", "org/b", "org/c"]
        state = initial_state(token="tok", consumer_repos=repos)
        result = discover_consumers(state)
        assert len(result["consumers"]) == 3
        names = {c.full_name for c in result["consumers"]}
        assert names == set(repos)

    def test_consumer_repo_type(self):
        state = initial_state(token="tok", consumer_repos=["org/service"])
        result = discover_consumers(state)
        assert isinstance(result["consumers"][0], ConsumerRepo)
