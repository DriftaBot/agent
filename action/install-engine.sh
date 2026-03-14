#!/usr/bin/env bash
# Download and install the latest drift-guard-engine binary.
# Requires GH_TOKEN env var (set by action.yml from github.token).
set -euo pipefail

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64\|arm64/arm64/')

gh release download \
  --repo DriftaBot/engine \
  --pattern "drift-guard_${OS}_${ARCH}.tar.gz" \
  --dir /tmp \
  --clobber

tar xz -C /usr/local/bin drift-guard < "/tmp/drift-guard_${OS}_${ARCH}.tar.gz"
echo "[drift-agent] drift-guard-engine installed: $(which drift-guard)"
