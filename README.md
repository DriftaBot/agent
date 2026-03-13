# api-drift-agent

[![View on GitHub Marketplace](https://img.shields.io/badge/GitHub%20Marketplace-api--drift--agent-blue?logo=github)](https://github.com/marketplace/actions/api-drift-agent)

LangGraph-powered agent that detects breaking API changes in provider PRs and automatically opens GitHub Issues in affected consumer repos — zero config on consumer side.

## Usage

Add to your provider repo's workflow:

```yaml
name: API Drift Check
on:
  pull_request:

permissions:
  contents: read
  issues: write

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: DriftAgent/api-drift-agent@v1
        with:
          org-read-token: ${{ secrets.ORG_READ_TOKEN }}
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}  # optional
```

## How it works

Powered by [drift-guard-engine](https://pgomes13.github.io/drift-guard-engine/).

1. Downloads the latest `drift-guard-engine` binary
2. Compares the OpenAPI schema between base and head branch
3. If breaking changes are found, searches the org for repos that reference those endpoints
4. Clones each consumer repo and scans for affected files
5. Opens (or updates) a GitHub Issue in each impacted consumer repo

## Inputs

| Input | Required | Description |
|---|---|---|
| `base-schema` | No | Path to OpenAPI schema (auto-detected if omitted) |
| `head-schema` | No | Path on PR branch (defaults to `base-schema`) |
| `org-read-token` | No | PAT with `repo:read` + `read:org` for private repos |
| `anthropic-api-key` | No | Enables LLM-powered impact explanations in Issues |

## Python CLI

```sh
pip install drift-guard-agent

drift-guard-agent \
  --diff diff.json \
  --org my-org \
  --token $ORG_READ_TOKEN \
  --github-token $GITHUB_TOKEN \
  --pr 42
```
