#!/usr/bin/env Rscript
# Reconnaissance on the NCAA's Nitty Gritty / selection-ranking reports.
#
# stats.ncaa.org/selection_rankings/nitty_gritties is the selection committee's own
# RPI report -- RPI rank and value, record, top-25 and top-50 wins, conference and
# non-conference splits, strength of schedule, home/away/neutral splits. It sits on
# stats.ncaa.org, which 403s plain HTTP but yields to headless Chrome, so the same
# transport the scraper already uses works here.
#
# This does not parse anything. It dumps enough structure to write a parser against,
# because the report IDs are a global space across all sports and cannot be guessed.
#
# Usage:  Rscript explore_nitty.R [report_id]

suppressPackageStartupMessages({
  library(rvest)
})

INDEX <- "https://stats.ncaa.org/selection_rankings/nitty_gritties"
args <- commandArgs(trailingOnly = TRUE)
report_id <- if (length(args) >= 1) args[1] else NA_character_

fetch <- function(url) {
  cat("fetching:", url, "\n")
  pg <- tryCatch(rvest::read_html_live(url),
                 error = function(e) { cat("  FAILED:", conditionMessage(e), "\n"); NULL })
  if (is.null(pg)) return(NULL)
  Sys.sleep(3)
  pg
}

if (is.na(report_id)) {
  pg <- fetch(INDEX)
  if (is.null(pg)) quit(status = 1)

  cat("\n=== page title ===\n")
  print(rvest::html_text(rvest::html_element(pg, "title")))

  links <- rvest::html_elements(pg, "a")
  href <- rvest::html_attr(links, "href")
  text <- trimws(rvest::html_text(links))
  keep <- !is.na(href) & grepl("nitty", href, ignore.case = TRUE)
  cat(sprintf("\n=== %d links mentioning 'nitty' ===\n", sum(keep)))
  df <- data.frame(text = text[keep], href = href[keep])
  print(utils::head(df, 40), right = FALSE)

  vb <- df[grepl("volley", df$text, ignore.case = TRUE), ]
  cat(sprintf("\n=== %d of those mention volleyball ===\n", nrow(vb)))
  if (nrow(vb)) print(vb, right = FALSE)

  cat("\n=== tables on the index page ===\n")
  tabs <- rvest::html_elements(pg, "table")
  cat("count:", length(tabs), "\n")
  if (length(tabs)) {
    t1 <- rvest::html_table(tabs[[1]])
    cat("first table:", nrow(t1), "rows x", ncol(t1), "cols\n")
    print(utils::head(t1, 8))
  }
  cat("\nNext: pick a women's volleyball id and re-run:\n")
  cat("  Rscript scripts/r/explore_nitty.R <id>\n")
  try(pg$session$close(), silent = TRUE)
  quit(status = 0)
}

url <- paste0("https://stats.ncaa.org/selection_rankings/nitty_gritties/", report_id)
pg <- fetch(url)
if (is.null(pg)) quit(status = 1)

cat("\n=== page title ===\n")
print(rvest::html_text(rvest::html_element(pg, "title")))

tabs <- rvest::html_elements(pg, "table")
cat("\n=== tables:", length(tabs), "===\n")
for (i in seq_along(tabs)) {
  t <- tryCatch(rvest::html_table(tabs[[i]]), error = function(e) NULL)
  if (is.null(t) || nrow(t) == 0) next
  cat(sprintf("\n--- table %d: %d rows x %d cols ---\n", i, nrow(t), ncol(t)))
  cat("columns:", paste(names(t), collapse = " | "), "\n")
  print(utils::head(t, 5))
  if (nrow(t) > 40) cat("  (this looks like the team table)\n")
}
try(pg$session$close(), silent = TRUE)
