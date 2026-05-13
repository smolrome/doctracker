#!/bin/bash
# sync-version.sh
# Fetches latest_version from the live API and stamps app.json before an EAS build.
# Exits non-zero on any failure so EAS aborts the build rather than shipping a
# mis-versioned APK.
#
# Usage:
#   bash scripts/sync-version.sh          # manual
#   npm run sync-version                  # via npm script
#   eas build --pre-build-command "..."   # wired into EAS profile (see eas.json)

set -euo pipefail

API_URL="http://localhost:7001/api/app-version"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_JSON="$SCRIPT_DIR/../app.json"

# ── 1. Fetch version info from the live API ────────────────────────────────────
echo "⏳ Fetching version info from server..."
RESPONSE=$(curl --silent --fail --max-time 10 "$API_URL") || {
  echo "❌ ERROR: curl failed — could not reach $API_URL"
  echo "   Check your network connection or verify the server is running."
  exit 1
}

if [ -z "$RESPONSE" ]; then
  echo "❌ ERROR: Server returned an empty response from $API_URL"
  exit 1
fi

# ── 2. Parse latest_version from the JSON response ────────────────────────────
# Uses python3 (guaranteed present in this Python project) for reliable JSON
# parsing — avoids brittle grep/sed that breaks on formatting changes.
LATEST=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    v = data.get('latest_version', '').strip()
    if not v:
        raise ValueError('latest_version is empty or missing')
    print(v)
except Exception as e:
    print(f'PARSE_ERROR: {e}', file=sys.stderr)
    sys.exit(1)
") || {
  echo "❌ ERROR: Could not parse latest_version from server response."
  echo "   Response was: $RESPONSE"
  exit 1
}

# ── 3. Read current version from app.json ─────────────────────────────────────
CURRENT=$(python3 -c "
import json, sys
try:
    with open('$APP_JSON') as f:
        data = json.load(f)
    print(data['expo']['version'])
except Exception as e:
    print(f'READ_ERROR: {e}', file=sys.stderr)
    sys.exit(1)
") || {
  echo "❌ ERROR: Could not read version from $APP_JSON"
  exit 1
}

# ── 4. Short-circuit if already in sync ───────────────────────────────────────
if [ "$CURRENT" = "$LATEST" ]; then
  echo "✅ app.json is already at version $CURRENT — nothing to do."
  exit 0
fi

# ── 5. Write new version into app.json ────────────────────────────────────────
python3 -c "
import json, sys

app_json = '$APP_JSON'
latest   = '$LATEST'

try:
    with open(app_json, 'r') as f:
        data = json.load(f)

    data['expo']['version'] = latest

    with open(app_json, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
except Exception as e:
    print(f'WRITE_ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" || {
  echo "❌ ERROR: Failed to write updated version to $APP_JSON"
  exit 1
}

# ── 6. Confirm ────────────────────────────────────────────────────────────────
echo "✅ app.json version updated: $CURRENT → $LATEST"
