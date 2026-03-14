#!/usr/bin/env bash
# Generate the BASE branch schema into $3.
# Usage: generate-base.sh <type> <base_ref> <output_path>
#
# For schema-first types (openapi/graphql/grpc): uses git show (fast, no build).
# For code-first types (nestjs/fastapi/go): creates a git worktree of base branch,
#   installs deps and generates the schema there, then removes the worktree.
set -euo pipefail

TYPE="${1:?Usage: generate-base.sh <type> <base_ref> <output_path>}"
BASE_REF="${2:?Missing base_ref}"
OUTPUT="${3:?Missing output_path}"
SCRIPTS_DIR="$(dirname "$0")"

mkdir -p "$(dirname "$OUTPUT")"

# ── Schema-first: just extract the file from git ────────────────────────────
if [ "$TYPE" = "openapi" ] || [ "$TYPE" = "graphql" ] || [ "$TYPE" = "grpc" ]; then

  # Find which file to extract (same logic as the generate script, applied to HEAD)
  case "$TYPE" in
    openapi)
      FILE_PATH=$(find . -maxdepth 4 \( \
        -name "openapi.yaml" -o -name "openapi.yml" -o -name "openapi.json" \
        -o -name "api.yaml" -o -name "api.yml" -o -name "api.json" \
        -o -name "swagger.yaml" -o -name "swagger.yml" -o -name "swagger.json" \) \
        ! -path "*/node_modules/*" ! -path "*/.git/*" | head -1)
      ;;
    graphql)
      FILE_PATH=$(find . -maxdepth 6 \( -name "*.graphql" -o -name "*.gql" \) \
        ! -path "*/node_modules/*" ! -path "*/.git/*" | head -1)
      ;;
    grpc)
      # For multiple .proto files we extract each one from git and concatenate
      PROTOS=$(find . -maxdepth 6 -name "*.proto" ! -path "*/.git/*" | sort)
      COUNT=$(echo "$PROTOS" | wc -l | tr -d ' ')
      > "$OUTPUT"
      echo "$PROTOS" | while IFS= read -r f; do
        echo "// === $f ===" >> "$OUTPUT"
        git show "origin/${BASE_REF}:${f#./}" >> "$OUTPUT" 2>/dev/null || true
        echo "" >> "$OUTPUT"
      done
      echo "[drift-agent] base grpc schema: $COUNT .proto files from origin/$BASE_REF → $OUTPUT"
      exit 0
      ;;
  esac

  if [ -z "$FILE_PATH" ]; then
    echo "::error::Could not find the schema file to extract from base branch" >&2
    exit 1
  fi

  # Strip leading ./ for git show
  GIT_PATH="${FILE_PATH#./}"
  git show "origin/${BASE_REF}:${GIT_PATH}" > "$OUTPUT" 2>/dev/null || {
    echo "::warning::Could not read $GIT_PATH from origin/$BASE_REF — the file may be new in this PR. Using head schema as base (diff will show everything as new)."
    cp "$FILE_PATH" "$OUTPUT"
  }
  echo "[drift-agent] base $TYPE schema: $GIT_PATH from origin/$BASE_REF → $OUTPUT"
  exit 0
fi

# ── Code-first: use a git worktree ──────────────────────────────────────────
echo "[drift-agent] code-first ($TYPE): creating worktree for origin/$BASE_REF..."

WORKTREE="/tmp/drift-base-worktree"
rm -rf "$WORKTREE"
git worktree add "$WORKTREE" "origin/${BASE_REF}" 2>/dev/null || {
  echo "::error::Failed to create git worktree for origin/$BASE_REF" >&2
  exit 1
}

# Copy generation scripts into the worktree so they're accessible
mkdir -p "$WORKTREE/.drift-scripts/generate"
cp -r "$SCRIPTS_DIR/generate/." "$WORKTREE/.drift-scripts/generate/"
chmod +x "$WORKTREE/.drift-scripts/generate/"*.sh

# Run the appropriate generator inside the worktree
case "$TYPE" in
  nestjs|fastapi|go) ;;
  *) echo "::error::Unknown code-first project type: $TYPE"; exit 1 ;;
esac
(cd "$WORKTREE" && bash ".drift-scripts/generate/${TYPE}.sh" "$OUTPUT") || {
  echo "::error::Base schema generation failed in worktree for $TYPE" >&2
  git worktree remove "$WORKTREE" --force 2>/dev/null || true
  exit 1
}

git worktree remove "$WORKTREE" --force 2>/dev/null || true
echo "[drift-agent] base $TYPE schema generated from origin/$BASE_REF → $OUTPUT"
