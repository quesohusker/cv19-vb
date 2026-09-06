#!/usr/bin/env Rscript
# Discover team IDs for a season the package does not ship yet, and fold them into
# the package's own team table.
#
# The bundled wvb_teams table stops at 2025, and check_sport() reads it through
# ncaavolleyballr::wvb_teams -- the exported binding -- so a runtime override with
# assignInNamespace() does not take. The table has to be rebuilt in the source tree
# and the package reinstalled, which is exactly what the maintainer's own
# data-raw/ncaa.R does each season.
#
# Usage:  Rscript discover_teams.R <path-to-package-source> [year] [sport] [divisions]
#
# `divisions` is a comma-separated list, default "1". Only discover what you intend
# to scrape -- each division walks its conferences with a 5s sleep between each, so
# pulling D2 and D3 you will never use costs real time.

suppressPackageStartupMessages(library(ncaavolleyballr))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Pass the path to the ncaavolleyballr source tree.")
pkg_dir <- normalizePath(args[1], mustWork = TRUE)
year    <- as.integer(if (length(args) >= 2) args[2] else 2026)
sport   <- if (length(args) >= 3) args[3] else "WVB"
divs    <- if (length(args) >= 4) as.integer(strsplit(args[4], ",")[[1]]) else 1L

obj <- if (sport == "MVB") "mvb_teams" else "wvb_teams"
rda <- file.path(pkg_dir, "data", paste0(obj, ".rda"))

# Read the table we are about to modify -- the copy in the source tree -- not the
# installed namespace. They diverge as soon as this script runs once without a
# reinstall, and trusting the namespace makes a re-run silently duplicate rows.
if (file.exists(rda)) {
  e <- new.env()
  load(rda, envir = e)
  existing <- get(obj, envir = e)
} else {
  existing <- get(obj, envir = asNamespace("ncaavolleyballr"))
}

have <- unique(existing$div[existing$yr == year])
if (all(divs %in% have)) {
  cat(sprintf("%s already covers %d for division(s) %s. Nothing to do.\n",
              obj, year, paste(divs, collapse = ", ")))
  quit(status = 0)
}
divs <- setdiff(divs, have)

cat(sprintf("Discovering %d %s teams, division(s) %s, from stats.ncaa.org ...\n",
            year, sport, paste(divs, collapse = ", ")))
found <- list()
for (division in divs) {
  d <- tryCatch(get_teams(year = year, division = division, sport = sport),
                error = function(e) {
                  cat(sprintf("  div %d failed: %s\n", division, conditionMessage(e)))
                  NULL
                })
  if (!is.null(d) && nrow(d) > 0) {
    cat(sprintf("  div %d: %d teams\n", division, nrow(d)))
    found[[length(found) + 1]] <- d
  }
}
if (length(found) == 0) {
  stop("No teams discovered. Either the season is not up on stats.ncaa.org yet, or\n",
       "  the year gate is still 2025 -- check that most_recent_season() was patched.")
}

new_rows <- do.call(rbind, found)
new_rows$team_name <- trimws(new_rows$team_name)
updated <- rbind(existing, new_rows)

# write into the source tree so the reinstall picks it up
assign(obj, updated)
save(list = obj, file = rda, compress = "bzip2", version = 2)
cat(sprintf("\nWrote %s.rda: %d rows (+%d for %d).\nReinstall the package, then scrape.\n",
            obj, nrow(updated), nrow(new_rows), year))
