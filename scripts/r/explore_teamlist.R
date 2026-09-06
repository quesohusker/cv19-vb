#!/usr/bin/env Rscript
# Dump the structure of the NCAA team-list page so a parser can be written
# against what is actually there, rather than guessed at.
#
# get_teams() assumes this page carries a conference menu of
# javascript:changeConference(<id>) links, and fetches each conference in turn.
# That assumption has now failed twice. This prints what the page really
# contains: its tables, its links, and whether the conference menu exists at all.
#
# Usage:  Rscript explore_teamlist.R [year] [division] [sport]

suppressPackageStartupMessages(library(rvest))

args     <- commandArgs(trailingOnly = TRUE)
year     <- as.integer(if (length(args) >= 1) args[1] else 2026)
division <- as.integer(if (length(args) >= 2) args[2] else 1)
sport    <- if (length(args) >= 3) args[3] else "WVB"

# use the same browser transport the scraper uses
shim <- file.path(dirname(dirname(normalizePath(
  sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1]),
  mustWork = FALSE))), "chrome-shim.sh")
if (!nzchar(Sys.getenv("VB_NO_SHIM")) && file.exists(shim)) {
  Sys.setenv(CHROMOTE_CHROME = shim)
}
options(chromote.timeout = as.numeric(Sys.getenv("VB_CHROMOTE_TIMEOUT", "60")))

url <- sprintf(paste0("http://stats.ncaa.org/team/inst_team_list",
                      "?academic_year=%d&conf_id=-1&division=%d&sport_code=%s"),
               year + 1, division, sport)
cat("URL:", url, "\n\n")

pg <- tryCatch(rvest::read_html_live(url),
               error = function(e) { cat("FAILED:", conditionMessage(e), "\n"); NULL })
if (is.null(pg)) quit(status = 1)
Sys.sleep(4)

cat("=== title ===\n"); print(rvest::html_text(rvest::html_element(pg, "title")))

html <- as.character(rvest::html_element(pg, "body"))
cat("\n=== body size ===\n"); cat(nchar(html), "chars\n")

cat("\n=== does the conference menu exist at all? ===\n")
cat("  'changeConference' appears:", lengths(regmatches(html, gregexpr("changeConference", html))), "times\n")
cat("  'conf_id' appears:", lengths(regmatches(html, gregexpr("conf_id", html))), "times\n")
cat("  '.level2' elements:", length(rvest::html_elements(pg, ".level2")), "\n")

cat("\n=== tables ===\n")
tabs <- rvest::html_elements(pg, "table")
cat("count:", length(tabs), "\n")
for (i in seq_along(tabs)) {
  t <- tryCatch(rvest::html_table(tabs[[i]]), error = function(e) NULL)
  if (is.null(t) || nrow(t) == 0) next
  cat(sprintf("\n--- table %d: %d rows x %d cols ---\n", i, nrow(t), ncol(t)))
  cat("columns:", paste(names(t), collapse = " | "), "\n")
  print(utils::head(t, 6))
}

cat("\n=== links inside tables (this is where teams live) ===\n")
ta <- rvest::html_elements(pg, "table a")
cat("count:", length(ta), "\n")
if (length(ta)) {
  d <- data.frame(text = trimws(rvest::html_text(ta)),
                  href = rvest::html_attr(ta, "href"))
  print(utils::head(d, 10), right = FALSE)
}

cat("\n=== distinct href shapes on the page ===\n")
allh <- rvest::html_attr(rvest::html_elements(pg, "a"), "href")
allh <- allh[!is.na(allh)]
shapes <- gsub("[0-9]+", "<n>", allh)
print(utils::head(sort(table(shapes), decreasing = TRUE), 12))

try(pg$session$close(), silent = TRUE)
