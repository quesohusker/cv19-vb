#!/usr/bin/env python3
r"""Make ncaavolleyballr's get_teams() work against stats.ncaa.org today.

Three problems, all in get_teams() only -- the rest of the package is fine.

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

3. SILENT TEAM LOSS. get_teams() built its roster by concatenating the 32
   per-conference pages, even though the conf_id=-1 page it already fetched
   lists all 348 D1 teams itself. A per-conference page that failed returned
   invisible(), purrr::list_rbind() dropped the NULL, and that conference's
   teams disappeared with no error -- the likely cause of the missing 2025
   Sun Belt. The conf_id=-1 roster is now authoritative and the per-conference
   pages only supply labels, left-joined on. A failed conference page now
   costs a label, not the teams, and is reported.

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

  # the conf_id=-1 page already lists every team in the division; treat that as
  # the roster of record so a failed conference page cannot delete teams
  roster_links <- data_read |>
    rvest::html_elements("table") |>
    rvest::html_elements("a")
  roster_df <- data.frame(
    team_url = rvest::html_attr(roster_links, "href"),
    team_name = trimws(rvest::html_text(roster_links)),
    div = division,
    yr = year
  )
  roster_df <- roster_df[grepl("^/teams/[0-9]+$", roster_df$team_url), , drop = FALSE]
  roster_df <- unique(roster_df)
  if (nrow(roster_df) == 0) {
    cli::cli_warn("No team links found on the team list page.")
    return(invisible())
  }
'''
)

OLD_LOOP = r"""  conferences_team_df <- lapply(conference_df$conference_id, function(x) {
    conf_team_urls <- paste0(
      "http://stats.ncaa.org/team/inst_team_list?academic_year=",
      url_year,
      "&conf_id=",
      x,
      "&division=",
      division,
      "&sport_code=",
      sport
    )
    resp <- tryCatch(
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

    # assemble data frame
    data <- data.frame(
      team_url = team_urls,
      team_name = team_names,
      div = division,
      yr = year,
      conference_id = x
    )
    data <- data |>
      dplyr::left_join(conference_df, by = c("conference_id"))
    Sys.sleep(5)
    return(data)
  }) |>
    purrr::list_rbind() |>
    dplyr::mutate(team_id = stringr::str_extract(.data$team_url, "(\\d+)")) |>
    dplyr::select(
      "team_id",
      "team_name",
      "conference_id",
      "conference",
      "div",
      "yr"
    )
}"""

NEW_LOOP = (
    "  " + MARKER + "\n"
    + r'''  # visit each conference page only to learn which teams belong to it
  failed_conf <- character(0)
  conf_map <- lapply(conference_df$conference_id, function(x) {
    conf_team_urls <- paste0(
      "http://stats.ncaa.org/team/inst_team_list?academic_year=",
      url_year,
      "&conf_id=",
      x,
      "&division=",
      division,
      "&sport_code=",
      sport
    )
    resp <- tryCatch(request_live_url(url = conf_team_urls),
                     error = function(cnd) NULL)
    if (is.null(resp) || is.character(resp)) {
      failed_conf <<- c(failed_conf, x)
      return(NULL)
    }
    on.exit(try(resp$session$close(), silent = TRUE), add = TRUE)

    hrefs <- resp |>
      rvest::html_elements("table") |>
      rvest::html_elements("a") |>
      rvest::html_attr("href")
    hrefs <- hrefs[grepl("^/teams/[0-9]+$", hrefs)]
    if (length(hrefs) == 0) {
      failed_conf <<- c(failed_conf, x)
      return(NULL)
    }
    Sys.sleep(stats::runif(1, 3, 7))
    data.frame(team_url = unique(hrefs), conference_id = x)
  }) |>
    purrr::list_rbind()

  if (length(failed_conf)) {
    cli::cli_warn(paste0("Conference page(s) failed, so those teams keep their ",
                         "roster entry but lose the label: conf_id ",
                         paste(failed_conf, collapse = ", "), "."))
  }
  # a team belongs to exactly one conference; guard against a doubled menu
  conf_map <- conf_map[!duplicated(conf_map$team_url), , drop = FALSE]

  conferences_team_df <- roster_df |>
    dplyr::left_join(conf_map, by = "team_url") |>
    dplyr::left_join(conference_df, by = "conference_id") |>
    dplyr::mutate(team_id = stringr::str_extract(.data$team_url, "(\\d+)")) |>
    dplyr::select(
      "team_id",
      "team_name",
      "conference_id",
      "conference",
      "div",
      "yr"
    ) |>
    dplyr::distinct()

  unlabelled <- sum(is.na(conferences_team_df$conference_id))
  if (unlabelled > 0) {
    cli::cli_warn(paste0(unlabelled, " of ", nrow(conferences_team_df),
                         " teams have no conference label."))
  }
  conferences_team_df
}'''
)


PATCHES = [
    ("initial team-list request", OLD_INITIAL_REQUEST, NEW_INITIAL_REQUEST),
    ("conference selection", OLD_CONFERENCE_BLOCK, NEW_CONFERENCE_BLOCK),
    ("per-conference loop", OLD_LOOP, NEW_LOOP),
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
          "content-based conference selection, roster-of-record join")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
