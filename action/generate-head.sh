#!/usr/bin/env bash
# Generate the head (PR branch) API schema.
# Env vars: TYPE, OVERRIDE_HEAD, OVERRIDE_BASE
set -euo pipefail

if [ -n "${OVERRIDE_HEAD:-}" ]; then
  mkdir -p /tmp/specs
  cp "$OVERRIDE_HEAD" /tmp/specs/head.yml
  echo "[drift-agent] head schema: override $OVERRIDE_HEAD"
elif [ -n "${OVERRIDE_BASE:-}" ]; then
  mkdir -p /tmp/specs
  cp "$OVERRIDE_BASE" /tmp/specs/head.yml
  echo "[drift-agent] head schema: override $OVERRIDE_BASE"
else
  case "$TYPE" in
    nestjs|fastapi|go|graphql|grpc|openapi)
      bash /tmp/scripts/generate/${TYPE}.sh /tmp/specs/head.yml ;;
    *)
      echo "::error::Unknown project type: $TYPE"; exit 1 ;;
  esac
fi
