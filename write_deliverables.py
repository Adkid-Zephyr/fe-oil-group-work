"""Build the coursework report and the five-minute briefing from outputs/summary.json."""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from pptx import Presentation
from pptx.dml.color import RGBColor as PptColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches as PInches, Pt as PPt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
SUMMARY = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))

# Guards so the prose cannot drift away from the estimated numbers.
assert SUMMARY["n_regression"] == 353
assert SUMMARY["n_oos"] == 233
assert SUMMARY["oos_start"] == "2005-02-28"
assert abs(SUMMARY["ols_r2"] - 0.03941) < 1e-4
assert SUMMARY["arima_order"] == {"p": 2, "d": 0, "q": 2}
assert SUMMARY["lasso_nonzero_full"] == 0
by_model = {row["model"]: row for row in SUMMARY["oos_metrics"]}
assert abs(by_model["ols"]["rmse"] - 0.12288) < 1e-4
assert abs(by_model["naive_zero"]["rmse"] - 0.11337) < 1e-4
assert abs(SUMMARY["may2020_share_of_ols_sse"] - 0.2409) < 1e-3
trades = {row["rule"]: row for row in SUMMARY["trading"]}
assert abs(trades["long_short"]["total_return"] - (-0.9378)) < 1e-3


NAVY = RGBColor(0x1F, 0x4E, 0x79)
INK = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x4B, 0x55, 0x63)


def shade(cell, hex_color: str) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def set_run(run, size=11, bold=False, italic=False, color=INK, font="Calibri"):
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = color


def add_text(paragraph, text, **kwargs):
    run = paragraph.add_run(text)
    set_run(run, **kwargs)
    return run


def paragraph(doc, text, style=None, size=11, bold=False, italic=False, color=INK, space_after=8, space_before=0, align="left"):
    p = doc.add_paragraph()
    if style:
        p.style = style
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.line_spacing = 1.12
    p.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }[align]
    add_text(p, text, size=size, bold=bold, italic=italic, color=color)
    return p


def heading(doc, text, level):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        set_run(run, size=16 if level == 1 else 13, bold=True, color=NAVY)
    p.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    p.paragraph_format.space_after = Pt(6)
    return p


def caption(doc, text):
    return paragraph(doc, text, size=9, italic=True, color=MUTED, space_after=10, space_before=2)


