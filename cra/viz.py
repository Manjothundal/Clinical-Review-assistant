# -*- coding: utf-8 -*-
"""
Charts for the Visualize page. Altair, which ships with Streamlit, so nothing
extra to install.

Colours (checked with a colour-blind validator against the white page):
    Critical #d03b3b   Major #ec835a   Minor #2a78d6
Major sits below 3:1 contrast, so every chart also carries labels and the page
offers each one as a table.
"""
import pandas as pd
import altair as alt

SEV = ["Critical", "Major", "Minor"]
SEV_COL = ["#d03b3b", "#ec835a", "#2a78d6"]
BLUE = "#2a78d6"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95",
       "#0d366b"]
FONT = "system-ui, -apple-system, Segoe UI, sans-serif"


def _theme(chart, height):
    return (chart.properties(height=height, background=SURFACE)
            .configure_view(stroke=None)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=GRID,
                            domainColor="#c3c2b7", tickColor="#c3c2b7",
                            labelFont=FONT, titleFont=FONT, labelFontSize=12,
                            titleFontSize=12, titleFontWeight="normal")
            .configure_legend(labelColor=INK, titleColor=MUTED, labelFont=FONT,
                              titleFont=FONT, orient="top", direction="horizontal",
                              symbolType="square", titleFontWeight="normal")
            .configure_text(font=FONT))


def frame(findings, status_of):
    return pd.DataFrame([{
        "Layer": f.layer, "Severity": f.severity, "Area": f.area,
        "Where": (f.output_file.split(",")[0].split("/")[0].strip()
                  or "(none)"),
        "Status": status_of(f), "Finding": f.finding} for f in findings])


def by_layer(df, layers):
    """Horizontal stacked bars: findings per layer, split by severity."""
    order = [l for l in layers if l in set(df.Layer)]
    totals = df.groupby("Layer").size().reset_index(name="n")
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, stroke=SURFACE,
                                  strokeWidth=2, height={"band": 0.62}).encode(
        y=alt.Y("Layer:N", sort=order, title=None),
        x=alt.X("count():Q", title="Findings", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Severity:N", scale=alt.Scale(domain=SEV, range=SEV_COL),
                        legend=alt.Legend(title=None)),
        order=alt.Order("sev_rank:Q"),
        tooltip=["Layer", "Severity", alt.Tooltip("count():Q", title="Findings")],
    ).transform_calculate(
        sev_rank="indexof(['Critical','Major','Minor'], datum.Severity)")
    labels = alt.Chart(totals).mark_text(align="left", dx=6, color=INK,
                                         fontSize=12).encode(
        y=alt.Y("Layer:N", sort=order), x="n:Q", text="n:Q")
    return _theme(alt.layer(bars, labels), 34 * len(order) + 40)


def heatmap(df, layers):
    """Layer x area: where the problems cluster."""
    t = df.groupby(["Layer", "Area"]).size().reset_index(name="n")
    order = [l for l in layers if l in set(df.Layer)]
    base = alt.Chart(t).encode(
        x=alt.X("Area:N", title=None,
                axis=alt.Axis(labelAngle=-35, labelOverlap=False,
                              labelLimit=120)),
        y=alt.Y("Layer:N", sort=order, title=None))
    cells = base.mark_rect(stroke=SURFACE, strokeWidth=2, cornerRadius=3).encode(
        color=alt.Color("n:Q", scale=alt.Scale(range=SEQ, zero=True),
                        legend=alt.Legend(title="Findings")),
        tooltip=["Layer", "Area", alt.Tooltip("n:Q", title="Findings")])
    text = base.mark_text(fontSize=12).encode(
        text="n:Q",
        color=alt.condition("datum.n > %d" % max(1, t.n.max() // 2),
                            alt.value("#ffffff"), alt.value(INK)))
    return _theme(alt.layer(cells, text), 36 * len(order) + 60)


def top_files(df, n=10):
    t = (df.groupby("Where").size().reset_index(name="n")
         .sort_values("n", ascending=False).head(n))
    base = alt.Chart(t).encode(y=alt.Y("Where:N", sort="-x", title=None))
    bars = base.mark_bar(color=BLUE, cornerRadiusEnd=4,
                         height={"band": 0.62}).encode(
        x=alt.X("n:Q", title="Findings", axis=alt.Axis(tickMinStep=1)),
        tooltip=[alt.Tooltip("Where:N", title="File or dataset"),
                 alt.Tooltip("n:Q", title="Findings")])
    labels = base.mark_text(align="left", dx=6, color=INK).encode(
        x="n:Q", text="n:Q")
    return _theme(alt.layer(bars, labels), 28 * len(t) + 30), t


def simple_bars(t, cat, val, title, sort=None):
    """One series, so one colour and no legend: the title names it."""
    base = alt.Chart(t).encode(y=alt.Y("%s:N" % cat, sort=sort or "-x",
                                       title=None))
    bars = base.mark_bar(color=BLUE, cornerRadiusEnd=4,
                         height={"band": 0.62}).encode(
        x=alt.X("%s:Q" % val, title=title, axis=alt.Axis(tickMinStep=1)),
        tooltip=[cat, alt.Tooltip("%s:Q" % val, title=title)])
    labels = base.mark_text(align="left", dx=6, color=INK).encode(
        x="%s:Q" % val, text="%s:Q" % val)
    return _theme(alt.layer(bars, labels), 30 * len(t) + 30)


def trend(history):
    """Findings per scan, one line per severity."""
    rows = []
    for i, h in enumerate(history):
        for s in SEV:
            rows.append({"Scan": h["at"], "Severity": s,
                         "Findings": sum(v for k, v in h["counts"].items()
                                         if k.endswith("|" + s))})
    t = pd.DataFrame(rows)
    sel = alt.selection_point(nearest=True, on="pointerover", fields=["Scan"],
                              empty=False)
    base = alt.Chart(t).encode(
        x=alt.X("Scan:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Findings:Q", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Severity:N", scale=alt.Scale(domain=SEV, range=SEV_COL),
                        legend=alt.Legend(title=None)))
    lines = base.mark_line(strokeWidth=2)
    points = base.mark_point(size=70, filled=True, stroke=SURFACE,
                             strokeWidth=2).encode(
        tooltip=["Scan", "Severity", "Findings"]).add_params(sel)
    rule = alt.Chart(t).mark_rule(color="#c3c2b7").encode(
        x=alt.X("Scan:N", sort=None)).transform_filter(sel)
    return _theme(alt.layer(lines, points, rule), 260), t
