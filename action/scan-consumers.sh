#!/usr/bin/env bash
# Search for consumer repos affected by breaking changes and open GitHub Issues.
# Env vars: GITHUB_TOKEN, ORG_READ_TOKEN, ANTHROPIC_API_KEY, GITHUB_REPOSITORY_OWNER, GITHUB_REPOSITORY, PR_NUMBER
set -euo pipefail

# Prefer ORG_READ_TOKEN for issue creation — it has org-wide write access.
# GITHUB_TOKEN is scoped to the provider repo only and cannot open issues in consumer repos.
ISSUE_TOKEN="${ORG_READ_TOKEN:-$GITHUB_TOKEN}"

if [ "$ISSUE_TOKEN" = "$GITHUB_TOKEN" ]; then
  echo "::warning::drift-guard-agent: no org-read-token provided — using GITHUB_TOKEN which cannot open issues in consumer repos. Set org-read-token to a PAT with 'repo' (or 'public_repo') + 'read:org' scopes."
fi

EXTRA_ARGS=""
if [ -n "${CONSUMER_REPOS:-}" ]; then
  EXTRA_ARGS="--consumer-repos $CONSUMER_REPOS"
fi

drift-guard-agent \
  --diff /tmp/drift-diff.json \
  --org "$GITHUB_REPOSITORY_OWNER" \
  --token "$ORG_READ_TOKEN" \
  --github-token "$ISSUE_TOKEN" \
  --provider-repo "$GITHUB_REPOSITORY" \
  --pr "$PR_NUMBER" \
  $EXTRA_ARGS
