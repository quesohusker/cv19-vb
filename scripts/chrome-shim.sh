#!/usr/bin/env bash
# Browser shim for chromote, to get past Akamai on stats.ncaa.org.
#
# chromote always appends a --headless flag (see chrome_headless_mode() in
# chromote's R/chrome.R -- there is no option to omit it), and headless is itself
# a detection signal. This wrapper drops any --headless* argument and adds the
# automation-flag suppression, then execs the real browser. Point chromote at it
# with CHROMOTE_CHROME and chromote is none the wiser.
#
# Defaults to Microsoft Edge because its TLS/JA3 fingerprint differs from
# bundled Chromium, which is the single biggest difference between a scrape that
# gets through and one that collects 403s. Override with VB_BROWSER.

set -euo pipefail

BROWSER="${VB_BROWSER:-/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge}"

if [ ! -x "$BROWSER" ]; then
  echo "chrome-shim: browser not found or not executable: $BROWSER" >&2
  echo "  set VB_BROWSER to your browser binary, e.g." >&2
  echo "  export VB_BROWSER='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'" >&2
  exit 127
fi

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
