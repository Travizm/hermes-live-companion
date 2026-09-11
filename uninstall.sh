#!/usr/bin/env bash
# Convenience wrapper — every change is undone by the installer's revert path.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install.sh" --revert "$@"
