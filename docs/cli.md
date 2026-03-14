# Python CLI

Use this if you want to run the agent locally or integrate it into a non-GitHub CI system. You'll need a diff JSON file produced by `drift-guard-engine` first.

## Installation

```sh
pip install drift-guard-agent
```

## Usage

```sh
drift-guard-agent \
  --diff diff.json \
  --org my-org \
  --token $ORG_READ_TOKEN \
  --github-token $ORG_READ_TOKEN \
  --consumer-repos your-org/service-a,your-org/service-b \
  --pr 42
```

## Options

| Flag | Env var | Description |
|---|---|---|
| `--diff` | — | Path to drift-guard JSON diff file, or `-` to read from stdin |
| `--org` | `GITHUB_ORG` / `GITHUB_REPOSITORY_OWNER` | GitHub org owning the consumer repos |
| `--token` | `ORG_READ_TOKEN` | PAT with `repo` + `read:org` scopes for cloning consumer repos |
| `--github-token` | `GITHUB_TOKEN` | Token for posting PR comments and opening Issues |
| `--pr` | `PR_NUMBER` | Pull request number to link in consumer Issues |
| `--provider-repo` | `GITHUB_REPOSITORY` | Full name of the provider repo (e.g. `org/repo`) — excluded from scan |
| `--consumer-repos` | `CONSUMER_REPOS` | Comma-separated list of `owner/repo` to scan |
| `--model` | `DRIFT_GUARD_MODEL` | Anthropic model for risk analysis (default: `claude-opus-4-6`) |
| `--dry-run` | — | Print output without posting to GitHub |

## Generating a diff

Use `drift-guard-engine` to produce the JSON diff first:

```sh
# OpenAPI
drift-guard openapi --base openapi.base.yaml --head openapi.yaml --format json > diff.json

# GraphQL
drift-guard graphql --base schema.base.graphql --head schema.graphql --format json > diff.json

# gRPC
drift-guard grpc --base api.base.proto --head api.proto --format json > diff.json
```
