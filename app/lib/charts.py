"""Plotly helpers following the dataviz method: fixed categorical hue order assigned per
entity (never cycled by rank), 2px lines, >= 8px markers, one y-axis, recessive grid,
legend always present for >= 2 series, hover tooltips on every mark."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL = "Blues"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e8e7e3"
SURFACE = "#fcfcfb"


def color_map(entities: list[str]) -> dict[str, str]:
    """Stable entity -> color assignment (sorted, first 8 slots; extras fold to gray)."""
    ordered = list(dict.fromkeys(entities))
    return {e: (CATEGORICAL[i] if i < len(CATEGORICAL) else "#9a9891") for i, e in enumerate(ordered)}


def base_layout(title: str, y_title: str, x_title: str = "Week") -> dict:
    return dict(
        title=dict(text=title, font=dict(size=15, color=TEXT)),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, size=12),
        margin=dict(l=48, r=16, t=48, b=44),
        xaxis=dict(title=x_title, showgrid=False, zeroline=False, dtick=1),
        yaxis=dict(title=y_title, gridcolor=GRID, zeroline=False),
        legend=dict(orientation="h", y=-0.22, x=0, title=None),
        hovermode="x unified",
        height=380,
    )


def line_chart(df: pd.DataFrame, x: str, y: str, series: str, title: str, y_title: str,
               y_format: str = ".2f", colors: dict[str, str] | None = None) -> go.Figure:
    colors = colors or color_map(sorted(df[series].dropna().unique().tolist()))
    fig = go.Figure()
    for name, part in df.groupby(series, sort=True):
        part = part.sort_values(x)
        fig.add_trace(go.Scatter(
            x=part[x], y=part[y], mode="lines+markers", name=str(name),
            line=dict(width=2, color=colors.get(name, "#9a9891")),
            marker=dict(size=8, color=colors.get(name, "#9a9891"), line=dict(width=2, color=SURFACE)),
            hovertemplate=f"%{{y:{y_format}}}<extra>{name}</extra>", connectgaps=False,
        ))
    fig.update_layout(**base_layout(title, y_title))
    if y_format.endswith("%"):
        fig.update_yaxes(tickformat=".0%")
    if len(df[series].unique()) == 1:
        fig.update_layout(showlegend=False)
    return fig


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, y_title: str, series: str | None = None,
              y_format: str = ".2f", colors: dict[str, str] | None = None, horizontal: bool = False,
              x_title: str = "Week") -> go.Figure:
    fig = go.Figure()
    if series:
        colors = colors or color_map(sorted(df[series].dropna().unique().tolist()))
        for name, part in df.groupby(series, sort=True):
            fig.add_trace(go.Bar(
                x=part[y] if horizontal else part[x], y=part[x] if horizontal else part[y], name=str(name),
                orientation="h" if horizontal else "v",
                marker=dict(color=colors.get(name, "#9a9891"), line=dict(width=2, color=SURFACE)),
                hovertemplate=f"%{{{'x' if horizontal else 'y'}:{y_format}}}<extra>{name}</extra>",
            ))
        fig.update_layout(barmode="group")
    else:
        fig.add_trace(go.Bar(
            x=df[y] if horizontal else df[x], y=df[x] if horizontal else df[y],
            orientation="h" if horizontal else "v",
            marker=dict(color=CATEGORICAL[0], line=dict(width=2, color=SURFACE)),
            hovertemplate=f"%{{{'x' if horizontal else 'y'}:{y_format}}}<extra></extra>",
        ))
    layout = base_layout(title, y_title, x_title="" if horizontal else x_title)
    if horizontal:
        layout["xaxis"] = dict(title=y_title, gridcolor=GRID, zeroline=False)
        layout["yaxis"] = dict(title="", showgrid=False, autorange="reversed")
        layout["hovermode"] = "closest"
    fig.update_layout(**layout)
    if not series:
        fig.update_layout(showlegend=False)
    return fig


def _mix(c1: str, c2: str, t: float) -> str:
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    r, g, bl = (round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return f"#{r:02x}{g:02x}{bl:02x}"


def heat_style(df: pd.DataFrame, low_is_strong: bool = True, fmt: str = "{:.0f}"):
    """A sequential single-hue background (light -> dark blue) for a numeric table, no matplotlib.
    Dark = strong. With low_is_strong=True a rank of 1 is darkest. Text stays in text tokens."""
    df = df.apply(pd.to_numeric, errors="coerce")
    values = df.stack().dropna()
    lo, hi = (values.min(), values.max()) if not values.empty else (0, 1)

    def shade(v):
        if pd.isna(v) or hi == lo:
            return ""
        t = (float(v) - lo) / (hi - lo)
        if low_is_strong:
            t = 1 - t
        color = _mix("#eef4fb", "#2a78d6", t)
        return f"background-color: {color}; color: {'#ffffff' if t > 0.6 else TEXT}"

    return df.style.map(shade).format(fmt, na_rep="—")


# ---- C5 (R-15): defense vs position as a picture ---------------------------------------------------------
def dvp_bars(sel: pd.DataFrame, value: str, title: str, x_title: str, league_avg: float | None = None,
             rank_col: str = "rank", n_total: int | None = None) -> go.Figure:
    """Ranked horizontal bars of points allowed per game (most first) for the rows `lib.matchups.dvp_selection`
    picked: the defenses your players face this week solid and labelled in bold with ◀ (never color alone), the
    rest lighter; a gap row "⋯ N more" where defenses are skipped; a hairline at the league average. One hue,
    no drag / zoom (a phone scrolls past it), a hover on every bar."""
    labels, xs, colors, hover = [], [], [], []
    gap_no = 0
    for r in sel.itertuples(index=False):
        if int(getattr(r, "gap_before", 0) or 0) > 0:
            gap_no += 1
            labels.append("⋯ " + f"{int(r.gap_before)} more" + "​" * gap_no)   # unique category per gap
            xs.append(None)
            colors.append(SURFACE)
            hover.append(f"{int(r.gap_before)} defenses in between (the full list is below)")
        mine = bool(getattr(r, "is_mine", False))
        labels.append(f"<b>{r.defense} ◀</b>" if mine else str(r.defense))
        v = pd.to_numeric(getattr(r, value), errors="coerce")
        xs.append(None if pd.isna(v) else float(v))
        colors.append(CATEGORICAL[0] if mine else "rgba(42,120,214,0.40)")
        rank = getattr(r, rank_col, None)
        of = f" of {n_total}" if n_total else ""
        facing = getattr(r, "facing", "") or ""
        hover.append(f"{r.defense}: {float(v):.1f} per game" + (f", #{int(rank)}{of}" if rank is not None and pd.notna(rank) else "")
                     + (f"<br>your {facing}" if facing else ""))
    # direct labels only on your opponents' bars, with the rank (the rest stay in the hover and the table)
    ranks = []
    for r in sel.itertuples(index=False):
        if int(getattr(r, "gap_before", 0) or 0) > 0:
            ranks.append(None)
        rk = getattr(r, rank_col, None)
        ranks.append(int(rk) if rk is not None and pd.notna(rk) else None)
    text = []
    for lab, x, rk in zip(labels, xs, ranks, strict=True):
        text.append((f"{x:.1f}" + (f" · #{rk}" if rk is not None else "")) if x is not None and "◀" in lab else "")
    fig = go.Figure(go.Bar(
        x=xs, y=labels, orientation="h", marker=dict(color=colors, line=dict(width=2, color=SURFACE)),
        # the label sits inside a long bar (white on the solid fill) and outside a short one, clear of the average line
        text=text, textposition="auto", insidetextanchor="end", insidetextfont=dict(size=11, color="#ffffff"),
        outsidetextfont=dict(size=11, color=TEXT), cliponaxis=False,
        customdata=hover, hovertemplate="%{customdata}<extra></extra>",
    ))
    if league_avg is not None and pd.notna(league_avg):
        fig.add_vline(x=float(league_avg), line=dict(color=TEXT_SECONDARY, width=1))
        fig.add_annotation(x=float(league_avg), y=1.0, yref="paper", yanchor="bottom", text="league average",
                           showarrow=False, font=dict(size=11, color=TEXT_SECONDARY))
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=TEXT)), paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, size=12), margin=dict(l=8, r=12, t=56, b=40), showlegend=False,
        height=100 + 24 * len(labels), dragmode=False, hovermode="closest", bargap=0.25,
        xaxis=dict(title=x_title, gridcolor=GRID, zeroline=False, fixedrange=True),
        yaxis=dict(title="", showgrid=False, autorange="reversed", automargin=True, fixedrange=True,
                   categoryorder="array", categoryarray=labels),
    )
    return fig


# ---- C5 (R-15): defense vs position as a heatmap (every defense x every position the league starts) -------
HEAT_RAMP = ["#0d366b", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"]   # sequential blue 700 -> 100: dark = gives up more


def dvp_heatmap(frame: pd.DataFrame, positions: list[str], title: str, n_total: int = 32) -> go.Figure:
    """Defense x position cells (the rows `lib.matchups.dvp_heat_frame` ordered: your opponents pinned first).
    Color = the defense's rank against the position (one blue ramp, darker = gives up more, so positions with
    different point scales compare), the number in the cell = points allowed per game; your starter's cell is
    ringed and his opponent's row label carries ◀ in bold (never color alone); a 2px surface gap between cells,
    a hover on every cell, a scale legend below, no drag / zoom (a phone scrolls past it)."""
    ys = [f"<b>{r.defense} ◀</b>" if r.is_mine else str(r.defense) for r in frame.itertuples(index=False)]
    z, text, hover = [], [], []
    for r in frame.itertuples(index=False):
        rz, rt, rh = [], [], []
        for p in positions:
            v, k = getattr(r, p, None), getattr(r, f"{p}_rank", None)
            ok = v is not None and pd.notna(v) and k is not None and pd.notna(k)
            rz.append(float(k) if ok else None)
            rt.append(f"{float(v):.1f}" if ok else "")
            mine = [s.split(" (")[0] for s in str(r.facing or "").split("; ") if s.endswith(f"({p})")]
            rh.append((f"{r.defense} vs {p}s: {float(v):.1f} points a game, #{int(k)} of {n_total}" if ok else f"{r.defense} vs {p}s: no games")
                      + (f"<br>your {', '.join(mine)}" if mine else ""))
        z.append(rz)
        text.append(rt)
        hover.append(rh)
    scale = [[i / (len(HEAT_RAMP) - 1), c] for i, c in enumerate(HEAT_RAMP)]
    fig = go.Figure(go.Heatmap(
        z=z, x=positions, y=ys, colorscale=scale, zmin=1, zmax=max(n_total, 2), xgap=2, ygap=2,
        customdata=hover, hovertemplate="%{customdata}<extra></extra>",
        colorbar=dict(orientation="h", thickness=10, len=1.0, x=0.5, xanchor="center", y=0, yanchor="top",
                      yref="paper", ypad=0, showticklabels=False, ticks="", outlinewidth=0),
    ))
    # the scale's two ends in words, inside the plot's width (tick labels at the ends would be clipped)
    for x, anchor, words in ((0, "left", "#1 = gives up the most"), (1, "right", f"#{n_total} = the fewest")):
        fig.add_annotation(x=x, xref="paper", xanchor=anchor, y=0, yref="paper", yanchor="top", yshift=-14,
                           text=words, showarrow=False, font=dict(size=11, color=TEXT_SECONDARY))
    # the number in each cell, in text ink that reads on its fill (white on the dark end of the ramp)
    for i, (row_z, row_t) in enumerate(zip(z, text, strict=True)):
        for j, (k, t) in enumerate(zip(row_z, row_t, strict=True)):
            if not t:
                continue
            dark = (k - 1) / max(n_total - 1, 1) < 0.4
            fig.add_annotation(x=positions[j], y=ys[i], text=t, showarrow=False,
                               font=dict(size=12, color="#ffffff" if dark else TEXT))
    # ring the cells where one of your starters plays: the defense he faces, at his position
    for i, r in enumerate(frame.itertuples(index=False)):
        for j, p in enumerate(positions):
            if str(r.facing or "") and any(s.endswith(f"({p})") for s in str(r.facing).split("; ")):
                fig.add_shape(type="rect", x0=j - 0.47, x1=j + 0.47, y0=i - 0.45, y1=i + 0.45, xref="x", yref="y",
                              line=dict(color=TEXT, width=2.5), fillcolor="rgba(0,0,0,0)")
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=TEXT)), paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, size=12), margin=dict(l=8, r=8, t=64, b=64),
        height=160 + 28 * len(ys), dragmode=False, hovermode="closest",
        xaxis=dict(side="top", showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=12, color=TEXT)),
        yaxis=dict(autorange="reversed", showgrid=False, zeroline=False, fixedrange=True, automargin=True,
                   categoryorder="array", categoryarray=ys, tickfont=dict(size=12)),
    )
    return fig
