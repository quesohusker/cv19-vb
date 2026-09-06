#!/usr/bin/env bash
# Browser shim for chromote, to get past Akamai on stats.ncaa.org.
#
# chromote always appends a --headless flag (see chrome_headless_mode() in
# chromote's R/chrome.R -- there is no option to omit it), and headless is itself
# a detection signal. This wrapper drops any --headless* argument and adds the
# automation-flag suppression, then execs the real browser. Point chromote at it
# with CHROMOTE_CHROME and chromote is none the wiser.
#
# Prefers a real, installed browser over any bundled automation build, since a
# bundled Chromium-for-testing has a recognizable fingerprint. Edge first only
# because it is the least common automation choice; installed Chrome is fine and
# is what most people will land on. Override with VB_BROWSER.

set -euo pipefail

pick_browser() {
  if [ -n "${VB_BROWSER:-}" ]; then printf '%s' "$VB_BROWSER"; return; fi
  local candidates=(
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
    "/usr/bin/microsoft-edge"
    "/usr/bin/google-chrome"
    "/usr/bin/chromium"
    "/usr/bin/chromium-browser"
  )
  local c
  for c in "${candidates[@]}"; do
    [ -x "$c" ] && { printf '%s' "$c"; return; }
  done
}

BROWSER="$(pick_browser)"

if [ -z "$BROWSER" ] || [ ! -x "$BROWSER" ]; then
  echo "chrome-shim: no usable browser found." >&2
  echo "  Looked for Edge, Chrome, Brave and Chromium in the usual places." >&2
  echo "  Set VB_BROWSER to your browser binary, e.g." >&2
  echo "  export VB_BROWSER='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'" >&2
  exit 127
fi

[ -n "${VB_SHIM_VERBOSE:-}" ] && echo "chrome-shim: using $BROWSER" >&2

args=()
for a in "$@"; do
  case "$a" in
    --headless|--headless=*) ;;          # drop: headless is detectable
    *) args+=("$a") ;;
  esac
done

exec "$BROWSER" \
  --disable-blink-features=AutomationControlled \
  "${args[@]}"
