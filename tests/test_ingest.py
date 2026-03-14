"""Tests for drift_guard_agent.nodes.ingest."""

from __future__ import annotations

import json

import pytest

from drift_guard_agent.nodes.ingest import ingest, parse_diff_json
from drift_guard_agent.state import Change, DiffResult, initial_state


# ── ingest() ────────────────────────────────────────────────────────────────

class TestIngest:
    def test_noop_when_diff_is_already_diffresult(self):
        diff = DiffResult(base_file="b", head_file="h", changes=[], summary={})
        state = initial_state(diff=diff)
        assert ingest(state) == {}

    def test_parses_dict_to_diffresult(self):
        raw = {
            "base_file": "base.yaml",
            "head_file": "head.yaml",
            "changes": [
                {
                    "type": "removed",
                    "severity": "breaking",
                    "path": "/users",
                    "method": "GET",
                    "location": "paths./users.get",
                    "description": "endpoint removed",
                }
            ],
            "summary": {"total": 1, "breaking": 1},
        }
        state = initial_state(diff=raw)
        result = ingest(state)

        diff = result["diff"]
        assert isinstance(diff, DiffResult)
        assert diff.base_file == "base.yaml"
        assert diff.head_file == "head.yaml"
        assert diff.summary == {"total": 1, "breaking": 1}
        assert len(diff.changes) == 1
        c = diff.changes[0]
        assert isinstance(c, Change)
        assert c.type == "removed"
        assert c.severity == "breaking"
        assert c.path == "/users"
        assert c.method == "GET"
        assert c.description == "endpoint removed"

    def test_empty_changes_list(self):
        raw = {"base_file": "b", "head_file": "h", "changes": [], "summary": {}}
        state = initial_state(diff=raw)
        result = ingest(state)
        assert result["diff"].changes == []

    def test_change_defaults_applied(self):
        raw = {"changes": [{}]}
        state = initial_state(diff=raw)
        result = ingest(state)
        c = result["diff"].changes[0]
        assert c.severity == "info"
        assert c.path == ""
        assert c.method == ""
        assert c.before == ""
        assert c.after == ""

    def test_raises_on_unexpected_type(self):
        state = initial_state(diff="not a valid type")
        with pytest.raises(ValueError, match="Unexpected diff type"):
            ingest(state)

    def test_raises_on_integer(self):
        state = initial_state(diff=42)
        with pytest.raises(ValueError):
            ingest(state)

    def test_multiple_changes(self):
        raw = {
            "changes": [
                {"type": "removed", "severity": "breaking", "path": "/a", "method": "DELETE",
                 "location": "", "description": "removed"},
                {"type": "modified", "severity": "breaking", "path": "/b", "method": "POST",
                 "location": "", "description": "schema changed"},
                {"type": "added", "severity": "non-breaking", "path": "/c", "method": "GET",
                 "location": "", "description": "new endpoint"},
            ]
        }
        state = initial_state(diff=raw)
        result = ingest(state)
        assert len(result["diff"].changes) == 3
        assert result["diff"].changes[0].severity == "breaking"
        assert result["diff"].changes[2].severity == "non-breaking"


# ── parse_diff_json() ────────────────────────────────────────────────────────

class TestParseDiffJson:
    def test_parses_valid_json(self):
        payload = {
            "base_file": "base.yaml",
            "head_file": "head.yaml",
            "changes": [
                {
                    "type": "removed",
                    "severity": "breaking",
                    "path": "/items/{id}",
                    "method": "DELETE",
                    "location": "",
                    "description": "endpoint removed",
                }
            ],
            "summary": {"breaking": 1},
        }
        diff = parse_diff_json(json.dumps(payload))
        assert isinstance(diff, DiffResult)
        assert diff.base_file == "base.yaml"
        assert diff.changes[0].path == "/items/{id}"
        assert diff.summary == {"breaking": 1}

    def test_defaults_for_missing_fields(self):
        diff = parse_diff_json(json.dumps({"changes": [{}]}))
        c = diff.changes[0]
        assert c.severity == "info"
        assert c.path == ""
        assert c.before == ""
        assert c.after == ""

    def test_empty_changes(self):
        diff = parse_diff_json(json.dumps({"changes": []}))
        assert diff.changes == []

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            parse_diff_json("not json")

    def test_before_after_fields(self):
        payload = {
            "changes": [
                {
                    "type": "modified",
                    "severity": "breaking",
                    "path": "/users",
                    "method": "GET",
                    "location": "",
                    "description": "type changed",
                    "before": "integer",
                    "after": "string",
                }
            ]
        }
        diff = parse_diff_json(json.dumps(payload))
        assert diff.changes[0].before == "integer"
        assert diff.changes[0].after == "string"
