"""Render a page's output table to a single dark PNG the reader can post.

WHY THIS EXISTS
---------------
The app already exports every page as Markdown for an LLM to read. This is the other
half of the same idea: a picture of just the numbers, for a forum post or a tweet,
where a CSV is useless and a browser screenshot drags in filters, sliders and
half a sidebar.

It deliberately does NOT screenshot the page. It redraws the table from the same
values the page rendered, which is why no chrome can leak in and why the image looks
identical on every browser and on Streamlit Cloud.

Matplotlib is imported inside the renderer, not at module scope. If it is missing
from the deploy environment the button quietly does not appear, rather than taking
the whole app down at import time.
"""
from __future__ import annotations

import html as _html
import io

import numpy as np
import pandas as pd
import streamlit as st

from app import theme as T

BG = "#0e1117"          # Streamlit's dark canvas, which the app's CSS matches
PANEL = "#161a23"
ROW_ALT = "#12161f"
HEADER = T.ACCENT       # one source of truth for the brand red
TXT = "#e6e6e6"
MUTED = "#9aa0aa"
HL = "#2d3550"          # the compared teams, tinted the way the HTML tables tint them

FOOTER = "QuesoHusker's Volleyball · NCAA women's D1"

# Columns never worth putting in a static image.
_DROP = {"Logo", "logo", "logo_url"}


def plain(s) -> str:
    """The page's cells carry HTML entities; an image needs the characters."""
    if s is None:
        return "—"
    return _html.unescape(str(s)).replace(" ", " ").strip()


def _wrap(s: str, width: int = 12) -> str:
    """Stack a long multi-word header so one wide label cannot stretch the table."""
    s = str(s)
    if len(s) <= width or " " not in s:
        return s
    lines, cur = [], ""
    for w in s.split(" "):
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


