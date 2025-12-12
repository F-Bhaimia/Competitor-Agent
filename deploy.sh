#!/bin/bash
# DEPRECATED: Use install.sh instead
# This script is kept for backwards compatibility

echo "Note: deploy.sh is deprecated. Using install.sh instead."
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/install.sh" "$@"
