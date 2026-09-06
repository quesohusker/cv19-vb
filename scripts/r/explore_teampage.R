#!/usr/bin/env Rscript
# Dump the structure of a single team page on stats.ncaa.org.
#
# Three of the four scrape levels fail on every one of the 348 teams, which is
# a page-shape problem rather than a network one. Both failing call sites pick
# their table by POSITION:
#
#   find_team_contests()  css = "div.row:nth-child(4) > div:nth-child(1) > ..."
#   team_season_stats()   output[[2]]
#
# The one level that works, team_match_stats(), selects by id (#game_log_<n>_player).
# This prints what the page actually holds so the two positional selectors can be
# replaced with content-based ones instead of guessed at.
#
# Usage:  Rscript explore_teampage.R [team_id]
#         Rscript explore_teampage.R            # defaults to Nebraska 2026

suppressPackageStartupMessages({
  library(rvest)
  library(ncaavolleyballr)
})

args <- commandArgs(trailingOnly = TRUE)

# match the scraper's browser configuration exactly
shim <- file.path(dirname(dirname(normalizePath(
  sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1]),
  mustWork = FALSE))), "chrome-shim.sh")
if (!nzchar(Sys.getenv("VB_NO_SHIM")) && file.exists(shim)) {
  Sys.setenv(CHROMOTE_CHROME = shim)
  cat("browser: via shim\n")
} else {
  cat("browser: default chromote (headless)\n")
}
options(chromote.timeout = as.numeric(Sys.getenv("VB_CHROMOTE_TIMEOUT", "90")))

if (length(args) >= 1) {
  team_id <- args[1]
  team_lab <- team_id
} else {
  tm <- ncaavolleyballr::wvb_teams
  row <- tm[tm$yr == 2026 & tm$team_name == "Nebraska", ]
  if (nrow(row) == 0) stop("Nebraska 2026 not found in wvb_teams; pass a team_id.")
  team_id <- row$team_id[1]
  team_lab <- paste0("Nebraska (", team_id, ")")
}

url <- paste0("https://stats.ncaa.org/teams/", team_id)
cat("team:", team_lab, "\nURL: ", url, "\n\n")

pg <- tryCatch(rvest::read_html_live(url),
               error = function(e) { cat("FAILED:", conditionMessage(e), "\n"); NULL })
if (is.null(pg)) quit(status = 1)
Sys.sleep(5)

cat("=== title ===\n")
print(rvest::html_text(rvest::html_element(pg, "title")))
cat("(if this says 'Access Denied' nothing below is meaningful)\n")

cat("\n=== does the OLD positional selector still match? ===\n")
old_css <- paste0("div.row:nth-child(4) > div:nth-child(1) > div:nth-child(1) > ",
                  "div:nth-child(2) > table:nth-child(1)")
cat("  find_team_contests() css matches:",
    length(rvest::html_elements(pg, old_css)), "element(s)  [needs exactly 1]\n")

tabs <- rvest::html_elements(pg, "table")
cat("\n=== tables on the page:", length(tabs), "===\n")
cat("  team_season_stats() takes output[[2]] -- watch which index actually holds Player\n")

for (i in seq_along(tabs)) {
  t <- tryCatch(rvest::html_table(tabs[[i]]), error = function(e) NULL)
  id <- rvest::html_attr(tabs[[i]], "id")
  cls <- rvest::html_attr(tabs[[i]], "class")
  nbox <- length(rvest::html_elements(tabs[[i]], "a[href*='box_score']"))
  cat(sprintf("\n--- table %d ---\n", i))
  cat("  id:", if (is.na(id)) "(none)" else id,
      "| class:", if (is.na(cls)) "(none)" else cls, "\n")
  cat("  box_score links:", nbox, "\n")
  if (is.null(t) || nrow(t) == 0) { cat("  (empty / unparseable)\n"); next }
  cat("  dims:", nrow(t), "x", ncol(t), "\n")
  cat("  columns:", paste(names(t), collapse = " | "), "\n")
  cat("  has 'Date':", "Date" %in% names(t),
      "| has 'Opponent':", "Opponent" %in% names(t),
      "| has 'Player':", "Player" %in% names(t), "\n")
  print(utils::head(t, 3))
}

cat("\n=== content-based candidates (what the patch would select) ===\n")
has_col <- function(tb, col) {
  t <- tryCatch(rvest::html_table(tb), error = function(e) NULL)
  !is.null(t) && col %in% names(t)
}
sched <- which(vapply(tabs, function(tb)
  has_col(tb, "Date") && has_col(tb, "Opponent"), logical(1)))
roster <- which(vapply(tabs, has_col, logical(1), "Player"))
boxes <- which(vapply(tabs, function(tb)
  length(rvest::html_elements(tb, "a[href*='box_score']")) > 0, logical(1)))
cat("  table(s) with Date+Opponent (schedule):", paste(sched, collapse = ", "), "\n")
cat("  table(s) with Player (season stats):   ", paste(roster, collapse = ", "), "\n")
cat("  table(s) containing box_score links:   ", paste(boxes, collapse = ", "), "\n")

try(pg$session$close(), silent = TRUE)
