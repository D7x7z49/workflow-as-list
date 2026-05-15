#!/usr/bin/env bash
# scripts/actions/check-tag.sh
# Validate package name and version extracted from a Git tag.
# Usage: check-tag.sh <package> <version>

set -euo pipefail

PACKAGE="${1:-}"
VERSION="${2:-}"

# Check package name: non-empty, allowed characters: a-z A-Z 0-9 _ -
if ! grep -qE '^[a-zA-Z0-9_-]+$' <<< "$PACKAGE"; then
    echo "::error::Invalid package name: '$PACKAGE'"
    exit 1
fi

# Check version: simplified semver (X.Y.Z with optional pre-release identifiers)
if ! grep -qE '^[0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9.]*$' <<< "$VERSION"; then
    echo "::error::Invalid version: '$VERSION'"
    exit 1
fi

echo "Package and version are valid: <$PACKAGE> <$VERSION>"
