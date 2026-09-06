#!/usr/bin/env Rscript
# Which stats.ncaa.org paths are actually blocked right now?
#
# The team list page returned 348 teams. A team page returns "Access Denied"
# from both headless chromote and a real browser. Those cannot both be a
# blanket IP ban, so this checks each path shape in one run and reports the
# page title for each -- "NCAA Statistics" means through, "Access Denied"
# means blocked.
#
# It also tries the team page a second time after first loading the site root,
# to see whether an Akamai cookie picked up from a normal landing page is what
# the direct hit is missing.
#
# Usage:  Rscript probe_paths.R [team_id]

suppressPackageStartupMessages(library(rvest))

args <- commandArgs(trailingOnly = TRUE)
team_id <- if (length(args) >= 1) args[1] else "625334"   # Nebraska 2026

shim <- file.path(dirname(dirname(normalizePath(
  sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1]),
  mustWork = FALSE))), "chrome-shim.sh")
if (!nzchar(Sys.getenv("VB_NO_SHIM")) && file.exists(shim)) {
  Sys.setenv(CHROMOTE_CHROME = shim)
  cat("browser: via shim (real browser)\n\n")
} else {
  cat("browser: default chromote (headless)\n\n")
}
options(chromote.timeout = as.numeric(Sys.getenv("VB_CHROMOTE_TIMEOUT", "90")))

probe <- function(label, url, pause = 6) {
  cat(sprintf("%-34s", label))
  pg <- tryCatch(rvest::read_html_live(url), error = function(e) NULL)
  if (is.null(pg)) { cat("  LAUNCH FAILED\n"); return(invisible(NULL)) }
  Sys.sleep(pause)
  title <- tryCatch(rvest::html_text(rvest::html_element(pg, "title")),
                    error = function(e) NA_character_)
  ntab <- length(rvest::html_elements(pg, "table"))
  nlink <- length(rvest::html_elements(pg, "a"))
  cat(sprintf("  %-20s tables:%-4d links:%-5d\n",
              substr(ifelse(is.na(title), "(none)", title), 1, 20), ntab, nlink))
  invisible(pg)
}

cat("path                                  title                tables    links\n")
cat(strrep("-", 78), "\n")

probe("site root",            "https://stats.ncaa.org/")
probe("team list (worked)",   paste0("https://stats.ncaa.org/team/inst_team_list",
                                     "?academic_year=2027&conf_id=-1&division=1&sport_code=WVB"))
probe("team page (fails)",    paste0("https://stats.ncaa.org/teams/", team_id))
probe("team roster",          paste0("https://stats.ncaa.org/teams/", team_id, "/roster"))
probe("team season stats",    paste0("https://stats.ncaa.org/teams/", team_id, "/season_to_date_stats"))

cat("\n--- same team page again, in a session warmed on the site root ---\n")
root <- tryCatch(rvest::read_html_live("https://stats.ncaa.org/"),
                 error = function(e) NULL)
if (!is.null(root)) {
  Sys.sleep(6)
  cat(sprintf("%-34s", "  root loaded, now navigating"))
  ok <- tryCatch({ root$session$Page$navigate(
      paste0("https://stats.ncaa.org/teams/", team_id)); TRUE },
      error = function(e) FALSE)
  if (ok) {
    Sys.sleep(8)
    cat(sprintf("  %-20s tables:%-4d links:%-5d\n",
        substr(rvest::html_text(rvest::html_element(root, "title")), 1, 20),
        length(rvest::html_elements(root, "table")),
        length(rvest::html_elements(root, "a"))))
  } else cat("  navigate failed\n")
  try(root$session$close(), silent = TRUE)
}

cat("\nReading the result:\n")
cat("  all 'Access Denied'          -> IP-level block; stop for an hour.\n")
cat("  list through, /teams/ denied -> the block is path-specific, not the IP.\n")
cat("  warmed attempt through       -> a landing cookie is what direct hits lack.\n")
