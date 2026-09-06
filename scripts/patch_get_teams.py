#!/usr/bin/env python3
r"""Make ncaavolleyballr's get_teams() work against stats.ncaa.org today.

Two problems, both in get_teams() only -- the rest of the package is fine.

1. TRANSPORT. stats.ncaa.org sits behind Akamai and returns 403 to plain HTTP
   regardless of user agent; it fingerprints the client. The package's stats
   functions already go through request_live_url() (a real browser), but
   get_teams() still used plain request_url(), so team discovery was the one
   step that failed. Both of its request sites are switched to the browser path.

2. DOM POSITION. get_teams() located the conference menu as
   (html_elements(".level2"))[[4]] -- a positional index. How many .level2
   blocks a page yields depends on the browser and on whether it is headless,
   so that index is not stable: under one configuration it pointed at a doubled
   menu (every team returned twice, 696 teams instead of 348), and under another
   it did not exist at all ("subscript out of bounds"). It is replaced with a
   content-based selector: conference links are exactly the anchors whose href
   is javascript:changeConference(<digits>). The "all conferences" link uses
   (-1), which the digit pattern excludes on its own.

Idempotent. Fails loudly rather than half-patching if upstream changes shape.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "# patched: browser transport + content-based conference selection"

OLD_INITIAL_REQUEST = '''  resp <- tryCatch(
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
'''

NEW_INITIAL_REQUEST = f'''  {MARKER}
  data_read <- request_live_url(url = url)
  if (is.null(data_read) || is.character(data_read)) return(invisible())
  on.exit(try(data_read$session$close(), silent = TRUE), add = TRUE)
'''

OLD_CONFERENCE_BLOCK = r'''  conference_names <- ((data_read |>
    rvest::html_elements(".level2"))[[4]] |>
    rvest::html_elements("a") |>
    rvest::html_text())[-1]

  conference_ids <- (data_read |>
    rvest::html_elements(".level2"))[[4]] |>
    rvest::html_elements("a") |>
    rvest::html_attr("href") |>
    stringr::str_extract("javascript:changeConference\\(\\d+\\)") |>
    stringr::str_subset("javascript:changeConference\\(\\d+\\)") |>
    stringr::str_extract("\\d+")

  conference_df <- data.frame(
    conference = conference_names,
    conference_id = conference_ids
  )
'''

NEW_CONFERENCE_BLOCK = (
    "  " + MARKER + "\n"
    r'''  conf_links <- rvest::html_elements(data_read, "a")
  conf_href <- rvest::html_attr(conf_links, "href")
  conf_keep <- !is.na(conf_href) & grepl("changeConference\\(\\d+\\)", conf_href)
  if (!any(conf_keep)) {
    cli::cli_warn("No conference links found on the team list page.")
    return(invisible())
  }
  conference_ids <- stringr::str_extract(
    stringr::str_extract(conf_href[conf_keep], "changeConference\\(\\d+\\)"),
    "\\d+"
  )
  conference_names <- trimws(rvest::html_text(conf_links[conf_keep]))

  conference_df <- data.frame(
    conference = conference_names,
    conference_id = conference_ids
  )
  conference_df <- conference_df[nzchar(conference_df$conference), , drop = FALSE]
  conference_df <- unique(conference_df)
'''
)

OLD_CONF_REQUEST = '''    resp <- tryCatch(
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
'''

NEW_CONF_REQUEST = f'''    {MARKER}
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
'''

OLD_TAIL = '''    dplyr::select(
      "team_id",
      "team_name",
      "conference_id",
      "conference",
      "div",
      "yr"
    )
}'''

NEW_TAIL = '''    dplyr::select(
      "team_id",
      "team_name",
      "conference_id",
      "conference",
      "div",
      "yr"
    ) |>
    dplyr::distinct()
}'''

PATCHES = [
    ("initial team-list request", OLD_INITIAL_REQUEST, NEW_INITIAL_REQUEST),
    ("conference selection", OLD_CONFERENCE_BLOCK, NEW_CONFERENCE_BLOCK),
    ("per-conference request", OLD_CONF_REQUEST, NEW_CONF_REQUEST),
    ("de-duplicate the team table", OLD_TAIL, NEW_TAIL),
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
    print(f"  get_teams.R patched ({len(PATCHES)} sites): browser transport, "
          "content-based conference selection, de-duplicated output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
