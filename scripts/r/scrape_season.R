#!/usr/bin/env Rscript
# Scrape one NCAA volleyball season into the CSV shape this project's pipeline reads.
#
# Chunked and resumable on purpose. The maintainer of ncaavolleyballr notes that
# "the NCAA is making it very difficult to scrape lots of data at once" -- they could
# not finish D2/D3 for 2025. A single division_stats() call over ~340 teams that dies
# at team 300 loses everything, so this walks teams in chunks and checkpoints each one.
# Re-run it after a failure and it picks up where it stopped.
#
# Usage:  Rscript scrape_season.R [year] [division] [sport] [outdir] [delay] [chunk] [limit]
#
# `limit` caps how many teams are scraped -- use it for a smoke test before an
# hours-long run, to confirm the season's columns match what the pipeline expects.

suppressPackageStartupMessages({
  library(ncaavolleyballr)
})

args     <- commandArgs(trailingOnly = TRUE)
year     <- as.integer(if (length(args) >= 1) args[1] else 2026)
division <- as.integer(if (length(args) >= 2) args[2] else 1)
sport    <- if (length(args) >= 3) args[3] else "WVB"
outdir   <- if (length(args) >= 4) args[4] else "data/ncaavolleyballr/data-csv"
delay    <- as.numeric(if (length(args) >= 5) args[5] else 3)
chunk_sz <- as.integer(if (length(args) >= 6) args[6] else 10)
limit    <- if (length(args) >= 7) as.integer(args[7]) else NA_integer_

ckpt_dir <- file.path(outdir, "..", "checkpoints", paste0(tolower(sport), "_", year))
dir.create(outdir,   recursive = TRUE, showWarnings = FALSE)
dir.create(ckpt_dir, recursive = TRUE, showWarnings = FALSE)

# Levels worth scraping, most valuable first. teammatch and pbp alone are enough to
# light up the whole app; the other two only add player-level views.
LEVELS <- c("teammatch", "pbp", "teamseason", "playermatch")

teams <- ncaavolleyballr::wvb_teams
if (sport == "MVB") teams <- ncaavolleyballr::mvb_teams
teams <- teams[teams$yr == year & teams$div == division, ]
if (nrow(teams) == 0) {
  stop(sprintf(
    "No %s teams found for %d division %d. Run the discovery stage first -- the\n  bundled team table has no IDs for this season yet.", sport, year, division))
}
team_names <- sort(unique(trimws(teams$team_name)))
if (!is.na(limit) && limit < length(team_names)) {
  team_names <- team_names[seq_len(limit)]
  cat(sprintf("SMOKE TEST: limited to %d teams. Output is partial -- do not feed it\n",
              limit),
      "  to the pipeline; re-run without a limit for the real scrape.\n", sep = "")
  ckpt_dir <- file.path(ckpt_dir, sprintf("smoke%d", limit))
  dir.create(ckpt_dir, recursive = TRUE, showWarnings = FALSE)
}
chunks <- split(team_names, ceiling(seq_along(team_names) / chunk_sz))
cat(sprintf("%d teams in %d chunks of up to %d, delay %.1fs\n",
            length(team_names), length(chunks), chunk_sz, delay))

scrape_level <- function(level) {
  cat(sprintf("\n=== %s ===\n", level))
  parts <- vector("list", length(chunks))
  for (i in seq_along(chunks)) {
    f <- file.path(ckpt_dir, sprintf("%s_chunk%03d.rds", level, i))
    if (file.exists(f)) {                      # resume: already done
      parts[[i]] <- readRDS(f)
      cat(sprintf("  [%d/%d] cached\n", i, length(chunks)))
      next
    }
    cat(sprintf("  [%d/%d] %s ... ", i, length(chunks), chunks[[i]][1]))
    res <- tryCatch(
      group_stats(teams = chunks[[i]], year = year, level = level,
                  sport = sport, delay = delay),
      error = function(e) {
        cat(sprintf("FAILED (%s)\n", conditionMessage(e)))
        NULL
      })
    if (is.null(res)) next                      # leave uncached so a re-run retries it
    saveRDS(res, f)
    parts[[i]] <- res
    cat("ok\n")
  }
  parts[!vapply(parts, is.null, logical(1))]
}

# teamseason returns a list(playerdata, teamdata); every other level a data frame.
combine <- function(parts, level) {
  if (length(parts) == 0) return(NULL)
  if (level == "teamseason") {
    list(playerseason = do.call(rbind, lapply(parts, `[[`, "playerdata")),
         teamseason   = do.call(rbind, lapply(parts, `[[`, "teamdata")))
  } else {
    stats::setNames(list(do.call(rbind, parts)), level)
  }
}

# Filename must match what the Python pipeline reads:
#   {sport}_{label}_div{division}_{year}.csv  e.g. wvb_teammatch_div1_2026.csv
write_out <- function(df, label) {
  if (is.null(df) || nrow(df) == 0) {
    cat(sprintf("  %-12s no rows, skipped\n", label)); return(invisible())
  }
  path <- file.path(outdir, sprintf("%s_%s_div%d_%d.csv",
                                    tolower(sport), label, division, year))
  utils::write.csv(df, path, row.names = FALSE)
  cat(sprintf("  %-12s %7d rows -> %s\n", label, nrow(df), path))
}

for (level in LEVELS) {
  out <- combine(scrape_level(level), level)
  if (is.null(out)) next
  for (label in names(out)) write_out(out[[label]], label)
}

cat("\nDone. Checkpoints kept in", ckpt_dir,
    "\nDelete them only once the CSVs look right.\n")
