"""Tests for drift_agent.nodes.scan."""

from __future__ import annotations

from pathlib import Path

import pytest

from drift_agent.nodes.scan import (
    _build_patterns,
    _scan_dir,
    _walk,
    scan_consumers,
)
from drift_agent.state import Change, ConsumerRepo, DiffResult, Hit, initial_state


def _change(path="/users/{id}", method="GET", severity="breaking", description="removed"):
    return Change(
        type="removed",
        severity=severity,
        path=path,
        method=method,
        location="",
        description=description,
    )


# ── _build_patterns() ────────────────────────────────────────────────────────

class TestBuildPatterns:
    def test_strips_single_path_param(self):
        patterns = _build_patterns([_change("/users/{id}")])
        assert len(patterns) == 1
        _, stable, _ = patterns[0]
        assert stable == "/users"

    def test_strips_multiple_path_params(self):
        patterns = _build_patterns([_change("/orgs/{org}/repos/{repo}")])
        _, stable, _ = patterns[0]
        assert stable == "/orgs/repos"

    def test_no_params_kept_as_is(self):
        patterns = _build_patterns([_change("/users")])
        _, stable, _ = patterns[0]
        assert stable == "/users"

    def test_skips_empty_path(self):
        patterns = _build_patterns([_change("")])
        assert patterns == []

    def test_skips_root_only_path(self):
        # path "/" has no non-param parts after splitting → skipped
        patterns = _build_patterns([_change("/{id}")])
        assert patterns == []

    def test_case_insensitive_match(self):
        patterns = _build_patterns([_change("/Users")])
        pattern, _, _ = patterns[0]
        assert pattern.search("/users/123") is not None

    def test_multiple_changes_produce_multiple_patterns(self):
        changes = [_change("/users/{id}"), _change("/orders/{id}")]
        patterns = _build_patterns(changes)
        assert len(patterns) == 2

    def test_change_attached_to_pattern(self):
        c = _change("/items/{id}")
        patterns = _build_patterns([c])
        _, _, attached = patterns[0]
        assert attached is c

    def test_nested_path_without_params(self):
        patterns = _build_patterns([_change("/api/v1/users")])
        _, stable, _ = patterns[0]
        assert stable == "/api/v1/users"

    def test_nested_path_with_params(self):
        patterns = _build_patterns([_change("/api/v1/users/{id}/posts/{postId}")])
        _, stable, _ = patterns[0]
        assert stable == "/api/v1/users/posts"


# ── _walk() ─────────────────────────────────────────────────────────────────

class TestWalk:
    def test_yields_py_and_ts_files(self, tmp_path):
        (tmp_path / "app.py").write_text("code")
        (tmp_path / "client.ts").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert "app.py" in names
        assert "client.ts" in names

    def test_skips_unsupported_extension(self, tmp_path):
        (tmp_path / "binary.exe").write_bytes(b"\x00")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        names = {f.name for f in _walk(tmp_path)}
        assert "binary.exe" not in names
        assert "image.png" not in names

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "lib"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("code")
        (tmp_path / "app.js").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert "index.js" not in names
        assert "app.js" in names

    def test_skips_git(self, tmp_path):
        git = tmp_path / ".git" / "objects"
        git.mkdir(parents=True)
        (git / "config.py").write_text("code")
        (tmp_path / "app.py").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert "config.py" not in names
        assert "app.py" in names

    def test_skips_pycache(self, tmp_path):
        pc = tmp_path / "__pycache__"
        pc.mkdir()
        (pc / "mod.py").write_text("code")
        (tmp_path / "app.py").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert names == {"app.py"}

    def test_skips_venv(self, tmp_path):
        ve = tmp_path / ".venv" / "lib" / "python3.11"
        ve.mkdir(parents=True)
        (ve / "site.py").write_text("code")
        (tmp_path / "main.py").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert "site.py" not in names

    def test_skips_vendor(self, tmp_path):
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "third_party.go").write_text("code")
        (tmp_path / "main.go").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert "third_party.go" not in names

    def test_skips_dist_and_build(self, tmp_path):
        for d in ("dist", "build"):
            p = tmp_path / d
            p.mkdir()
            (p / "bundle.js").write_text("code")
        (tmp_path / "src.js").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert "bundle.js" not in names
        assert "src.js" in names

    def test_scans_yaml_and_json(self, tmp_path):
        (tmp_path / "config.yaml").write_text("key: value")
        (tmp_path / "data.json").write_text("{}")
        names = {f.name for f in _walk(tmp_path)}
        assert "config.yaml" in names
        assert "data.json" in names

    def test_empty_directory(self, tmp_path):
        assert list(_walk(tmp_path)) == []

    def test_nested_directories(self, tmp_path):
        sub = tmp_path / "src" / "api"
        sub.mkdir(parents=True)
        (sub / "client.py").write_text("code")
        names = {f.name for f in _walk(tmp_path)}
        assert "client.py" in names


# ── _scan_dir() ──────────────────────────────────────────────────────────────

