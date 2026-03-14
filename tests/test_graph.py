"""Tests for drift_agent.graph routing functions."""

from __future__ import annotations

import pytest
from langgraph.graph import END

from drift_agent.graph import (
    _route_after_discover,
    _route_after_ingest,
    _route_after_scan,
)
from drift_agent.state import Change, ConsumerRepo, DiffResult, Hit, initial_state


def _breaking():
    return Change(type="removed", severity="breaking", path="/u", method="GET",
                  location="", description="gone")


def _non_breaking():
    return Change(type="added", severity="non-breaking", path="/v", method="GET",
                  location="", description="added")


# ── _route_after_ingest() ────────────────────────────────────────────────────

class TestRouteAfterIngest:
    def test_no_diff_returns_end(self):
        state = initial_state(diff=None)
        assert _route_after_ingest(state) == END

    def test_empty_changes_returns_end(self):
        diff = DiffResult("b", "h", [], {})
        state = initial_state(diff=diff)
        assert _route_after_ingest(state) == END

    def test_only_non_breaking_returns_end(self, capsys):
        diff = DiffResult("b", "h", [_non_breaking()], {})
        state = initial_state(diff=diff)
        assert _route_after_ingest(state) == END
        assert "No breaking changes" in capsys.readouterr().out

    def test_only_info_changes_returns_end(self):
        c = Change(type="info", severity="info", path="/x", method="GET",
                   location="", description="note")
        diff = DiffResult("b", "h", [c], {})
        state = initial_state(diff=diff)
        assert _route_after_ingest(state) == END

    def test_one_breaking_change_routes_to_discover(self):
        diff = DiffResult("b", "h", [_breaking()], {})
        state = initial_state(diff=diff)
        assert _route_after_ingest(state) == "discover_consumers"

    def test_mixed_changes_routes_to_discover_when_any_breaking(self):
        diff = DiffResult("b", "h", [_non_breaking(), _breaking()], {})
        state = initial_state(diff=diff)
        assert _route_after_ingest(state) == "discover_consumers"

    def test_multiple_breaking_changes_routes_to_discover(self):
        diff = DiffResult("b", "h", [_breaking(), _breaking()], {})
        state = initial_state(diff=diff)
        assert _route_after_ingest(state) == "discover_consumers"


# ── _route_after_discover() ──────────────────────────────────────────────────

class TestRouteAfterDiscover:
    def test_no_consumers_returns_end(self, capsys):
        state = initial_state(consumers=[])
        assert _route_after_discover(state) == END
        assert "No consumers" in capsys.readouterr().out

    def test_one_consumer_routes_to_fetch(self):
        state = initial_state(consumers=[ConsumerRepo("org/a", "url")])
        assert _route_after_discover(state) == "fetch_consumers"

    def test_multiple_consumers_routes_to_fetch(self):
        state = initial_state(consumers=[
            ConsumerRepo("org/a", "url"),
            ConsumerRepo("org/b", "url"),
        ])
        assert _route_after_discover(state) == "fetch_consumers"


# ── _route_after_scan() ──────────────────────────────────────────────────────

class TestRouteAfterScan:
    def test_empty_hits_returns_end(self, capsys):
        state = initial_state(hits={})
        assert _route_after_scan(state) == END
        assert "No consumer hits" in capsys.readouterr().out

    def test_none_hits_returns_end(self):
        # hits not set at all → state.get("hits") returns {} from initial_state
        state = initial_state()
        assert _route_after_scan(state) == END

    def test_hits_without_api_key_routes_to_notify(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        state = initial_state(hits={"org/a": [Hit("f", 1, "l", "t", "p")]})
        assert _route_after_scan(state) == "notify"

    def test_hits_with_api_key_routes_to_explain(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        state = initial_state(hits={"org/a": [Hit("f", 1, "l", "t", "p")]})
        assert _route_after_scan(state) == "explain"

    def test_multiple_repos_with_hits_routes_to_notify(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        state = initial_state(hits={
            "org/a": [Hit("f1", 1, "l", "t", "p")],
            "org/b": [Hit("f2", 2, "l", "t", "p")],
        })
        assert _route_after_scan(state) == "notify"
