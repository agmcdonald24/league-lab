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
