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
# Usage:  Rscript discover_teams.R <path-to-package-source> [year] [sport]

suppressPackageStartupMessages(library(ncaavolleyballr))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Pass the path to the ncaavolleyballr source tree.")
pkg_dir <- normalizePath(args[1], mustWork = TRUE)
year    <- as.integer(if (length(args) >= 2) args[2] else 2026)
sport   <- if (length(args) >= 3) args[3] else "WVB"

obj  <- if (sport == "MVB") "mvb_teams" else "wvb_teams"
existing <- get(obj, envir = asNamespace("ncaavolleyballr"))

if (any(existing$yr == year)) {
  cat(sprintf("%s already contains %d (%d rows). Nothing to do.\n",
              obj, year, sum(existing$yr == year)))
  quit(status = 0)
}

cat(sprintf("Discovering %d %s teams from stats.ncaa.org ...\n", year, sport))
found <- list()
for (division in 1:3) {
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
save(list = obj, file = file.path(pkg_dir, "data", paste0(obj, ".rda")),
     compress = "bzip2", version = 2)
cat(sprintf("\nWrote %s.rda: %d rows (+%d for %d).\nReinstall the package, then scrape.\n",
            obj, nrow(updated), nrow(new_rows), year))
