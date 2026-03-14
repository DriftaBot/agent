# DriftaBot Agent

<a href="https://driftabot.github.io/agent/guide" target="_blank"><img src="https://img.shields.io/badge/docs-DriftaBot+Agent-6366f1?logo=gitbook&logoColor=white" alt="Documentation"></a>

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

      - uses: DriftaBot/agent@v2
        with:
          org-read-token: ${{ secrets.ORG_READ_TOKEN }}
          consumer-repos: |
            your-org/service-a
            your-org/service-b
```

## How it works

Powered by <a href="https://driftabot.github.io/engine/" target="_blank">DriftaBot</a>.

1. Downloads the latest `api-drift-engine` binary
2. Compares the OpenAPI schema between base and head branch
3. If breaking changes are found, searches the org for repos that reference those endpoints
4. Clones each consumer repo and scans for affected files
5. Opens (or updates) a GitHub Issue in each impacted consumer repo

