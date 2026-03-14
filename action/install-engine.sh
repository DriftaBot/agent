#!/usr/bin/env bash
# Download and install the latest driftabot binary.
# Requires GH_TOKEN env var (set by action.yml from github.token).
set -euo pipefail

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64\|arm64/arm64/')

gh release download \
  --repo DriftaBot/engine \
  --pattern "driftabot_${OS}_${ARCH}.tar.gz" \
  --dir /tmp \
  --clobber

tar xz -C /usr/local/bin driftabot < "/tmp/driftabot_${OS}_${ARCH}.tar.gz"
echo "[driftabot] installed: $(which driftabot)"
