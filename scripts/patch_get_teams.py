#!/usr/bin/env python3
"""Route get_teams() through headless Chrome instead of plain HTTP.

stats.ncaa.org returns 403 to plain HTTP requests regardless of user agent --
it appears to fingerprint the client rather than read headers. Headless Chrome
gets through fine.

The package already knows this: its stats functions call request_live_url(),
which wraps rvest::read_html_live(). Only get_teams() still uses request_url()
(plain httr2), so team discovery is the one step that fails. This rewrites its
two request sites to use the browser path the rest of the package already uses.

Idempotent, and fails loudly if upstream has changed shape rather than
silently producing a half-patched file.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "# patched: browser path (stats.ncaa.org 403s plain HTTP)"

# (description, exact text to find, replacement)
PATCHES = [
    (
        "initial team-list request",
        """  resp <- tryCatch(
    error = function(cnd) {
      cli::cli_warn("No website available.")
    },
    request_url(url = url)
  )
  if (length(resp) == 1) {
    if (grepl(pattern = "No website available", resp)) return(invisible())
  }

  # create HTML table
  data_read <- resp |>
    httr2::resp_body_html()
""",
        f"""  {MARKER}
  data_read <- request_live_url(url = url)
  if (is.null(data_read) || is.character(data_read)) return(invisible())
  on.exit(try(data_read$session$close(), silent = TRUE), add = TRUE)
""",
    ),
    (
        "per-conference request",
        """    resp <- tryCatch(
      error = function(cnd) {
        cli::cli_warn("No website available.")
      },
      request_url(url = conf_team_urls)
    )
    if (length(resp) == 1) {
      if (grepl(pattern = "No website available", resp)) return(invisible())
    }

    team_urls <- resp |>
      httr2::resp_body_html() |>
      rvest::html_elements("table") |>
      rvest::html_elements("a") |>
      rvest::html_attr("href")

    team_names <- resp |>
      httr2::resp_body_html() |>
      rvest::html_elements("table") |>
      rvest::html_elements("a") |>
      rvest::html_text()
""",
        f"""    {MARKER}
    resp <- request_live_url(url = conf_team_urls)
    if (is.null(resp) || is.character(resp)) return(invisible())
    on.exit(try(resp$session$close(), silent = TRUE), add = TRUE)

    team_urls <- resp |>
      rvest::html_elements("table") |>
      rvest::html_elements("a") |>
      rvest::html_attr("href")

    team_names <- resp |>
      rvest::html_elements("table") |>
      rvest::html_elements("a") |>
      rvest::html_text()
""",
    ),
    (
        "de-duplicate conferences and teams",
        """  conference_df <- data.frame(
    conference = conference_names,
    conference_id = conference_ids
  )
""",
        f"""  conference_df <- data.frame(
    conference = conference_names,
    conference_id = conference_ids
  )
  {MARKER}
  # A rendered DOM is not the raw server HTML, and the conference list is picked by
  # positional index (.level2[[4]]), so the browser path can pick up a doubled menu.
  # That doubles every team row, and a duplicated row makes find_team_id() return a
  # length-2 vector, which chromote rejects with "string value expected at position 12".
  conference_df <- unique(conference_df)
"""
    ),
    (
        "de-duplicate the returned team table",
        """    dplyr::select(
      "team_id",
      "team_name",
      "conference_id",
      "conference",
      "div",
      "yr"
    )
}""",
        """    dplyr::select(
      "team_id",
      "team_name",
      "conference_id",
      "conference",
      "div",
      "yr"
    ) |>
    dplyr::distinct()
}"""
    ),
]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: patch_get_teams.py <path-to-ncaavolleyballr-source>")
        return 2
    target = Path(sys.argv[1]) / "R" / "get_teams.R"
    if not target.exists():
        print(f"not found: {target}")
        return 1

    text = target.read_text()
    if MARKER in text:
        print("  get_teams.R already patched")
        return 0

    for label, old, new in PATCHES:
        if old not in text:
            print(f"  FAILED: could not find the {label} block.\n"
                  "  Upstream get_teams.R has changed; the patch needs updating.")
            return 1
        text = text.replace(old, new, 1)

    target.write_text(text)
    print(f"  get_teams.R patched: {len(PATCHES)} request sites now use headless Chrome")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
