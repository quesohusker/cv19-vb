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
#
# It also forces its own --user-data-dir. Without one, Chrome opens the user's
# real profile set: on a machine with more than one profile it stops at the
# "Who's using Chrome?" picker and never navigates, and because a normal Chrome
# is usually already running, the new process hands off to that instance and
# exits immediately -- so chromote never sees a debugging port and reports
# "Cannot find an available port". A dedicated profile directory avoids the
# picker, guarantees a separate browser process with its own port, and leaves
# the user's own Chrome untouched.
#
# The profile directory persists between runs (VB_CHROME_PROFILE to relocate it)
# so cookies survive, which makes the traffic look less like a fresh bot on
# every request.

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

[ -n "${VB_SHIM_VERBOSE:-}" ] && echo "chrome-shim: using $BROWSER" >&2 || true

args=()
have_user_data_dir=0
for a in "$@"; do
  case "$a" in
    --headless|--headless=*) ;;          # drop: headless is detectable
    --user-data-dir=*) have_user_data_dir=1; args+=("$a") ;;
    *) args+=("$a") ;;
  esac
done

# Only supply a profile directory if the caller did not. Chromote does not,
# which is what lands us on the profile picker.
extra=()
if [ "$have_user_data_dir" -eq 0 ]; then
  PROFILE_DIR="${VB_CHROME_PROFILE:-$HOME/.cache/cv19-vb/chrome-profile}"
  mkdir -p "$PROFILE_DIR"
  extra+=("--user-data-dir=$PROFILE_DIR" "--profile-directory=Default")
  [ -n "${VB_SHIM_VERBOSE:-}" ] && echo "chrome-shim: profile $PROFILE_DIR" >&2 || true
fi

exec "$BROWSER" \
  --disable-blink-features=AutomationControlled \
  --no-first-run \
  --no-default-browser-check \
  --disable-session-crashed-bubble \
  "${extra[@]}" \
  "${args[@]}"
