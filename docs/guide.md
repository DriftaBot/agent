# Guide

`@driftabot/agent` detects breaking API changes in provider PRs, scans a configured list of consumer repos, and automatically opens GitHub Issues in any that are affected — zero setup required on the consumer side.

## Quick start

### Step 1 — Create a GitHub PAT

Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens** and create a token with:
- **Repository access:** All repositories (or select your provider + consumer repos)
- **Permissions:** `Contents: Read`, `Issues: Read and write`

### Step 2 — Add secrets to your provider repo

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `ORG_READ_TOKEN` | The PAT from Step 1 |
| `ANTHROPIC_API_KEY` | _(optional)_ Enables Claude risk analysis in opened issues |

### Step 3 — Add the workflow file

Create `.github/workflows/api-drift-check.yml` in your provider repo:

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

      - uses: DriftaBot/agent@v1
        with:
          org-read-token: ${{ secrets.ORG_READ_TOKEN }}
          consumer-repos: |
            your-org/service-a
            your-org/service-b
          # anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

Replace `your-org/service-a` etc. with the repos that consume your API.

### Step 4 — Open a PR with a breaking change

Open a pull request that removes or renames an API endpoint. Within about a minute you'll see:

**A comment posted on your PR:**

> ⚠️ **API Drift Agent Report — 1 breaking change detected**
>
> **Breaking changes**
>
> | Path | Description |
> | ---- | ----------- |
> | `/users/{id}` | endpoint removed |
>
> **Affected consumer repos**
>
> Issues have been opened in **1** affected consumer repo:
>
> | Issue |
> | ----- |
> | your-org/service-a #42 |
>
> _Update consumer repos before merging this PR._

**A GitHub Issue opened in each affected consumer repo**, listing the exact files and line numbers where the breakage will occur at runtime.

### Step 5 — Fix and re-run

Once breaking changes are resolved, re-run the action. It will:
- Close open issues in consumer repos with a "Breaking changes resolved" comment
- Update the PR comment to ✅ **no breaking changes detected**

## How it works

```
Provider PR opened
       │
       ▼
┌─────────────────────────────────────┐
│  Download api-drift-engine binary   │
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
│  Post Drift Agent Report on PR      │
└─────────────────────────────────────┘
       │ PR re-run / changes fixed
       ▼
┌─────────────────────────────────────┐
│  Close resolved consumer issues     │
│  Update PR comment → all clear ✅   │
└─────────────────────────────────────┘
```

## Inputs

| Input | Required | Description |
|---|---|---|
| `org-read-token` | No | PAT with `repo` + `read:org` scopes. Required to clone consumer repos and open issues in them. Falls back to `GITHUB_TOKEN` (which cannot open issues in other repos). |
| `consumer-repos` | No | Newline or comma-separated list of `owner/repo` to scan. When omitted, the PR comment includes setup instructions and no scan is run. |
| `base-schema` | No | Path to schema file. Auto-detected if omitted — supports OpenAPI (`.yaml`/`.yml`/`.json`), GraphQL (`.graphql`/`.gql`), and Protobuf (`.proto`). |
| `head-schema` | No | Path on the PR branch. Defaults to `base-schema`. |
| `anthropic-api-key` | No | Enables Claude risk analysis in opened issues. |

## Re-run behaviour

The agent is fully idempotent — safe to re-run at any time:

| Scenario | PR comment | Consumer issues |
|---|---|---|
| Re-run, same breaking changes | Updated in-place | Updated in-place — no duplicates |
| Re-run, more breaking changes | Updated in-place | Updated in-place |
| PR fixed — breaking changes gone | Updated → ✅ all clear | Closed with "Breaking changes resolved" |
| Breaking changes found, no `consumer-repos` configured | Posted with breaking changes + setup instructions | Nothing touched |
| Clean PR, no previous activity | Nothing posted | Nothing touched |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Action fails: "No API schema found" | Schema not at a standard path, or generated at runtime | Set `base-schema` explicitly |
| Action fails: schema diff error | Schema file is invalid or malformed | Validate locally: `drift-guard openapi --base ... --head ...` (or `graphql`/`grpc`) |
| Issues created but no AI explanations | `ANTHROPIC_API_KEY` not set | Add the secret — the agent works without it but skips risk analysis |
| No issues created in consumer repos | `org-read-token` missing or insufficient scope | Set a PAT with `repo` + `read:org` scopes |
| PR comment: "no consumer scan conducted" | `consumer-repos` not set | Add the `consumer-repos` input |