@st.cache_data(show_spinner=False)
def _draw(cells, headers, aligns, title, subtitle, highlight_rows, footer):
    """Draw a fully stringified table to PNG bytes.

    Cached on the exact cell content, so a rerun that changes no data is a cache hit
    and nothing is redrawn. The button needs the bytes at render time -- Streamlit
    cannot generate them on click without a second rerun -- so this runs on every
    page load and the cache is what keeps that cheap.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ncol, nrow = len(headers), len(cells)
    wrapped = [_wrap(h) for h in headers]
    widths = []
    for c in range(ncol):
        hmax = max((len(x) for x in wrapped[c].split("\n")), default=1)
        cmax = max((len(cells[r][c]) for r in range(nrow)), default=1) if nrow else 1
        widths.append(max(hmax, cmax) + 1)
    total_w = sum(widths) or 1

    row_h = 0.34
    header_lines = max((h.count("\n") + 1 for h in wrapped), default=1)
    header_h = 0.30 * header_lines + 0.18
    fig_w = max(3.5, min(24.0, total_w * 0.115))
    fig_h = (header_h + nrow * row_h + 0.55
             + (0.55 if title else 0) + (0.3 if footer else 0))

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.axis("off")

    xedges = np.concatenate([[0], np.cumsum(widths)]) / total_w
    top = 1.0
    if title:
        ax.text(0.0, 1.0, title, color=TXT, fontsize=12, fontweight="bold",
                va="top", ha="left", transform=ax.transAxes)
        top = 1.0 - (0.52 / fig_h)
        if subtitle:
            ax.text(0.0, top, subtitle, color=MUTED, fontsize=8.5,
                    va="top", ha="left", transform=ax.transAxes)
            top -= (0.32 / fig_h)

    header_frac = header_h / fig_h
    row_frac = row_h / fig_h

    def _x_ha(c):
        pad = 0.006
        if aligns[c] == "right":
            return xedges[c + 1] - pad, "right"
        return xedges[c] + pad, "left"

    y_top = top
    y_bot = top - header_frac
    ax.add_patch(plt.Rectangle((0, y_bot), 1, header_frac, transform=ax.transAxes,
                               facecolor=HEADER, edgecolor="none", zorder=1))
    for c in range(ncol):
        tx, ha = _x_ha(c)
        ax.text(tx, (y_top + y_bot) / 2, wrapped[c], color="white", fontsize=8.5,
                fontweight="bold", va="center", ha=ha, transform=ax.transAxes, zorder=2)

    hlset = set(highlight_rows or ())
    y = y_bot
    for r in range(nrow):
        yb = y - row_frac
        bg = HL if r in hlset else (ROW_ALT if r % 2 else PANEL)
        ax.add_patch(plt.Rectangle((0, yb), 1, row_frac, transform=ax.transAxes,
                                   facecolor=bg, edgecolor="none", zorder=0))
        for c in range(ncol):
            tx, ha = _x_ha(c)
            ax.text(tx, (y + yb) / 2, cells[r][c], color=TXT, fontsize=8,
                    va="center", ha=ha, transform=ax.transAxes, zorder=2)
        y = yb

    if footer:
        ax.text(0.0, y - 0.012, footer, color=MUTED, fontsize=7.5,
                va="top", ha="left", transform=ax.transAxes)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return buf.getvalue()


def table_bytes(df: pd.DataFrame, *, title=None, subtitle=None,
                highlight_rows=None, footer=FOOTER, max_rows=400) -> bytes:
    """Turn a display frame -- already formatted, as strings -- into image bytes.

    Alignment is decided per column by what is in it: a column whose cells all read
    as numbers is right-aligned, like the HTML tables. Judging it on the frame's
    dtype would left-align every column, since a display frame is all strings.
    """
    df = df.reset_index(drop=True)
    drop = [c for c in df.columns if c in _DROP]
    if drop:
        df = df.drop(columns=drop)
    if max_rows and len(df) > max_rows:
        # Say so on the image. A cropped table that does not admit it is cropped
        # reads as the whole board, and this one gets posted where nobody can see
        # the page it came from.
        note = f"Top {max_rows} of {len(df):,}"
        footer = f"{note} · {footer}" if footer else note
        df = df.head(max_rows)

    cols = list(df.columns)
    cells = tuple(tuple(plain(df.iat[r, c]) for c in range(len(cols)))
                  for r in range(len(df)))

    def numericish(c: int) -> bool:
        """Right-align a column that is mostly numbers, not only entirely numbers.

        A majority rather than a unanimity. The comparison board puts a Yes/No in the
        "Won set 1" row of an otherwise numeric column, and requiring every cell to be
        a number left-aligned the whole column -- so a team's match figure no longer
        lined up with its season figure beside it.
        """
        seen = [cells[r][c] for r in range(len(cells)) if cells[r][c] not in ("", "—")]
        if not seen:
            return False
        n = sum(1 for v in seen
                if v.lstrip("+-").replace(",", "").replace(".", "").replace("%", "")
                    .replace("/", "").replace("–", "").replace(" ", "")
                    .replace("✓", "").replace("✗", "").isdigit())
        return n >= 0.7 * len(seen)

    aligns = tuple("right" if numericish(c) else "left" for c in range(len(cols)))
    return _draw(cells, tuple(plain(c) for c in cols), aligns,
                 title, subtitle, tuple(highlight_rows or ()), footer)


def button(container, df, *, title, filename, key, subtitle=None,
           highlight_rows=None, label="\U0001f5bc️  Download table (PNG)",
           max_rows=400) -> None:
    """Offer the page's table as an image. Never raises.

    An empty frame or a missing matplotlib means no button, not a broken page: a
    picture of the numbers is a convenience, and it should not be able to take down
    the numbers themselves.
    """
    if df is None or not len(df):
        return
    try:
        data = table_bytes(df, title=title, subtitle=subtitle,
                           highlight_rows=highlight_rows, max_rows=max_rows)
    except Exception:
        return
    container.download_button(label, data, file_name=filename, mime="image/png",
                              key=key, use_container_width=False)


def slug(s: str) -> str:
    keep = "".join(c if c.isalnum() else "_" for c in plain(s).lower())
    return "_".join(p for p in keep.split("_") if p)[:80] or "table"
