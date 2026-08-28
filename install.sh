#!/usr/bin/env bash
# Puts `mymailforai` on the PATH by symlinking it into ~/.local/bin.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${MYMAILFORAI_BIN:-$HOME/.local/bin}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required and was not found on PATH." >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
ln -sf "$REPO_DIR/bin/mymailforai" "$TARGET_DIR/mymailforai"
echo "linked $TARGET_DIR/mymailforai -> $REPO_DIR/bin/mymailforai"

case ":$PATH:" in
  *":$TARGET_DIR:"*) ;;
  *) echo "note: $TARGET_DIR is not on your PATH — add it to your shell profile." ;;
esac

echo
echo "next: mymailforai login you@gmail.com"
