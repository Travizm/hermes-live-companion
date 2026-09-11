# Agent install procedure

For an AI agent installing this on a user's Hermes machine. Follow it in order; **stop and report**
rather than improvising if a precondition fails. Every step is verifiable, and the verification is
part of the step — do not report success without it.

## Preconditions (verify, do not assume)

```bash
uname -s                                   # must be Darwin
node -e "console.log(require(process.env.NPM_ROOT + '/hermes-live-voice/package.json').version)" \
  || node -e "console.log(require(require('child_process').execSync('npm root -g').toString().trim()+'/hermes-live-voice/package.json').version)"
ls ~/.hermes/plugins/hermes-live/dashboard/plugin_api.py
curl -sf http://127.0.0.1:8788/ready | head -c 80      # hermes-live gateway
test -x ~/.hermes/hermes-agent/venv/bin/python && echo venv-ok
```

Abort if: not macOS; hermes-live-voice ≠ 1.1.3; the plugin dir is missing; the venv python is missing.

## Install

```bash
git clone https://github.com/Travizm/hermes-live-companion.git /tmp/hlc
cd /tmp/hlc && ./install.sh --phrase "<user's phrase>"
```

`install.sh` is idempotent (it detects its own patch marker and skips) and makes `.pre-companion`
backups of every file it touches.

## Verify (all four must pass)

```bash
curl -s http://127.0.0.1:8799/wake            # expect "armed": true, "phrase": "<phrase>"
/tmp/hlc/tests/run-tests.sh                    # matcher + wake-engine detection
node --check ~/.hermes/plugins/hermes-live/dashboard/dist/index.js
tail -3 ~/.hermes/logs/wake-live-voice.log     # no repeated "arm failed"
```

Then confirm the page: open `http://127.0.0.1:9119/live-voice` (launch the dashboard with
`env -u HERMES_WEB_DIST -u HERMES_DESKTOP`) and check for `Wake word: listening for '<phrase>'`.

## Known failures and the correct response

| Symptom | Cause | Action |
|---|---|---|
| `Timed out while opening the wake-word microphone` | launchd gets no macOS TCC microphone access | Run the daemon once from a Terminal to trigger the prompt, then `launchctl kickstart -k gui/$(id -u)/dev.hermes.wake-live-voice`. If the prompt never appears, the user must add the venv python under Privacy & Security → Microphone. |
| Page dies with *Desktop IPC bridge is unavailable* | dashboard launched with `HERMES_WEB_DIST` set | Relaunch with `env -u HERMES_WEB_DIST -u HERMES_DESKTOP` |
| Gateway crash-loops, log says `must be a string` | unquoted value in `config.env` | Quote it (`KEY="60000"`) and `hermes-live service restart` |
| Wake fires but the session never connects | provider handshake exceeded the 10 s cap | Confirm `patches/openai-realtime-adapter.patch` applied, then restart the gateway |
| Picker is empty | proxy timeout too short for a cold session query | Confirm `patches/plugin_api.patch` applied, restart the dashboard |
| `ModuleNotFoundError: pypinyin` | upstream `wake.sherpa` dependency omission | `pip install pypinyin` into the Hermes venv |
| Wake fires but nothing is audible | browser audio gesture rule | Ask the user to click the page once |

## Uninstall

```bash
/tmp/hlc/uninstall.sh     # restores every .pre-companion backup, removes the plist + daemon
```

## Rules

- **Never** enable `wake_word.enabled: true` in `config.yaml`. That arms the *desktop app's* own
  listener, which also starts the app's native voice loop on every wake — the exact double-answer
  this project exists to avoid. The daemon passes `enabled=True` to its own engine in-process.
- Never edit the vendor bundle by hand from an agent: apply `patches/`, so upgrades are reproducible.
- Report version drift instead of forcing a patch.
