# Every href shape the recon dump reported on the live page.
href <- c(
  "javascript:changeConference(-1);",                    # "All Confs" -- must NOT match
  sprintf("javascript:changeConference(%d);", c(1,32,865,10001)),
  sprintf("javascript:changeYears(%d);", c(1,2027)),
  sprintf("javascript:changeDivisions(%d);", 1:3),
  sprintf("/teams/%d", c(624921, 624953, 624514)),
  "/rankings", "/head_coaches", "/search/players",
  "/selection_rankings/nitty_gritties", "/active_career_leaders",
  "/contests/livestream_scoreboards", "/", "#"
)

keep <- grepl("changeConference\\(\\d+\\)", href)
ids  <- regmatches(href[keep], regexpr("\\d+", href[keep]))
cat("conference hrefs matched:", sum(keep), "(expect 4)\n")
cat("  ids:", paste(ids, collapse = ", "), "\n")
cat("  changeConference(-1) excluded:",
    !grepl("changeConference\\(\\d+\\)", "javascript:changeConference(-1);"), "\n")
cat("  changeYears/changeDivisions excluded:",
    !any(grepl("changeYears|changeDivisions", href[keep])), "\n")

tk <- grepl("^/teams/[0-9]+$", href)
cat("team hrefs matched:", sum(tk), "(expect 3)\n")
cat("  nav links excluded:", !any(grepl("rankings|coaches|players", href[tk])), "\n")

stopifnot(sum(keep) == 4, identical(ids, c("1","32","865","10001")), sum(tk) == 3)
cat("\nALL ASSERTIONS PASSED\n")
