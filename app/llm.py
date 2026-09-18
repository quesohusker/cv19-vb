"""Hand the page to an LLM of the reader's choosing, as one self-describing file.

No API key, no provider, no per-question cost, and nothing here calls anything. The
page packs what it is showing into a single Markdown file -- the explanation up top,
the numbers as CSV below -- and the reader downloads it and uploads it to ChatGPT,
Claude, Gemini or whatever they already pay for.

WHY THIS SHAPE. A rating of 75.3 means nothing to a model that has not been told what
a rating is, and a rank of 256 is actively misleading without the band beside it. So
the context block is not decoration: it is the difference between a model reading the
table and a model inventing volleyball. Every file states what the numbers are, how
they were computed, and what they are known not to measure, so the answer a reader
gets back carries the same caveats the app carries.

Everything exported is this app's own computed output -- ratings, benchmark counts,
rank bands -- not raw NCAA box scores.
"""
from __future__ import annotations

import datetime as _dt

import pandas as pd

HOWTO = (
    "Want to dig deeper? **Download this and upload it to the LLM of your choice** "
    "(ChatGPT, Claude, Gemini…), then ask it questions. It is one self-describing "
    "Markdown file — context up top, the numbers as CSV below. This is the app's own "
    "computed output (ratings, benchmark grades, confidence bands), not raw NCAA box "
    "scores."
)

PREAMBLE = (
    "This file was exported from QuesoHusker's Volleyball, an NCAA women's Division I "
    "analytics app. Everything below is the app's own computed output. Answer only from "
    "what is in this file; if a question cannot be answered from it, say so rather than "
    "filling the gap from memory — these are real athletes and a confident wrong "
    "number about one of them is worse than no answer."
)


def _csv(df: pd.DataFrame, columns: list[str] | None = None, limit: int | None = None) -> str:
    if df is None or len(df) == 0:
        return "(no rows)\n"
    d = df if columns is None else df[[c for c in columns if c in df.columns]]
    note = ""
    if limit is not None and len(d) > limit:
        note = f"\n_First {limit:,} of {len(d):,} rows._\n"
        d = d.head(limit)
    # %.5g, not a fixed decimal count: a kill total should read "11" and a hitting
    # efficiency ".36364", and one format has to serve both in the same table.
    return "```csv\n" + d.to_csv(index=False, float_format="%.5g") + "```\n" + note


def build(title: str, context: str, tables: list[tuple[str, pd.DataFrame, list[str] | None]],
          glossary: dict[str, str] | None = None, limits: list[str] | None = None,
          limit: int | None = None) -> str:
    """Assemble the download: title, how to read it, the caveats, then the numbers."""
    out = [f"# {title}", "", PREAMBLE, "", "## What these numbers are", "", context.strip(), ""]
    if glossary:
        out += ["## Columns", ""]
        out += [f"- `{k}` — {v}" for k, v in glossary.items()]
        out += [""]
    if limits:
        out += ["## Known limits", ""]
        # the source strings come from a JSON note field and a caveat list, which do
        # not agree about capitalisation; a bullet list should
        out += [f"- {x[:1].upper() + x[1:]}" for x in limits if x]
        out += [""]
    for name, df, cols in tables:
        out += [f"## {name}", "", _csv(df, cols, limit), ""]
    out += ["---", f"_Exported {_dt.date.today().isoformat()} from QuesoHusker's "
            f"Volleyball. Source: NCAA women's D1 box scores and play-by-play._"]
    return "\n".join(out)


def slug(*parts: str) -> str:
    s = "_".join(str(p) for p in parts if p)
    keep = [c.lower() if c.isalnum() else "-" for c in s]
    out = "".join(keep)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")
