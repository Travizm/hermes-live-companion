#!/usr/bin/env bash
# hermes-live-companion v0.1 — installer (macOS).
# Idempotent: safe to re-run after a hermes-live-voice upgrade. Reversible: --revert.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PYTHON="$HERMES_HOME/hermes-agent/venv/bin/python"
PLUGIN_DIR="$HERMES_HOME/plugins/hermes-live"
NPM_ROOT="$(npm root -g 2>/dev/null || echo /usr/local/lib/node_modules)"
ADAPTER="$NPM_ROOT/hermes-live-voice/dist/adapters/outbound/realtime/openai-realtime.adapter.js"
DAEMON_TARGET="$HERMES_HOME/scripts/wake-live-voice.py"
PLIST="$HOME/Library/LaunchAgents/dev.hermes.wake-live-voice.plist"
LABEL="dev.hermes.wake-live-voice"
BACKUP_SUFFIX=".pre-companion"

PHRASE="hey chaddy"
WAKE_PORT="8799"
CHECK_ONLY=0
REVERT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --phrase) PHRASE="$2"; shift 2 ;;
    --port) WAKE_PORT="$2"; shift 2 ;;
    --check-only) CHECK_ONLY=1; shift ;;
    --revert) REVERT=1; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────── revert
if [ "$REVERT" = 1 ]; then
  say "Reverting hermes-live-companion"
  for f in "$PLUGIN_DIR/dashboard/plugin_api.py" "$PLUGIN_DIR/dashboard/dist/index.js" "$ADAPTER"; do
    if [ -f "$f$BACKUP_SUFFIX" ]; then cp "$f$BACKUP_SUFFIX" "$f"; rm -f "$f$BACKUP_SUFFIX"; ok "restored $(basename "$f")"; fi
  done
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && ok "stopped launchd agent" || true
  rm -f "$PLIST" "$DAEMON_TARGET"; ok "removed daemon + plist"
  "$PYTHON" - <<'PY' || true
import subprocess, sys
cmd = ["hermes", "config", "set", "wake_word.enabled", "false"]
subprocess.run(cmd, check=False)
PY
  warn "wake_word.enabled set to false (provider/phrase keys left in place; remove them if you want)"
  echo; say "Reverted. Restart the dashboard to drop the patched page."; exit 0
fi

# ─────────────────────────────────────────────────────────────── preconditions
say "1/7  Checking prerequisites"
[ "$(uname -s)" = "Darwin" ] || die "macOS only (found $(uname -s))"
command -v node >/dev/null || die "node not found"
command -v ffmpeg >/dev/null || die "ffmpeg not found (brew install ffmpeg)"
[ -x "$PYTHON" ] || die "Hermes venv python not found at $PYTHON"
[ -d "$PLUGIN_DIR" ] || die "hermes-live plugin not installed at $PLUGIN_DIR (npm i -g hermes-live-voice && hermes-live setup)"
[ -f "$ADAPTER" ] || die "hermes-live-voice not found in npm root ($NPM_ROOT)"
ok "host + tooling present"

VERSION="$(node -e "try{console.log(require('$NPM_ROOT/hermes-live-voice/package.json').version)}catch(e){process.exit(1)}" 2>/dev/null || echo unknown)"
[ "$VERSION" = "1.1.3" ] || die "hermes-live-voice $VERSION is not a supported version (this release pins 1.1.3).
     Either install 1.1.3 (npm i -g hermes-live-voice@1.1.3) or rebase patches/ by hand."
ok "hermes-live-voice $VERSION"

if ! curl -sf -o /dev/null "http://127.0.0.1:8788/ready"; then
  warn "hermes-live gateway is not answering on :8788 — start it with 'hermes-live service start'"
fi
if [ ! -d "$HERMES_HOME/hermes-agent/web/dist" ] && [ ! -d "$HERMES_HOME/hermes-agent/hermes_cli/web_dist" ]; then
  warn "dashboard SPA not built yet; build it so the plugin page can load:
       cd $HERMES_HOME/hermes-agent/web && npm run build"
fi

if [ "$CHECK_ONLY" = 1 ]; then echo; say "Check-only run complete — nothing was changed."; exit 0; fi

# ─────────────────────────────────────────────────────────────── python deps
say "2/7  Installing wake-engine dependencies (sherpa-onnx, sentencepiece, pypinyin)"
"$PYTHON" - <<'PY'
import sys
sys.path.insert(0, str(__import__("pathlib").Path.home() / ".hermes" / "hermes-agent"))
try:
    from tools import lazy_deps
    lazy_deps.ensure("wake.sherpa", prompt=False)
except Exception as exc:
    print(f"  (lazy_deps unavailable: {exc})")
PY
"$PYTHON" -m pip install --quiet --disable-pip-version-check sherpa-onnx sentencepiece pypinyin
# pypinyin is an upstream omission: sherpa_onnx.text2token imports it, and its absence
# makes the sherpa engine raise at build time so the listener never arms.
"$PYTHON" -c "import sherpa_onnx, sentencepiece, pypinyin; print('  ✓ engine imports OK')"

say "3/7  Warming the wake-word model (one-time ~13 MB download)"
"$PYTHON" - <<'PY'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path.home() / ".hermes" / "hermes-agent"))
from tools.wake_word_engines import _ensure_sherpa_model
print("  ✓ model at", _ensure_sherpa_model())
PY

