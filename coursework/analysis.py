"""
Forecast the weekly CL2-CL1 crude calendar spread.

Source of the task: the coursework brief.
Source of every number: data/raw/Oil Data.xlsx only.
    Industry_D   CL1, CL2, and the crack, on the session used for that Friday.
    Industry_W   weekly production, rigs, stock change, and positions.
    Macro_M      yields, VIX, the dollar, industrial production.
    StockPrices_M  gasoline. Used only in the ridge and LASSO comparisons.

The definitions sheet says the contract is daily, industry data are weekly,
and macro data are monthly, over December 1994 to June 2024. The panel is
every Friday in that window. CL1 and CL2 are taken from the last daily
session on or before that Friday.

Choices fixed before the holdout is scored
    Spread      S = CL2 - CL1. Positive means contango.
    Target      next Friday's change in S, in $/bbl.
    Frequency   weekly.
    Model       OLS of the change on three regressors:
                    this Friday's spread,
                    last week's crude-stock change,
                    last week's change in the rig count.
    Holdout     target Fridays from 4 January 2019 through 28 June 2024.
                A forecast uses only earlier Fridays.
    Comparisons ARIMA; ARIMAX with the stock and rig regressors;
                ridge and LASSO on a wider set. The monthly yields,
                VIX, dollar, industrial production and gasoline enter
                that wider set as the last month already published.
                These comparisons do not replace the three-variable OLS.
    Trade       take the sign of the OLS forecast when its absolute value
                is at least $0.05; otherwise stay flat.

Run from the repository root:

    python coursework/analysis.py
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from sklearn.linear_model import LassoCV, Ridge
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.diagnostic import (
    acorr_breusch_godfrey,
    acorr_ljungbox,
    breaks_cusumolsresid,
    het_breuschpagan,
)
from statsmodels.stats.stattools import durbin_watson
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller, kpss

warnings.filterwarnings("ignore")

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "raw" / "Oil Data.xlsx").exists())
RAW = REPO / "data" / "raw" / "Oil Data.xlsx"
OUT = REPO / "data" / "results" / "coursework"
OUT.mkdir(parents=True, exist_ok=True)

WINDOW_START = pd.Timestamp("1994-12-30")  # first Friday of the definitions window
WINDOW_END = pd.Timestamp("2024-06-28")  # last Friday of June 2024
HOLDOUT_START = pd.Timestamp("2019-01-04")  # first target Friday of 2019
TRADE_THRESHOLD = 0.05
RIDGE_ALPHA = 10.0
OLS_COLS = ["spread", "stock_change", "rig_change"]
WIDE_COLS = [
    "spread", "stock_change", "rig_change", "production_change",
    "position_change", "crack_change", "vix_change", "ip_growth",
    "dollar_return", "gasoline_change", "yield_curve_change",
]


def read_sheet(name: str) -> pd.DataFrame:
    frame = pd.read_excel(RAW, sheet_name=name)
    frame.columns = [str(c).strip() for c in frame.columns]
    if "Date" not in frame.columns:
        raise RuntimeError(f"{name} has no Date column.")
    return frame


def build() -> tuple[pd.DataFrame, dict]:
    if RAW.name != "Oil Data.xlsx" or RAW.parent.name != "raw":
        raise RuntimeError(f"Refusing to read anything other than data/raw/Oil Data.xlsx, got {RAW}")

    weekly = read_sheet("Industry_W")
    daily = read_sheet("Industry_D")
    macro = read_sheet("Macro_M")
    stocks = read_sheet("StockPrices_M")

    weekly["Date"] = pd.to_datetime(weekly["Date"])
    weekly = weekly.dropna(subset=["Date"]).sort_values("Date")
    if not (weekly["Date"].dt.day_name() == "Friday").all():
        raise RuntimeError("Industry_W is not a Friday sheet.")
    if not (weekly["Date"].diff().dt.days.dropna() == 7).all():
        raise RuntimeError("Industry_W is not a continuous set of Fridays.")

    daily["Date"] = pd.to_datetime(daily["Date"])
    n_undated = int(daily["Date"].isna().sum())
    daily = daily.dropna(subset=["Date"]).sort_values("Date")
    prices = daily[["Date", "CL1", "CL2", "CRKS321C Index"]].rename(columns={"Date": "price_date"})

    panel = weekly[(weekly["Date"] >= WINDOW_START) & (weekly["Date"] <= WINDOW_END)].copy()
    panel = pd.merge_asof(panel, prices, left_on="Date", right_on="price_date", direction="backward")
    panel["price_lag_days"] = (panel["Date"] - panel["price_date"]).dt.days
    if panel["price_lag_days"].max() > 4:
        raise RuntimeError("A Friday has no crude print within four days.")
    if panel["CL1"].isna().any() or panel["CL2"].isna().any():
        raise RuntimeError("A Friday in the window has no CL1 or CL2.")

    panel["spread"] = panel["CL2"] - panel["CL1"]
    panel["change"] = panel["spread"].shift(-1) - panel["spread"]
    panel["target_date"] = panel["Date"].shift(-1)

    # The stock column is already the week's change. Rigs and production are
    # levels. All three are lagged one week: the sheet dates the week the
    # number describes, and the stock release comes out after that Friday.
    panel["stock_change"] = panel["Weekly change in Crude Stock"].shift(1)
    panel["rig_change"] = panel["Weekly Rig Count"].diff().shift(1)
    panel["production_change"] = panel["Weekly Prod Crude"].diff().shift(1)
    panel["position_change"] = (
        panel["Weekly Commercial Long"] - panel["Weekly Commercial Short"]
    ).diff().shift(1)
    panel["crack_change"] = panel["CRKS321C Index"].diff()

    macro["Date"] = pd.to_datetime(macro["Date"])
    stocks["Date"] = pd.to_datetime(stocks["Date"])
    macro = macro.dropna(subset=["Date"]).sort_values("Date")
    stocks = stocks.dropna(subset=["Date"]).sort_values("Date")
    macro["month"] = macro["Date"].dt.to_period("M")
    stocks["month"] = stocks["Date"].dt.to_period("M")
    macro = macro.merge(stocks.drop(columns=["Date"]), on="month", how="left")
    # Market rates are known at the month-end date. Industrial production and
    # gasoline are dated on the month they describe, so the row carries the
    # previous month's change, which has been released.
    macro["yield_curve_change"] = (macro["10Y Yield"] - macro["3M Yield"]).diff()
    macro["vix_change"] = macro["VIX"].diff()
    macro["dollar_return"] = 100 * macro["DXY returns"]
    macro["ip_growth"] = (100 * macro["IndustrialProduction Index"].pct_change()).shift(1)
    macro["gasoline_change"] = macro["Gasoline All Grades"].diff().shift(1)
    carried = macro[
        ["Date", "yield_curve_change", "vix_change", "dollar_return", "ip_growth", "gasoline_change"]
    ].rename(columns={"Date": "macro_date"})
    panel = pd.merge_asof(panel, carried, left_on="Date", right_on="macro_date", direction="backward")

    provenance = {
        "file": "data/raw/Oil Data.xlsx",
        "resolved_path": str(RAW.resolve()),
        "spread_from": "Industry_D columns CL1 and CL2",
        "industry_from": "Industry_W",
        "macro_from": "Macro_M, last month-end on or before the Friday",
        "gasoline_from": "StockPrices_M, previous month's change",
        "window": [str(WINDOW_START.date()), str(WINDOW_END.date())],
        "fridays": int(len(panel)),
        "fridays_using_an_earlier_session": int((panel["price_lag_days"] > 0).sum()),
        "max_price_lag_days": int(panel["price_lag_days"].max()),
        "daily_rows_without_a_date": n_undated,
    }
    panel[
        ["Date", "price_date", "price_lag_days", "target_date", "CL1", "CL2", "spread", "change"]
    ].to_csv(OUT / "weekly_panel_head.csv", index=False)
    return panel.reset_index(drop=True), provenance


def adf_kpss(series: pd.Series, regression: str) -> dict:
    sample = series.replace([np.inf, -np.inf], np.nan).dropna()
    adf_stat, adf_p, usedlag, nobs, crit, _ = adfuller(sample, maxlag=12, autolag="AIC", regression=regression)
    kpss_stat, kpss_p, _, kpss_crit = kpss(sample, regression=regression, nlags="auto")
    return {
        "n": int(nobs),
        "adf_stat": float(adf_stat),
        "adf_p": float(adf_p),
        "adf_lags": int(usedlag),
        "adf_5pct": float(crit["5%"]),
        "kpss_stat": float(kpss_stat),
        "kpss_p": float(kpss_p),
        "kpss_5pct": float(kpss_crit["5%"]),
    }


def stationarity(data: pd.DataFrame) -> pd.DataFrame:
    early = data[data["target_date"] < HOLDOUT_START]
    rows = []
    for name, series, regression in [
        ("CL1", early["CL1"], "ct"),
        ("CL2", early["CL2"], "ct"),
        ("spread CL2-CL1", early["spread"], "c"),
        ("change in the spread", early["change"], "c"),
        ("stock change, lagged", early["stock_change"], "c"),
        ("rig change, lagged", early["rig_change"], "c"),
        ("yield-curve change, carried month", early["yield_curve_change"], "c"),
    ]:
        row = adf_kpss(series, regression)
        row["series"] = name
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "stationarity.csv", index=False)
    return table


def diagnostics(data: pd.DataFrame) -> dict:
    sample = (
        data[(data["target_date"] < HOLDOUT_START) & data["change"].notna()]
        .dropna(subset=OLS_COLS)
        .copy()
    )
    y = sample["change"].to_numpy(dtype=float)
    X = sm.add_constant(sample[OLS_COLS].to_numpy(dtype=float))
    ols = sm.OLS(y, X).fit()
    nw_lags = int(np.floor(4 * (len(sample) / 100) ** (2 / 9)))
    hac = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": nw_lags})
    bg = acorr_breusch_godfrey(ols, nlags=4)
    lb = acorr_ljungbox(ols.resid, lags=[1, 4, 12], model_df=0)
    bp = het_breuschpagan(ols.resid, ols.model.exog)
    names = ["intercept", *OLS_COLS]
    pd.DataFrame({
        "term": names,
        "estimate": hac.params,
        "hac_se": hac.bse,
        "hac_t": hac.tvalues,
        "hac_p": hac.pvalues,
    }).to_csv(OUT / "coefficients.csv", index=False)

    mid = len(sample) // 2

    def ssr(a, b):
        beta, *_ = np.linalg.lstsq(X[a:b], y[a:b], rcond=None)
        return float(np.sum((y[a:b] - X[a:b] @ beta) ** 2))

    full, left, right = ssr(0, len(y)), ssr(0, mid), ssr(mid, len(y))
    k = X.shape[1]
    chow = ((full - left - right) / k) / ((left + right) / (len(y) - 2 * k))
    chow_p = float(1 - stats.f.cdf(chow, k, len(y) - 2 * k))
    break_week = str(sample["target_date"].iloc[mid].date())
    cusum_stat, cusum_p, _ = breaks_cusumolsresid(ols.resid)
    pd.DataFrame([
        {"test": "Durbin-Watson", "stat": float(durbin_watson(ols.resid)), "p_value": np.nan},
        {"test": "Breusch-Godfrey, 4 lags", "stat": float(bg[0]), "p_value": float(bg[1])},
        {"test": "Ljung-Box lag 1", "stat": float(lb["lb_stat"].iloc[0]), "p_value": float(lb["lb_pvalue"].iloc[0])},
        {"test": "Ljung-Box lag 4", "stat": float(lb["lb_stat"].iloc[1]), "p_value": float(lb["lb_pvalue"].iloc[1])},
        {"test": "Ljung-Box lag 12", "stat": float(lb["lb_stat"].iloc[2]), "p_value": float(lb["lb_pvalue"].iloc[2])},
        {"test": "Breusch-Pagan", "stat": float(bp[0]), "p_value": float(bp[1])},
        {"test": f"Chow break at target week {break_week}", "stat": float(chow), "p_value": chow_p},
        {"test": "CUSUM", "stat": float(cusum_stat), "p_value": float(cusum_p)},
    ]).to_csv(OUT / "diagnostics.csv", index=False)
    plot_fit(sample, ols)
    plot_stability(sample)
    return {
        "n": int(ols.nobs),
        "r_squared": float(ols.rsquared),
        "adj_r_squared": float(ols.rsquared_adj),
        "from": str(sample["target_date"].iloc[0].date()),
        "to": str(sample["target_date"].iloc[-1].date()),
        "nw_lags": nw_lags,
        "coefficients": {name: float(est) for name, est in zip(names, hac.params)},
        "hac_se": {name: float(se) for name, se in zip(names, hac.bse)},
        "hac_t": {name: float(t) for name, t in zip(names, hac.tvalues)},
        "hac_p": {name: float(p) for name, p in zip(names, hac.pvalues)},
        "dw": float(durbin_watson(ols.resid)),
        "bg_p": float(bg[1]),
        "lb1_p": float(lb["lb_pvalue"].iloc[0]),
        "lb4_p": float(lb["lb_pvalue"].iloc[1]),
        "lb12_p": float(lb["lb_pvalue"].iloc[2]),
        "bp_p": float(bp[1]),
        "chow_break": break_week,
        "chow_p": chow_p,
        "cusum_stat": float(cusum_stat),
        "cusum_p": float(cusum_p),
    }


def select_arima(spread: np.ndarray) -> tuple[int, int, int]:
    adf_p = adfuller(spread, maxlag=12, autolag="AIC", regression="c")[1]
    d = 0 if adf_p < 0.05 else 1
    best, best_aic = (0, d, 0), np.inf
    rows = []
    for p in range(3):
        for q in range(3):
            try:
                fit = ARIMA(spread, order=(p, d, q), trend="c" if d == 0 else "n").fit()
            except Exception:
                continue
            rows.append({"p": p, "d": d, "q": q, "aic": float(fit.aic)})
            if fit.aic < best_aic:
                best, best_aic = (p, d, q), float(fit.aic)
    pd.DataFrame(rows).sort_values("aic").to_csv(OUT / "arima_orders.csv", index=False)
    return best


def arimax_order(spread: np.ndarray, exog: np.ndarray, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    mask = np.isfinite(exog).all(axis=1) & np.isfinite(spread)
    d = fallback[1]
    best, best_aic = fallback, np.inf
    rows = []
    for p in range(3):
        for q in range(3):
            try:
                fit = ARIMA(
                    spread[mask], order=(p, d, q), exog=exog[mask], trend="c" if d == 0 else "n"
                ).fit()
            except Exception:
                continue
            rows.append({"p": p, "d": d, "q": q, "aic": float(fit.aic)})
            if fit.aic < best_aic:
                best, best_aic = (p, d, q), float(fit.aic)
    if rows:
        pd.DataFrame(rows).sort_values("aic").to_csv(OUT / "arimax_orders.csv", index=False)
    return best


def forecast(data: pd.DataFrame, order: tuple[int, int, int]) -> pd.DataFrame:
    # The reported regression keeps every Friday that has the spread, the stock
    # change and the rig change. Ridge and LASSO also need the monthly series,
    # which are missing on seven Fridays in January and February 1995.
    usable = data.dropna(subset=["change", *OLS_COLS]).reset_index(drop=True)
    wide_ok = usable[WIDE_COLS].notna().all(axis=1).to_numpy()
    hold = np.where(usable["target_date"].to_numpy() >= np.datetime64(HOLDOUT_START))[0]
    if len(hold) == 0 or hold[0] < 80:
        raise RuntimeError("The holdout does not leave enough history to estimate.")
    if not bool(wide_ok[hold].all()):
        raise RuntimeError("A holdout week is missing a comparison regressor.")
    spread = usable["spread"].to_numpy(dtype=float)
    y = usable["change"].to_numpy(dtype=float)
    stock = usable["stock_change"].to_numpy(dtype=float)
    rig = usable["rig_change"].to_numpy(dtype=float)
    exog_at = np.column_stack([np.r_[np.nan, stock[:-1]], np.r_[np.nan, rig[:-1]]])
    x_order = arimax_order(spread[: hold[0] + 1], exog_at[: hold[0] + 1], order)
    lasso_kept: dict[str, float] = {}
    rows = []
    for i in hold:
        y_train, spread_now = y[:i], spread[i]

        def ols_hat(columns: list[str]) -> float:
            design = sm.add_constant(usable.loc[: i - 1, columns].to_numpy(dtype=float))
            beta, *_ = np.linalg.lstsq(design, y_train, rcond=None)
            x = np.r_[1.0, usable.loc[i, columns].to_numpy(dtype=float)]
            return float(x @ beta)

        past_idx = np.flatnonzero(wide_ok[:i])
        if len(past_idx) < 80:
            raise RuntimeError("Not enough complete weeks for ridge and LASSO.")
        scaler = StandardScaler()
        X_past = scaler.fit_transform(usable.iloc[past_idx][WIDE_COLS].to_numpy(dtype=float))
        x_now = scaler.transform(usable.loc[i, WIDE_COLS].to_numpy(dtype=float).reshape(1, -1))
        ridge = Ridge(alpha=RIDGE_ALPHA).fit(X_past, y[past_idx])
        lasso = LassoCV(cv=5, random_state=0, max_iter=20000).fit(X_past, y[past_idx])
        if i == hold[0]:
            lasso_kept = {name: float(coef) for name, coef in zip(WIDE_COLS, lasso.coef_) if coef != 0}
            pd.DataFrame({"variable": WIDE_COLS, "coefficient": lasso.coef_}).to_csv(
                OUT / "lasso_coefficients.csv", index=False
            )

        trend = "c" if order[1] == 0 else "n"
        arma = ARIMA(spread[: i + 1], order=order, trend=trend).fit()
        arma_hat = float(np.asarray(arma.forecast(1))[0]) - spread_now
        x_trend = "c" if x_order[1] == 0 else "n"
        arimax = ARIMA(spread[1 : i + 1], order=x_order, exog=exog_at[1 : i + 1], trend=x_trend).fit()
        next_exog = np.array([[stock[i], rig[i]]])
        arimax_hat = float(np.asarray(arimax.forecast(1, exog=next_exog))[0]) - spread_now
        rows.append({
            "target_date": str(usable.at[i, "target_date"].date()),
            "origin_date": str(usable.at[i, "Date"].date()),
            "spread": spread_now,
            "actual_change": y[i],
            "no_change": 0.0,
            "ols": ols_hat(OLS_COLS),
            "spread_only": ols_hat(["spread"]),
            "arima": arma_hat,
            "arimax": arimax_hat,
            "ridge": float(ridge.predict(x_now)[0]),
            "lasso": float(lasso.predict(x_now)[0]),
        })
    forecasts = pd.DataFrame(rows)
    forecasts.to_csv(OUT / "forecasts.csv", index=False)
    forecasts.attrs["arimax_order"] = list(x_order)
    forecasts.attrs["lasso_kept"] = lasso_kept
    return forecasts


def rmse(error: np.ndarray) -> float:
    return float(np.sqrt(np.mean(error ** 2)))


def score(forecasts: pd.DataFrame) -> pd.DataFrame:
    y = forecasts["actual_change"].to_numpy()
    naive = forecasts["no_change"].to_numpy()
    rows = []
    for column, name in [
        ("no_change", "No change"),
        ("ols", "OLS: spread, stocks, rigs"),
        ("spread_only", "OLS: spread only"),
        ("arima", "ARIMA"),
        ("arimax", "ARIMAX: stocks and rigs"),
        ("ridge", "Ridge, wider set"),
        ("lasso", "LASSO, wider set"),
    ]:
        error = y - forecasts[column].to_numpy()
        row = {"model": name, "n": int(len(y)), "rmse": rmse(error), "mae": float(np.mean(np.abs(error)))}
        if column != "no_change":
            row["oos_r2_vs_no_change"] = float(1 - np.sum(error ** 2) / np.sum((y - naive) ** 2))
            called = forecasts[column].to_numpy() != 0
            row["direction_hit_rate"] = float(np.mean(np.sign(forecasts.loc[called, column]) == np.sign(y[called])))
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "metrics.csv", index=False)
    return table


def trading(forecasts: pd.DataFrame) -> dict:
    frame = forecasts.copy()
    frame["position"] = np.sign(frame["ols"])
    frame.loc[frame["ols"].abs() < TRADE_THRESHOLD, "position"] = 0.0
    frame["pnl"] = frame["position"] * frame["actual_change"]
    traded = frame["position"] != 0
    summary = {
        "threshold": TRADE_THRESHOLD,
        "weeks": int(len(frame)),
        "weeks_traded": int(traded.sum()),
        "hit_rate_when_traded": float(np.mean(
            np.sign(frame.loc[traded, "actual_change"]) == frame.loc[traded, "position"]
        )),
        "cumulative_pnl": float(frame["pnl"].sum()),
        "mean_pnl_per_week": float(frame["pnl"].mean()),
    }
    frame[["target_date", "ols", "actual_change", "position", "pnl"]].to_csv(OUT / "trading.csv", index=False)
    return summary


def style() -> None:
    plt.rcParams.update({
        "figure.figsize": (10.2, 4.8),
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
    })


def plot_spread(data: pd.DataFrame) -> None:
    style()
    fig, ax = plt.subplots()
    ax.plot(data["Date"], data["spread"], color="#1f4e79", lw=1.0, label="CL2 − CL1")
    ax.axvline(HOLDOUT_START, color="#c47b00", ls="--", lw=1, label="Holdout targets start")
    ax.axhline(0, color="#888888", lw=0.6)
    ax.set_ylabel("$/bbl")
    ax.set_title("Calendar spread, Friday")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "spread.png", dpi=160)
    plt.close(fig)


def plot_fit(sample: pd.DataFrame, ols) -> None:
    style()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    sm.graphics.tsa.plot_acf(ols.resid, lags=24, ax=axes[0], zero=False)
    axes[0].set_title("Residual autocorrelation, fit through 2018")
    axes[0].set_xlabel("Lag, weeks")
    axes[1].scatter(ols.fittedvalues, sample["change"], s=12, color="#1f4e79", alpha=0.7)
    limits = [min(ols.fittedvalues.min(), sample["change"].min()), max(ols.fittedvalues.max(), sample["change"].max())]
    axes[1].plot(limits, limits, color="#c47b00", lw=1)
    axes[1].set_title("Fitted change against the outcome, through 2018")
    axes[1].set_xlabel("Fitted change, $/bbl")
    axes[1].set_ylabel("Actual change, $/bbl")
    fig.tight_layout()
    fig.savefig(OUT / "fit.png", dpi=160)
    plt.close(fig)


def plot_stability(sample: pd.DataFrame) -> None:
    slopes, weeks = [], []
    for t in range(150, len(sample) + 1):
        beta, *_ = np.linalg.lstsq(
            sm.add_constant(sample.iloc[:t][OLS_COLS].to_numpy(dtype=float)),
            sample.iloc[:t]["change"].to_numpy(dtype=float),
            rcond=None,
        )
        slopes.append(float(beta[1]))
        weeks.append(sample["target_date"].iloc[t - 1])
    style()
    fig, ax = plt.subplots()
    ax.plot(weeks, slopes, color="#1f4e79", lw=1.2)
    ax.axhline(slopes[-1], color="#c47b00", ls="--", lw=1, label="Full-sample slope")
    ax.set_title("Recursive slope on this Friday's spread, through 2018")
    ax.set_ylabel("Coefficient")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "stability.png", dpi=160)
    plt.close(fig)


def plot_errors(forecasts: pd.DataFrame) -> None:
    style()
    date = pd.to_datetime(forecasts["target_date"])
    actual = forecasts["actual_change"].to_numpy()
    fig, ax = plt.subplots()
    for column, label, color in [
        ("no_change", "No change", "#888888"),
        ("ols", "OLS with stocks and rigs", "#1f4e79"),
        ("arima", "ARIMA", "#c47b00"),
        ("arimax", "ARIMAX", "#2a9d8f"),
        ("lasso", "LASSO", "#9b2226"),
    ]:
        ax.plot(date, np.cumsum((actual - forecasts[column].to_numpy()) ** 2), label=label, color=color, lw=1.3)
    ax.set_title("Cumulative squared error, 2019–2024")
    ax.set_ylabel("($/bbl)²")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "cumulative_error.png", dpi=160)
    plt.close(fig)

    frame = forecasts.copy()
    frame["position"] = np.where(frame["ols"].abs() >= TRADE_THRESHOLD, np.sign(frame["ols"]), 0.0)
    fig, ax = plt.subplots()
    ax.plot(date, (frame["position"] * frame["actual_change"]).cumsum(), color="#1f4e79")
    ax.axhline(0, color="#888888", lw=0.6)
    ax.set_title("Spread score when the forecast is at least 5 cents")
    ax.set_ylabel("Cumulative change, $/bbl")
    fig.tight_layout()
    fig.savefig(OUT / "trading.png", dpi=160)
    plt.close(fig)


def main() -> None:
    data, provenance = build()
    plot_spread(data)
    stationarity_table = stationarity(data)
    diag = diagnostics(data)
    history = data.loc[(data["target_date"] < HOLDOUT_START) & data["spread"].notna(), "spread"].to_numpy()
    order = select_arima(history)
    forecasts = forecast(data, order)
    metrics = score(forecasts)
    trade = trading(forecasts)
    plot_errors(forecasts)
    biggest = forecasts.loc[forecasts["actual_change"].abs().idxmax()]
    summary = {
        "source": provenance,
        "spread": "CL2 - CL1",
        "frequency": "weekly",
        "holdout": [forecasts["target_date"].iloc[0], forecasts["target_date"].iloc[-1]],
        "n_holdout": int(len(forecasts)),
        "arima_order": list(order),
        "arimax_order": forecasts.attrs["arimax_order"],
        "lasso_nonzero_at_2018": forecasts.attrs["lasso_kept"],
        "diagnostics": diag,
        "stationarity": stationarity_table.to_dict(orient="records"),
        "metrics": metrics.to_dict(orient="records"),
        "trading": trade,
        "largest_holdout_move": {
            "target_date": biggest["target_date"],
            "spread": float(biggest["spread"]),
            "ols": float(biggest["ols"]),
            "actual_change": float(biggest["actual_change"]),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    import importlib.util
    slides = importlib.util.spec_from_file_location("build_briefing", Path(__file__).with_name("build_briefing.py"))
    module = importlib.util.module_from_spec(slides)
    slides.loader.exec_module(module)
    module.build_briefing()
    print("source", provenance["resolved_path"])
    print("ARIMA order", order)
    print(stationarity_table.to_string(index=False))
    print(metrics.to_string(index=False))
    print("trade", trade)
    print("coefficients", diag["coefficients"])
    print("p-values", diag["hac_p"])
    print("largest move", summary["largest_holdout_move"])
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
