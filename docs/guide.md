# Guide

`api-drift-agent` is a LangGraph-powered agentic workflow that detects breaking API changes in provider PRs, scans a configured list of consumer repos, and automatically opens GitHub Issues in any that are affected.

## How it works

```
Provider PR opened
       │
       ▼
┌─────────────────────────────────────┐
│  Download drift-guard-engine binary │
│  Auto-detect schema type & compare  │
│  (OpenAPI, GraphQL, or gRPC/proto)  │
└─────────────────────────────────────┘
       │ breaking changes found
       ▼
┌─────────────────────────────────────┐
│  Scan consumer repos from           │
│  consumer-repos input               │
│  (no consumer-repos → post comment  │
│   with setup instructions & skip)   │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Clone each consumer repo           │
│  Scan for affected files            │
│  Open (or update) a GitHub Issue    │
│  Post DriftAgent Report on PR       │
└─────────────────────────────────────┘
       │ PR re-run / changes fixed
       ▼
┌─────────────────────────────────────┐
│  Close resolved consumer issues     │
│  Update PR comment → all clear ✅   │
└─────────────────────────────────────┘
```

## Prerequisites

- Create a GitHub Personal Access Token (PAT) with `repo` and `read:org` scopes. This is required to clone and open issues in consumer repos. Add it as a repository secret named `ORG_READ_TOKEN` (**Settings → Secrets and variables → Actions → New repository secret**).
- Optionally, add an `ANTHROPIC_API_KEY` secret to enable Claude-powered risk analysis in the issues the agent opens.

## Usage

Add to your **provider** repo's workflow:

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
          consumer-repos: |
            your-org/service-a
            your-org/service-b
          # anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}  # optional: enables AI risk analysis
```

## Inputs

| Input | Required | Description |
|---|---|---|
| `base-schema` | No | Path to schema file (auto-detected if omitted). Supports OpenAPI (`.yaml`/`.yml`/`.json`), GraphQL (`.graphql`/`.gql`), and Protobuf (`.proto`). |
| `head-schema` | No | Path on PR branch (defaults to `base-schema`) |
| `org-read-token` | No | PAT with `repo` + `read:org` scopes. Required to clone consumer repos and open issues in them. Falls back to `GITHUB_TOKEN` (cannot open issues in other repos). |
| `consumer-repos` | No | Newline or comma-separated list of consumer repos to scan (e.g. `org/repo`). When omitted, no scan is conducted and the PR comment will include setup instructions. |
| `anthropic-api-key` | No | Enables Claude risk analysis in opened issues |

## Re-run behaviour

The agent is fully idempotent across CI rebuilds:

| Scenario | PR comment | Consumer issues |
|---|---|---|
| Re-run, same breaking changes | Updated in-place | Updated in-place — no duplicates |
| Re-run, more breaking changes | Updated in-place | Updated in-place |
| PR fixed — breaking changes gone | Updated → ✅ all clear | Closed with "Breaking changes resolved" |
| Breaking changes found, no `consumer-repos` configured | Posted with breaking changes table + setup instructions | Nothing touched |
| Clean PR, no previous activity | Nothing posted | Nothing touched |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Action fails: "No API schema found" | Schema file not at a standard path, or generated at runtime and not committed | Set the `base-schema` input explicitly |
| Action fails: "drift-guard-engine failed to diff schemas" | Schema file is invalid or malformed | Validate locally: `drift-guard openapi --base ... --head ...` (or `graphql`/`grpc`) |
| Issues created but no AI explanations | `ANTHROPIC_API_KEY` not set | Set the secret in your repo — the agent runs without it but skips Claude risk analysis |
| No issues created in consumer repos | `org-read-token` not set, or PAT has insufficient scope | Set `org-read-token` to a PAT with `repo` + `read:org` scopes |
| PR comment shows "no consumer scan conducted" | `consumer-repos` input not set | Add the `consumer-repos` input listing repos to scan |
