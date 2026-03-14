# api-drift-agent

<a href="https://driftagent.github.io/api-drift-agent/guide" target="_blank"><img src="https://img.shields.io/badge/docs-api--drift--agent-6366f1?logo=gitbook&logoColor=white" alt="Documentation"></a>

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
```

## How it works

Powered by <a href="https://driftagent.github.io/api-drift-engine/" target="_blank">DriftAgent</a>.

1. Downloads the latest `drift-guard-engine` binary
2. Compares the OpenAPI schema between base and head branch
3. If breaking changes are found, searches the org for repos that reference those endpoints
4. Clones each consumer repo and scans for affected files
5. Opens (or updates) a GitHub Issue in each impacted consumer repo

