"""Five-minute slides for the CL2-CL1 briefing. Reads the saved results."""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "raw" / "Oil Data.xlsx").exists())
OUT = REPO / "data" / "results" / "coursework"
DECK = REPO / "coursework" / "briefing.pptx"

NAVY = RGBColor(0x1F, 0x4E, 0x79)
INK = RGBColor(0x1C, 0x1C, 0x1C)
MUTED = RGBColor(0x5C, 0x65, 0x70)
PAPER = RGBColor(0xF6, 0xF4, 0xEF)


def _run(paragraph, text, size, bold=False, color=INK, font="Calibri"):
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return run


def _box(slide, left, top, width, height):
    shape = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    shape.text_frame.word_wrap = True
    shape.text_frame.auto_size = None
    return shape.text_frame


def _bar(slide, prs):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.08))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()


def _notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def _picture(slide, name, left, top, width):
    slide.shapes.add_picture(str(OUT / name), Inches(left), Inches(top), width=Inches(width))


def build_briefing() -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "Next week's CL2 − CL1"
    blank = prs.slide_layouts[6]
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    trade = summary["trading"]
    diag = summary["diagnostics"]
    slope = diag["coefficients"]["spread"]
    cents = abs(slope) * 100
    r2 = diag["r_squared"] * 100

    def rmse(name: str) -> float:
        for row in summary["metrics"]:
            if row["model"] == name:
                return row["rmse"]
        raise KeyError(name)

    shock = summary["largest_holdout_move"]

    # 1. The question
    s = prs.slides.add_slide(blank)
    _bar(s, prs)
    tf = _box(s, 0.55, 0.35, 6.2, 1.3)
    _run(tf.paragraphs[0], "Next week's CL2 − CL1", 32, True, NAVY)
    p = tf.add_paragraph()
    _run(p, "A five-minute briefing. Two speakers.", 16, color=MUTED)
    tf = _box(s, 0.55, 2.0, 6.1, 4.6)
    lines = [
        "The decision is the curve, not the flat price.",
        "S = CL2 − CL1. Positive means contango.",
        "We forecast next Friday's change in S, in $/bbl.",
        "Weekly. Fit through 2018. Scored on 2019–June 2024.",
        "What survives is mean reversion in the spread.",
    ]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(14)
        _run(p, line, 20)
    _picture(s, "spread.png", 6.9, 1.7, 6.0)
    _notes(s, (
        "Speaker one, about 40 seconds. We are not calling the flat price. "
        "The brief names the CL2 minus CL1 spread, and that is the series. "
        "Positive is contango. We forecast how many dollars that gap moves by next Friday. "
        "The chart is the Friday spread. Prices come from the daily sheet in Oil Data.xlsx, "
        "matched to each Friday. The dashed line is where the holdout starts."
    ))

    # 2. Frequency
    s = prs.slides.add_slide(blank)
    _bar(s, prs)
    tf = _box(s, 0.55, 0.32, 12, 0.7)
    _run(tf.paragraphs[0], "One frequency: weekly", 32, True, NAVY)
    cards = [
        ("Daily", "CL1 and CL2 live here.\n534 rows have no date.\nA Friday with no print uses the previous session.\nMacro is not daily."),
        ("Weekly", "Every Friday, no gaps.\nStocks, rigs, production, positions.\nThe spread is joined from the daily sheet.\nThis is the frequency we use."),
        ("Monthly", "Yields, VIX, the dollar: last published month-end.\nOutput and gasoline: the previous month.\nUsed only in LASSO and ridge."),
    ]
    for i, (title, body) in enumerate(cards):
        left = 0.5 + i * 4.2
        card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1.5), Inches(3.95), Inches(4.6))
        card.fill.solid()
        card.fill.fore_color.rgb = PAPER
        card.line.fill.background()
        tf = _box(s, left + 0.25, 1.75, 3.45, 0.7)
        _run(tf.paragraphs[0], title, 26, True, NAVY if i == 1 else INK)
        tf = _box(s, left + 0.25, 2.6, 3.45, 3.1)
        first = True
        for line in body.split("\n"):
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.space_after = Pt(10)
            _run(p, line, 16)
    _notes(s, (
        "Speaker one, about 50 seconds. The weekly sheet is every Friday and it has the stocks and the rigs, "
        "but it does not have CL1 or CL2. Those come from the daily sheet in the same workbook, "
        "the last session on or before that Friday. Monthly yields stay in the comparison models only, "
        "and only after the month has been published."
    ))

    # 3. The model
    s = prs.slides.add_slide(blank)
    _bar(s, prs)
    tf = _box(s, 0.55, 0.28, 12, 0.6)
    _run(tf.paragraphs[0], "Mean reversion, plus a stock effect", 28, True, NAVY)
    tf = _box(s, 0.55, 1.15, 6.3, 5.6)
    points = [
        f"Slope on the spread: {slope:.2f}. About {cents:.0f} cents of pullback per extra dollar.",
        f"Stocks: p = {diag['hac_p']['stock_change']:.2f}. Rigs: p = {diag['hac_p']['rig_change']:.2f}.",
        f"About {r2:.0f}% of the weekly move. The rest is news.",
        "The 3-month and 10-year yields went into LASSO and ridge, as the last published month's change in the slope.",
        "Those monthly series do not replace the Friday regression.",
        "The slope is re-estimated on lengthening windows through 2018.",
    ]
    for i, line in enumerate(points):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(12)
        _run(p, line, 18)
    _picture(s, "stability.png", 6.9, 1.35, 6.0)
    _notes(s, (
        f"Speaker two, about 70 seconds. The slope on this Friday's spread is {slope:.2f}, "
        "about 13 cents of pullback per extra dollar. The fitted equation settles near 20 cents of contango. "
        "A one-standard-deviation stock build on the estimation sample, about 4,030, lines up with about 3.1 cents. "
        "Stocks and rigs are the weekly industry series, lagged one week. "
        "Interest rates are monthly in the file. They enter LASSO and ridge only after that month is published. "
        "The chart is the recursive slope on the estimation sample. "
        f"Chow split at the target week {diag['chow_break']}, p = {diag['chow_p']:.2f}. "
        f"CUSUM p = {diag['cusum_p']:.2f}."
    ))

    # 4. Holdout
    s = prs.slides.add_slide(blank)
    _bar(s, prs)
    tf = _box(s, 0.55, 0.28, 12, 0.6)
    _run(tf.paragraphs[0], "2019–2024, scored once", 32, True, NAVY)
    tf = _box(s, 0.55, 1.05, 6.2, 5.8)
    points = [
        f"No change: RMSE ${rmse('No change'):.2f}.",
        f"OLS: RMSE ${rmse('OLS: spread, stocks, rigs'):.2f}.",
        f"ARIMA: RMSE ${rmse('ARIMA'):.2f}.",
        f"ARIMAX with stocks and rigs: ${rmse('ARIMAX: stocks and rigs'):.2f}.",
        f"LASSO, including the yield curve: ${rmse('LASSO, wider set'):.2f}.",
        f"Largest week, {shock['target_date']}: forecast ${shock['ols']:.2f}, actual ${shock['actual_change']:.2f}.",
    ]
    for i, line in enumerate(points):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(12)
        _run(p, line, 18)
    _picture(s, "cumulative_error.png", 6.85, 1.25, 6.1)
    _notes(s, (
        "Speaker two, about 70 seconds. Lower on the chart is better. "
        "Read the RMSE lines against a forecast of no change. "
        "The ARIMA is a model of the spread, not of the regression residuals. "
        "The last line is the largest weekly move in the holdout, which is the shock the regression does not see in advance."
    ))

    # 5. The desk
    s = prs.slides.add_slide(blank)
    _bar(s, prs)
    tf = _box(s, 0.55, 0.28, 12, 0.6)
    _run(tf.paragraphs[0], "What a desk could do with it", 32, True, NAVY)
    tf = _box(s, 0.55, 1.1, 6.2, 5.5)
    hit = f"{trade['hit_rate_when_traded'] * 100:.0f}%"
    pnl = f"+${trade['cumulative_pnl']:.2f}"
    points = [
        "Trade only if the forecast is at least 5 cents.",
        f"{trade['weeks_traded']} of {trade['weeks']} weeks traded. Direction right in {hit} of those.",
        f"Cumulative spread points: {pnl} per barrel, before rolls and the bid–ask.",
        "This is not a return on capital. The front contract still expires.",
        "Use it to lean against a curve that is already far from flat.",
        "Do not use it to see the next shock.",
    ]
    for i, line in enumerate(points):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(12)
        _run(p, line, 18)
    _picture(s, "trading.png", 6.9, 1.45, 6.0)
    _notes(s, (
        "Speaker two, about 50 seconds, then questions. "
        "The rule was written before we looked at 2019. "
        "The score is dollars per barrel of the Friday spread, before any roll or bid-ask. "
        "The rest of the group takes the questions. "
        "If asked why inventories are still in the regression: they were in the specification, "
        "and the result is that they do not help. If asked about interest rates: they were in the LASSO and the ridge, and neither beat the short model."
    ))

    prs.save(DECK)
    return DECK


if __name__ == "__main__":
    print(build_briefing())
