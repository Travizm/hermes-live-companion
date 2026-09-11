#!/usr/bin/env bash
# Self-tests for hermes-live-companion. No network, no microphone required.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PY="$HERMES_HOME/hermes-agent/venv/bin/python"
fail=0
echo "── stop-phrase matcher (voice-instruction disconnect) ──"
node test_stop_matcher.mjs || fail=1
echo
echo "── wake-phrase detection (real audio through the engine) ──"
"$PY" test_wake_detection.py || fail=1
echo
[ "$fail" = 0 ] && echo "ALL TESTS PASSED" || { echo "FAILURES — see above"; exit 1; }