# ─────────────────────────────────────────────────────────────── vendor patches
say "4/7  Applying vendor patches (backups written as $BACKUP_SUFFIX)"
apply_patch() {  # apply_patch <patchfile> <target-file> <dir> <marker>
  local patch="$1" target="$2" dir="$3" marker="$4"
  if grep -q "$marker" "$target" 2>/dev/null; then ok "already patched: $(basename "$target")"; return 0; fi
  [ -f "$target$BACKUP_SUFFIX" ] || cp "$target" "$target$BACKUP_SUFFIX"
  ( cd "$dir" && patch -p1 --forward --silent < "$patch" ) || die "patch failed: $(basename "$patch") — restore from $BACKUP_SUFFIX and report this"
  ok "patched $(basename "$target")"
}
apply_patch "$REPO_DIR/patches/plugin_api.patch"            "$PLUGIN_DIR/dashboard/plugin_api.py"  "$PLUGIN_DIR" "hermes-live-companion"
apply_patch "$REPO_DIR/patches/dashboard-index.patch"       "$PLUGIN_DIR/dashboard/dist/index.js"  "$PLUGIN_DIR" "hermes-live-companion"
apply_patch "$REPO_DIR/patches/openai-realtime-adapter.patch" "$ADAPTER" "$NPM_ROOT/hermes-live-voice" "hermes-live-companion"
node --check "$PLUGIN_DIR/dashboard/dist/index.js" && ok "patched bundle parses"
node --check "$ADAPTER" && ok "patched adapter parses"

# ─────────────────────────────────────────────────────────────── config
say "5/7  Configuring wake word, provider timeouts and turn detection"
hermes config set wake_word.enabled false   >/dev/null  # the APP's listener stays off; the daemon owns the mic
hermes config set wake_word.provider sherpa >/dev/null
hermes config set wake_word.phrase "$PHRASE" >/dev/null
ok "wake_word: provider=sherpa phrase='$PHRASE' (app listener off)"

CFG="$HERMES_HOME/hermes-live/config.env"
if [ -f "$CFG" ]; then
  cp -n "$CFG" "$CFG$BACKUP_SUFFIX" 2>/dev/null || true
  grep -q '^OPENAI_REALTIME_TURN_DETECTION=' "$CFG" || printf '\n# hermes-live-companion: seamless turns (was unset => "disabled")\nOPENAI_REALTIME_TURN_DETECTION="semantic_vad"\n' >> "$CFG"
  grep -q '^HERMES_LIVE_PROVIDER_READY_TIMEOUT_MS=' "$CFG" || printf '\n# hermes-live-companion: provider handshake can exceed 10s on a cold path\nHERMES_LIVE_PROVIDER_READY_TIMEOUT_MS="60000"\n' >> "$CFG"
  ok "gateway config updated ($CFG)"
  hermes-live service restart >/dev/null 2>&1 || warn "could not restart hermes-live service"
else
  warn "no $CFG yet — run 'hermes-live setup' then re-run this installer"
fi

# ─────────────────────────────────────────────────────────────── daemon + launchd
say "6/7  Installing companion daemon + launchd agent"
mkdir -p "$HERMES_HOME/scripts" "$HOME/Library/LaunchAgents"
install -m 0755 "$REPO_DIR/scripts/wake-live-voice.py" "$DAEMON_TARGET"
ok "daemon at $DAEMON_TARGET"

sed -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__DAEMON__|$DAEMON_TARGET|g" \
    -e "s|__HERMES_HOME__|$HERMES_HOME|g" \
    -e "s|__PORT__|$WAKE_PORT|g" \
    "$REPO_DIR/launchd/dev.hermes.wake-live-voice.plist.template" > "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "$PLIST" && ok "launchd agent loaded ($LABEL)"
sleep 8

# ─────────────────────────────────────────────────────────────── verify
say "7/7  Verifying"
STATE="$(curl -sf "http://127.0.0.1:$WAKE_PORT/wake" || true)"
if [ -z "$STATE" ]; then
  warn "bridge did not answer on :$WAKE_PORT yet — check $HERMES_HOME/logs/wake-live-voice.log"
else
  echo "  $STATE"
  case "$STATE" in
    *'"armed": true'*) ok "listener armed" ;;
    *) warn "not armed yet. If you see 'Timed out while opening the wake-word microphone', macOS is
       withholding microphone access from the launchd process — say the phrase once via
       'python $DAEMON_TARGET' in a terminal to trigger the permission prompt, then re-run this script." ;;
  esac
fi
if [ -f "$HERMES_HOME/logs/wake-live-voice.log" ]; then
  echo "  last daemon log line:"; tail -1 "$HERMES_HOME/logs/wake-live-voice.log" | sed 's/^/    /'
fi

cat <<EOF

$(say "Installed.")
  Wake phrase : $PHRASE
  Bridge      : http://127.0.0.1:$WAKE_PORT/wake
  Dashboard   : open it and go to PLUGINS → LIVE VOICE

  Say the phrase out loud. Expect a chime, then the page connects.
  If playback stays silent on the first reply, click the page once (browser audio gesture rule).

  Re-run after 'npm i -g hermes-live-voice' — upgrades overwrite the patches.
  Undo everything: ./install.sh --revert
EOF