def add_table(doc, headers, rows, col_widths):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        add_text(p, h, size=9, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        shade(cell, "1F4E79")
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = table.rows[r + 1].cells[c]
            cell.text = ""
            p = cell.paragraphs[0]
            add_text(p, value, size=9, bold=(c == 0))
            if r % 2 == 1:
                shade(cell, "F4F7FB")
    for row in table.rows:
        for i, w in enumerate(col_widths):
            row.cells[i].width = Inches(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return table


def picture(doc, name, width=6.3):
    doc.add_picture(str(OUT / name), width=Inches(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER


BODY: list[str] = []


def body(doc, text):
    BODY.append(text)
    return paragraph(doc, text, align="justify", space_after=8)


def build_report() -> Path:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.3)
    section.right_margin = Cm(2.3)
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = INK

    prose_path = ROOT / "report_prose.txt"
    paras = [p.strip() for p in prose_path.read_text(encoding="utf-8").split("\n\n") if p.strip()]
    if len(paras) != 26:
        raise RuntimeError(f"Expected 26 prose paragraphs, found {len(paras)}")

    headings_at = {
        0: "Abstract",
        1: "1. Introduction",
        3: "2. Data and frequency",
        6: "3. Methodology",
        10: "4. Diagnostics",
        15: "5. Out-of-sample performance",
        21: "6. Implications for trading",
        25: "7. Conclusion",
    }

    paragraph(doc, "Imperial College Business School", size=11, bold=True, color=NAVY, align="center", space_after=2)
    paragraph(doc, "Autumn 2025 Financial Econometrics", size=11, color=MUTED, align="center", space_after=2)
    paragraph(doc, "Group coursework", size=11, color=MUTED, align="center", space_after=10)
    paragraph(doc, "Forecasting next month's WTI return", size=22, bold=True, color=NAVY, align="center", space_after=4)
    paragraph(
        doc,
        "What month-end data can, and cannot, tell an oil desk",
        size=12,
        italic=True,
        color=MUTED,
        align="center",
        space_after=8,
    )
    paragraph(doc, "Group members: [add names]", size=11, align="center", space_after=12)

    counted = []

    def emit_heading(text):
        heading(doc, text, 1)
        counted.append(text)

    def emit_body(text):
        body(doc, text)
        counted.append(text)

    for i, text in enumerate(paras):
        if i in headings_at:
            emit_heading(headings_at[i])
        emit_body(text)
        if i == 4:
            picture(doc, "fig1_price_and_returns.png")
            caption(doc, "Figure 1. Front-month WTI price and its monthly log return, December 1994 to June 2024. Source: Oil Data.xlsx.")
        if i == 11:
            add_table(
                doc,
                ["Predictor (lagged one month)", "Coefficient", "Newey–West s.e.", "p-value"],
                [
                    ["Constant", "0.004", "0.006", "0.557"],
                    ["Futures basis, (CL1−CL2)/CL1", "−0.648", "0.329", "0.049"],
                    ["Crude inventory growth", "0.050", "0.435", "0.908"],
                    ["US dollar index return", "−0.062", "0.239", "0.795"],
                    ["US industrial production growth", "−0.686", "1.433", "0.632"],
                    ["Baltic Dry Index growth", "0.037", "0.031", "0.222"],
                ],
                [2.7, 1.15, 1.45, 0.9],
            )
            caption(doc, "Table 1. Full-sample OLS, February 1995 to June 2024 (353 months). Newey–West standard errors use four lags. R-squared is 0.039.")
        if i == 14:
            picture(doc, "fig5_recursive_coefficients.png")
            caption(doc, "Figure 2. Expanding-window OLS coefficients. The date is the last month used in that estimate. The industrial-production slope changes sign in spring 2020.")
        if i == 15:
            add_table(
                doc,
                ["Model", "RMSE", "MAE", "Hit rate", "R² vs zero", "R² vs mean"],
                [
                    ["Forecast of zero", "11.34", "7.90", "—", "0", "+0.5%"],
                    ["Historical mean", "11.36", "7.87", "55.4%", "−0.5%", "0"],
                    ["ARIMA(2,0,2)", "11.31", "7.88", "52.4%", "+0.4%", "+0.9%"],
                    ["OLS, five predictors", "12.29", "8.08", "53.6%", "−17.5%", "−16.9%"],
                    ["ARIMAX", "12.24", "8.06", "51.5%", "−16.6%", "−16.1%"],
                    ["LASSO, sixteen predictors", "11.36", "7.87", "55.4%", "−0.5%", "0"],
                    ["Ridge, sixteen predictors", "12.19", "8.12", "55.8%", "−15.6%", "−15.1%"],
                ],
                [2.15, 0.75, 0.7, 0.85, 0.95, 1.0],
            )
            caption(doc, "Table 2. One-step accuracy, February 2005 to June 2024 (233 months). RMSE and MAE are in percentage points of the monthly log return. Each forecast uses only data available at the previous month-end.")
            picture(doc, "fig2_oos_rmse.png")
            caption(doc, "Figure 3. Out-of-sample root-mean-squared error. The axis starts at zero.")
        if i == 21:
            add_table(
                doc,
                ["Rule", "Ann. return", "Ann. vol.", "Sharpe", "Total return", "Max drawdown"],
                [
                    ["Buy and hold", "10.8%", "39.3%", "0.26", "+69%", "−87%"],
                    ["Long / flat", "4.5%", "27.0%", "0.16", "+6%", "−76%"],
                    ["Long / short", "−1.4%", "39.5%", "−0.04", "−94%", "−99%"],
                ],
                [1.3, 1.15, 1.0, 0.8, 1.15, 1.3],
            )
            caption(doc, "Table 3. Illustrative P&L on the spliced CL1 simple return, February 2005 to June 2024. Active rules pay 10 basis points per unit of turnover. Buy-and-hold does not trade.")
        if i == 22:
            picture(doc, "fig3_trading_wealth.png")
            caption(doc, "Figure 4. Growth of one dollar. The long/short path breaks in the spring of 2020.")

    heading(doc, "References", 1)
    for ref in [
        "Campbell, J.Y. and Thompson, S.B. (2008). Predicting excess stock returns out of sample: Can anything beat the historical average? Review of Financial Studies, 21(4), 1509–1531.",
        "Clark, T.E. and West, K.D. (2007). Approximately normal tests for equal predictive accuracy in nested models. Journal of Econometrics, 138(1), 291–311.",
        "Diebold, F.X. and Mariano, R.S. (1995). Comparing predictive accuracy. Journal of Business and Economic Statistics, 13(3), 253–263.",
        "Gorton, G.B., Hayashi, F. and Rouwenhorst, K.G. (2013). The fundamentals of commodity futures returns. Review of Finance, 17(1), 35–105.",
        "Newey, W.K. and West, K.D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. Econometrica, 55(3), 703–708.",
        "Working, H. (1949). The theory of price of storage. American Economic Review, 39(6), 1254–1262.",
    ]:
        paragraph(doc, ref, size=10, space_after=4)

    n_words = len(" ".join(counted).split())
    paragraph(
        doc,
        f"Word count: {n_words} (abstract through conclusion, including headings; excluding tables, figures, captions and references). Forecasts are produced by oil_forecast.py.",
        size=9,
        italic=True,
        color=MUTED,
        space_before=8,
    )
    path = ROOT / "Forecasting_Oil_Returns_Report.docx"
    doc.save(path)
    print(f"Report words: {n_words}")
    print(f"Wrote {path}")
    return path

def add_slide(prs, title, bullets, notes, image=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = PptColor(0xFF, 0xFF, 0xFF)

    bar = slide.shapes.add_shape(1, PInches(0), PInches(0), PInches(0.12), PInches(7.5))
    bar.fill.solid()
    bar.fill.fore_color.rgb = PptColor(0x1F, 0x4E, 0x79)
    bar.line.fill.background()

    box = slide.shapes.add_textbox(PInches(0.45), PInches(0.28), PInches(12.4), PInches(0.7))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = PPt(28)
    p.font.bold = True
    p.font.color.rgb = PptColor(0x1F, 0x4E, 0x79)
    p.font.name = "Calibri"

    text_width = PInches(6.3) if image else PInches(12.2)
    body_box = slide.shapes.add_textbox(PInches(0.45), PInches(1.15), text_width, PInches(5.8))
    btf = body_box.text_frame
    btf.word_wrap = True
    for i, line in enumerate(bullets):
        para = btf.paragraphs[0] if i == 0 else btf.add_paragraph()
        para.text = line
        para.level = 0
        para.font.size = PPt(18)
        para.font.name = "Calibri"
        para.font.color.rgb = PptColor(0x1F, 0x29, 0x37)
        para.space_after = PPt(12)
    if image:
        slide.shapes.add_picture(str(OUT / image), PInches(6.9), PInches(1.25), width=PInches(6.0))
    notes_frame = slide.notes_slide.notes_text_frame
    notes_frame.text = notes
    return slide


def build_presentation() -> Path:
    prs = Presentation()
    prs.slide_width = PInches(13.333)
    prs.slide_height = PInches(7.5)
    prs.core_properties.title = "Forecasting next month's WTI return"
    prs.core_properties.subject = "Autumn 2025 Financial Econometrics briefing"

    add_slide(
        prs,
        "Forecasting next month's WTI return",
        [
            "Briefing for the oil desk",
            "Autumn 2025 Financial Econometrics",
            "Decision: do we have a month-ahead view on front-month WTI?",
            "Answer: no. A forecast of zero is the best simple description of next month.",
        ],
        "Start with the decision. Month-end public data do not justify a view on next month's front-month return. A forecast of zero is more accurate than the regression we can explain. The next five minutes cover the target, whether the model is healthy, the horse race against doing nothing, and the P&L if the desk had traded the sign.",
    )
    add_slide(
        prs,
        "What we forecast, and why it is monthly",
        [
            "Target: next month's log return on CL1, the front-month price.",
            "Not the price level. The level behaves like a random walk, so the forecast would just be last month's price.",
            "Not the calendar spread. That is a roll trade. We use the spread as an input, not as the thing we bet on.",
            "Monthly, and only monthly. Industrial production, the dollar and yields arrive once a month. A daily model would mostly be yesterday's macro number plus noise.",
            "Every input is known at the previous month-end. Nothing from the month being forecast is used.",
        ],
        "The price is what the desk quotes, and it is a poor forecast target. It has a unit root, so a level forecast collapses to the last mark. The return is stationary, and it is what a long or short earns. We stay monthly because industrial production and the dollar arrive monthly. A daily model would mostly repeat a stale macro number. The curve is an input. We do not trade the spread itself.",
    )
    add_slide(
        prs,
        "Five numbers from last month",
        [
            "Curve: is the front month above or below the second month?",
            "Inventories: did US crude stocks build or draw?",
            "Dollar: did the dollar strengthen?",
            "Activity: US industrial production, and the Baltic Dry freight index.",
            "We expected scarcity and strong activity to point to higher oil, and a stronger dollar to point to lower oil.",
            "In the full sample, only the curve is even marginally related to the next return, and the sign is the wrong way round.",
        ],
        "These five were fixed before we saw the out-of-sample scores. Backwardation was supposed to predict higher returns, inventory builds lower returns, a stronger dollar lower oil, and stronger activity higher oil. Four of the five slopes are indistinguishable from zero. The curve slope is negative: backwardation lined up with weaker subsequent returns. A typical move in the curve, about two points, lines up with only one and a half points of return, against an eleven-point monthly move. LASSO was also allowed to use positioning, the VIX, equities and the crack, sixteen variables in all. It kept none.",
    )
    add_slide(
        prs,
        "The model does not stay still",
        [
            "In-sample, the five variables explain about 4 per cent of monthly returns.",
            "Errors are fat-tailed. A normal confidence band would understate crash risk.",
            "The industrial-production coefficient is positive for fifteen years, then flips sign in the spring of 2020.",
            "The same equation would have told you the opposite thing about growth in 2019 and in 2021.",
        ],
        "Four per cent in sample is already a weak relationship, and that fit uses the whole history. The errors have crash risk in them, so we would not quote a tight band around the forecast. The chart is why the growth coefficient cannot be used. It is large and positive until April 2020, then turns negative once the lockdown is in the sample. The full-sample number averages those two regimes. The curve coefficient stays modestly negative throughout. Stable is not the same as useful.",
        image="fig5_recursive_coefficients.png",
    )
    add_slide(
        prs,
        "Out of sample, predicting zero wins",
        [
            "233 months, February 2005 to June 2024. The model is refitted every month on past data only.",
            "Typical error if we predict zero: 11.3 percentage points.",
            "Typical error of our regression: 12.3.",
            "LASSO's error equals the historical average, because it throws every predictor out.",
            "A pure time-series model is a rounding error better than zero. We would not trade it.",
        ],
        "Each bar is the typical monthly mistake, in percentage points. Predicting zero is wrong by about eleven points, which is simply the ordinary size of a monthly oil move. Our regression is worse, at just over twelve. Putting the macro variables into a time-series model makes that model worse too. LASSO matches the historical average because cross-validation set every weight to zero. The only model slightly ahead of zero is an ARIMA in the return itself, by a few hundredths of a point. That gap is not significant, and it gets the sign right less often than always being long. The 55 per cent hit rate of the average is just the share of up months.",
        image="fig2_oos_rmse.png",
    )
    add_slide(
        prs,
        "Trading the sign loses to holding the contract",
        [
            "Long when the forecast is positive, flat or short when it is not. Cost: 10 basis points of turnover.",
            "Buy and hold grows $1 to about $1.69.",
            "Long/flat grows it to $1.06. Long/short leaves about six cents.",
            "March 2020: the model goes long into a minus 54 per cent month.",
            "May 2020: it goes short into a plus 88 per cent month.",
        ],
        "If the forecast could time the market, being long only when it is positive should beat holding the contract. It does not. Buy and hold grows one dollar to about a dollar seventy. Standing aside when the model is negative gives up the drift. Going short destroys the capital. In early 2020 the short made money while oil was falling. In March the model flipped long and the contract fell 54 per cent. In May it forecast another 29 per cent decline and went short into an 88 per cent rally. Ten basis points of cost is not what does the damage. We did not add a cap after seeing this path.",
        image="fig3_trading_wealth.png",
    )
    add_slide(
        prs,
        "What the desk should do",
        [
            "Do not put this regression in the book.",
            "The working assumption for next month's WTI return is zero.",
            "The curve has a small, stable, wrong-signed link with the next return. It is not a signal.",
            "The growth coefficient changes regime. Do not listen to it after the next shock.",
            "A new model has to beat a forecast of zero on a window it has not been fitted to. Beating an in-sample chart is not enough.",
        ],
        "The action is to decline the signal. We do not know the sign of next month. The question you will get is about the curve: it is the only slope that is marginally significant, it does not change sign, and it points the wrong way relative to the scarcity story. Even if that sign is real, it is about one and a half points of return against eleven points of noise, and it did not help out of sample. LASSO and ridge saw a wider set. LASSO kept nothing, and ridge was worse. A more complicated model was not the missing piece. Leave the last minute for questions on 2020 and on the roll inside the CL1 series.",
    )

    path = ROOT / "Forecasting_Oil_Returns_Presentation.pptx"
    prs.save(path)
    print(f"Wrote {path}")
    return path


if __name__ == "__main__":
    build_report()
    build_presentation()
