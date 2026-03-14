"""Shared fixtures for drift-guard-agent tests."""

from __future__ import annotations

import pytest

from drift_guard_agent.state import Change, ConsumerRepo, DiffResult, Hit, initial_state


@pytest.fixture
def breaking_change():
    return Change(
        type="removed",
        severity="breaking",
        path="/users/{id}",
        method="GET",
        location="",
        description="endpoint removed",
    )


@pytest.fixture
def non_breaking_change():
    return Change(
        type="added",
        severity="non-breaking",
        path="/users",
        method="GET",
        location="",
        description="new field added",
    )


@pytest.fixture
def diff_result(breaking_change):
    return DiffResult(
        base_file="base.yaml",
        head_file="head.yaml",
        changes=[breaking_change],
        summary={"total": 1, "breaking": 1},
    )


@pytest.fixture
def consumer_repo(tmp_path):
    return ConsumerRepo(
        full_name="org/service-a",
        clone_url="https://x-access-token:tok@github.com/org/service-a.git",
        local_path=str(tmp_path),
    )


@pytest.fixture
def sample_hit():
    return Hit(
        file="src/api.py",
        line_num=10,
        line='    url = "/users/123"',
        change_type="removed",
        change_path="GET /users/{id}",
    )


@pytest.fixture
def base_state():
    return initial_state(
        pr_number=42,
        provider_repo="org/api",
        github_token="gh-token",
    )