class TestScanDir:
    def test_finds_matching_line(self, tmp_path):
        (tmp_path / "client.py").write_text('url = "/users/123"\n')
        changes = [_change("/users/{id}")]
        patterns = _build_patterns(changes)
        hits = _scan_dir(tmp_path, patterns, changes)
        assert len(hits) == 1
        assert hits[0].file == "client.py"
        assert hits[0].line_num == 1
        assert "/users" in hits[0].line

    def test_no_match_returns_empty(self, tmp_path):
        (tmp_path / "client.py").write_text('url = "/orders/123"\n')
        changes = [_change("/users/{id}")]
        patterns = _build_patterns(changes)
        hits = _scan_dir(tmp_path, patterns, changes)
        assert hits == []

    def test_only_one_hit_per_line(self, tmp_path):
        # Two patterns both matching same line → only one Hit produced
        (tmp_path / "f.py").write_text("fetch('/users/items')\n")
        changes = [_change("/users"), _change("/items")]
        patterns = _build_patterns(changes)
        hits = _scan_dir(tmp_path, patterns, changes)
        assert len(hits) == 1

    def test_hit_per_matching_line(self, tmp_path):
        content = "/users/1\n/users/2\n/orders/3\n"
        (tmp_path / "routes.py").write_text(content)
        changes = [_change("/users/{id}")]
        patterns = _build_patterns(changes)
        hits = _scan_dir(tmp_path, patterns, changes)
        assert len(hits) == 2

    def test_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("/users/1\n")
        (tmp_path / "b.ts").write_text("/users/2\n")
        changes = [_change("/users/{id}")]
        patterns = _build_patterns(changes)
        hits = _scan_dir(tmp_path, patterns, changes)
        assert len(hits) == 2

    def test_hit_contains_change_path(self, tmp_path):
        (tmp_path / "f.py").write_text("/users/42\n")
        c = _change("/users/{id}", method="GET")
        patterns = _build_patterns([c])
        hits = _scan_dir(tmp_path, patterns, [c])
        assert hits[0].change_path == "GET /users/{id}"

    def test_relative_path_in_hit(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "api.py").write_text("/users/1\n")
        changes = [_change("/users/{id}")]
        patterns = _build_patterns(changes)
        hits = _scan_dir(tmp_path, patterns, changes)
        assert hits[0].file == "src/api.py"

    def test_unreadable_file_skipped(self, tmp_path):
        # Write a file then make it unreadable
        f = tmp_path / "secret.py"
        f.write_text("/users/1\n")
        f.chmod(0o000)
        changes = [_change("/users/{id}")]
        patterns = _build_patterns(changes)
        try:
            hits = _scan_dir(tmp_path, patterns, changes)
            # Should not raise; file may be skipped due to permission error
        finally:
            f.chmod(0o644)


# ── scan_consumers() ─────────────────────────────────────────────────────────

class TestScanConsumers:
    def test_no_consumers_returns_empty(self):
        state = initial_state()
        assert scan_consumers(state) == {"hits": {}}

    def test_no_diff_returns_empty(self):
        consumer = ConsumerRepo("org/a", "url", local_path="/tmp")
        state = initial_state(diff=None, consumers=[consumer])
        assert scan_consumers(state) == {"hits": {}}

    def test_no_breaking_changes_returns_empty(self, tmp_path):
        diff = DiffResult("b", "h", [_change(severity="non-breaking")], {})
        consumer = ConsumerRepo("org/a", "url", local_path=str(tmp_path))
        state = initial_state(diff=diff, consumers=[consumer])
        assert scan_consumers(state) == {"hits": {}}

    def test_finds_hits_in_consumer(self, tmp_path):
        (tmp_path / "api.py").write_text("/users/123\n")
        diff = DiffResult("b", "h", [_change("/users/{id}")], {})
        consumer = ConsumerRepo("org/service", "url", local_path=str(tmp_path))
        state = initial_state(diff=diff, consumers=[consumer])
        result = scan_consumers(state)
        assert "org/service" in result["hits"]
        assert len(result["hits"]["org/service"]) == 1

    def test_no_hits_in_consumer_not_in_result(self, tmp_path):
        (tmp_path / "api.py").write_text("/orders/123\n")
        diff = DiffResult("b", "h", [_change("/users/{id}")], {})
        consumer = ConsumerRepo("org/service", "url", local_path=str(tmp_path))
        state = initial_state(diff=diff, consumers=[consumer])
        result = scan_consumers(state)
        assert result["hits"] == {}

    def test_consumer_without_local_path_skipped(self):
        diff = DiffResult("b", "h", [_change("/users/{id}")], {})
        consumer = ConsumerRepo("org/service", "url", local_path="")
        state = initial_state(diff=diff, consumers=[consumer])
        result = scan_consumers(state)
        assert result["hits"] == {}

    def test_multiple_consumers_partial_hits(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "api.py").write_text("/users/1\n")
        (dir_b / "api.py").write_text("/orders/1\n")

        diff = DiffResult("b", "h", [_change("/users/{id}")], {})
        consumers = [
            ConsumerRepo("org/a", "url", local_path=str(dir_a)),
            ConsumerRepo("org/b", "url", local_path=str(dir_b)),
        ]
        state = initial_state(diff=diff, consumers=consumers)
        result = scan_consumers(state)
        assert "org/a" in result["hits"]
        assert "org/b" not in result["hits"]

    def test_scan_dir_subdir_used_when_exists(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "api.py").write_text("/users/1\n")
        diff = DiffResult("b", "h", [_change("/users/{id}")], {})
        consumer = ConsumerRepo("org/a", "url", local_path=str(tmp_path), scan_dir="src")
        state = initial_state(diff=diff, consumers=[consumer])
        result = scan_consumers(state)
        assert "org/a" in result["hits"]

    def test_hits_are_hit_instances(self, tmp_path):
        (tmp_path / "f.py").write_text("/users/1\n")
        diff = DiffResult("b", "h", [_change("/users/{id}")], {})
        consumer = ConsumerRepo("org/a", "url", local_path=str(tmp_path))
        state = initial_state(diff=diff, consumers=[consumer])
        result = scan_consumers(state)
        assert isinstance(result["hits"]["org/a"][0], Hit)
