#!/usr/bin/env Rscript
# Find a route to team data that does not use a direct hit on /teams/<id>.
#
# Established by probe_paths.R: the site root, the team list and the rankings
# pages all load normally, while /teams/<id>, /teams/<id>/roster and
# /teams/<id>/season_to_date_stats all return "Access Denied" -- from headless
# chromote and from a real browser with its own profile alike, and loading the
# site root first does not help. So this is a path rule, not an IP ban and not
# headless detection.
#
# That matters because every level of the scrape begins at /teams/<id>:
# find_team_contests(), team_match_stats(), team_season_stats(),
# player_season_stats() and team_season_info() all build that URL first.
#
# Four candidate routes, in increasing order of how much rework each implies:
#   A  direct navigate                 -- the control, expected to fail
#   B  click a real link on the team list page (sends a Referer, which a
#      scripted navigate does not; Akamai rules often key on exactly that)
#   C  the daily scoreboard, which carries contest IDs for every match on a
#      date and would replace find_team_contests() with ~100 requests for a
#      whole season instead of 348
#   D  the older singular /team/<id> URL shape
#
# Usage:  Rscript probe_alt_paths.R [team_id] [game_date MM/DD/YYYY]

suppressPackageStartupMessages(library(rvest))

args <- commandArgs(trailingOnly = TRUE)
team_id <- if (length(args) >= 1) args[1] else "625334"
game_date <- if (length(args) >= 2) args[2] else format(Sys.Date() - 2, "%m/%d/%Y")

shim <- file.path(dirname(dirname(normalizePath(
  sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1]),
  mustWork = FALSE))), "chrome-shim.sh")
if (!nzchar(Sys.getenv("VB_NO_SHIM")) && file.exists(shim)) {
  Sys.setenv(CHROMOTE_CHROME = shim)
  cat("browser: via shim (real browser)\n")
}
options(chromote.timeout = as.numeric(Sys.getenv("VB_CHROMOTE_TIMEOUT", "90")))
cat("team_id:", team_id, " game_date:", game_date, "\n\n")

report <- function(label, pg) {
  if (is.null(pg)) { cat(sprintf("  %-40s LAUNCH FAILED\n", label)); return(invisible()) }
  title <- tryCatch(rvest::html_text(rvest::html_element(pg, "title")),
                    error = function(e) NA_character_)
  cat(sprintf("  %-40s %-18s tables:%-4d links:%-5d\n", label,
              substr(ifelse(is.na(title), "(none)", title), 1, 18),
              length(rvest::html_elements(pg, "table")),
              length(rvest::html_elements(pg, "a"))))
}

LIST <- paste0("https://stats.ncaa.org/team/inst_team_list",
               "?academic_year=2027&conf_id=-1&division=1&sport_code=WVB")

cat("A  direct navigate to /teams/<id>   (control -- expected to fail)\n")
pg <- tryCatch(read_html_live(paste0("https://stats.ncaa.org/teams/", team_id)),
               error = function(e) NULL)
if (!is.null(pg)) { Sys.sleep(6); report("direct /teams/<id>", pg)
                    try(pg$session$close(), silent = TRUE) }

cat("\nB  click the team's link on the team list page\n")
pg <- tryCatch(read_html_live(LIST), error = function(e) NULL)
if (is.null(pg)) {
  cat("  team list itself failed to load\n")
} else {
  Sys.sleep(6)
  report("team list before click", pg)
  sel <- sprintf("a[href='/teams/%s']", team_id)
  found <- length(rvest::html_elements(pg, sel))
  cat("  link present on page:", found, "\n")
  if (found > 0) {
    tryCatch({
      pg$session$Runtime$evaluate(
        expression = sprintf("document.querySelector(\"%s\").click()", sel))
      Sys.sleep(9)
      report("after clicking through", pg)
    }, error = function(e) cat("  click failed:", conditionMessage(e), "\n"))
  }
  try(pg$session$close(), silent = TRUE)
}

cat("\nC  daily scoreboard (would give contest IDs without /teams/)\n")
sb <- paste0("https://stats.ncaa.org/contests/livestream_scoreboards",
             "?utf8=%E2%9C%93&season_division_id=&game_date=",
             utils::URLencode(game_date, reserved = TRUE),
             "&conference_id=0&tournament_id=&commit=Submit")
pg <- tryCatch(read_html_live(sb), error = function(e) NULL)
if (!is.null(pg)) {
  Sys.sleep(8)
  report("livestream_scoreboards", pg)
  nbox <- length(rvest::html_elements(pg, "a[href*='box_score']"))
  ncon <- length(rvest::html_elements(pg, "a[href*='/contests/']"))
  cat("  box_score links:", nbox, " | /contests/ links:", ncon, "\n")
  hrefs <- rvest::html_attr(rvest::html_elements(pg, "a"), "href")
  hrefs <- unique(hrefs[!is.na(hrefs) & grepl("/contests/", hrefs)])
  if (length(hrefs)) print(utils::head(hrefs, 6))
  try(pg$session$close(), silent = TRUE)
}

cat("\nD  older singular /team/<id> URL shape\n")
pg <- tryCatch(read_html_live(paste0("https://stats.ncaa.org/team/", team_id)),
               error = function(e) NULL)
if (!is.null(pg)) { Sys.sleep(6); report("/team/<id>", pg)
                    try(pg$session$close(), silent = TRUE) }

cat("\nAny row showing 'NCAA Statistics' instead of 'Access Denied' is a way in.\n")
