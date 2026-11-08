"""
Monthly forecast of front-month WTI futures returns (CL1).

The script builds a common monthly dataset, tests stationarity, estimates a
small predictive regression and three comparisons (ARIMA, LASSO, Ridge),
and evaluates one-step-ahead forecasts against two naive benchmarks.
Only information known at the previous month-end is used as a predictor.

Run from this folder:
    python oil_forecast.py

The expanding-window ARIMA and LASSO fits take about ten minutes.
A later run can reload the saved forecasts with:
    python oil_forecast.py --reuse
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LassoCV, RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.diagnostic import (
    acorr_breusch_godfrey,
    breaks_cusumolsresid,
    het_breuschpagan,
)
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson, jarque_bera
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller, kpss

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "Oil Data.xlsx"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

# First forecast is formed only after this many usable months.
MIN_TRAIN = 120
HAC_LAGS = 4
# Round-trip cost applied to turnover in the trading rule, in return units.
COST = 0.001

PRIMARY = ["basis_l1", "inv_g_l1", "dxy_l1", "ip_g_l1", "bdi_g_l1"]
WIDE = PRIMARY + [
    "ret_l1",
    "rig_g_l1",
    "prod_g_l1",
    "crack_d_l1",
    "slope_d_l1",
    "vix_d_l1",
    "spx_l1",
    "cpi_d_l1",
    "net_spec_d_l1",
    "gas_l1",
    "oil_eq_l1",
]

PRETTY = {
    "basis_l1": "Futures basis (CL1-CL2)/CL1",
    "inv_g_l1": "Crude inventory growth",
    "dxy_l1": "US dollar index return",
    "ip_g_l1": "US industrial production growth",
    "bdi_g_l1": "Baltic Dry Index growth",
    "ret_l1": "Lagged CL1 log return",
    "rig_g_l1": "Rig-count growth",
    "prod_g_l1": "US crude production growth",
    "crack_d_l1": "Change in 3-2-1 crack spread",
    "slope_d_l1": "Change in 10Y-3M Treasury slope",
    "vix_d_l1": "Change in VIX",
    "spx_l1": "S&P 500 log return",
    "cpi_d_l1": "Change in CPI inflation",
    "net_spec_d_l1": "Change in commercial net positioning",
    "gas_l1": "US gasoline price growth",
    "oil_eq_l1": "DJ US Oil & Gas log return",
}


def load_sheet(name: str) -> pd.DataFrame:
    df = pd.read_excel(DATA, sheet_name=name)
    df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"])
    df["month"] = df["Date"].dt.to_period("M")
    df = df.dropna(subset=["month"]).sort_values("month")
    df = df.drop_duplicates("month", keep="last")
    return df.set_index("month")


def build_panel() -> pd.DataFrame:
    ind = load_sheet("Industry_M")
    mac = load_sheet("Macro_M")
    stk = load_sheet("StockPrices_M")

    df = pd.DataFrame(index=ind.index)
    df["cl1"] = ind["CL1"].astype(float)
    df["cl2"] = ind["CL2"].astype(float)
    df["crack"] = ind["CRKS321C Index"].astype(float)
    df["bdi"] = ind["Baltic Dry Index"].astype(float)
    df["prod"] = ind["Daily Production"].astype(float)
    df["inv"] = ind["Inventories"].astype(float)
    df["rigs"] = ind["Rig Count"].astype(float)
    df["comm_long"] = ind["Commercial Long"].astype(float)
    df["comm_short"] = ind["Commercial Short"].astype(float)
    df["oi"] = ind["Total Open Interest"].astype(float)

    mac = mac.reindex(df.index)
    stk = stk.reindex(df.index)
    df["cpi"] = mac["CPI YOY %"].astype(float)
    df["y3m"] = mac["3M Yield"].astype(float)
    df["y10"] = mac["10Y Yield"].astype(float)
    df["ip"] = mac["IndustrialProduction Index"].astype(float)
    df["spx"] = mac["SPX"].astype(float)
    df["dxy"] = mac["DXY returns"].astype(float)
    df["vix"] = mac["VIX"].astype(float)
    df["gasoline"] = stk["Gasoline All Grades"].astype(float)
    df["oil_eq"] = stk["Dow Jones US Oil&Gas Index"].astype(float)

    # Targets. Log return over the month ending on the row date.
    if (df["cl1"] <= 0).any() or (df["cl2"] <= 0).any():
        raise ValueError("Non-positive futures price; log returns are undefined.")
    df["ret"] = np.log(df["cl1"]).diff()
    df["simple"] = df["cl1"].pct_change()

    # Predictors observed at the same month-end, then lagged one month.
    df["basis"] = (df["cl1"] - df["cl2"]) / df["cl1"]
    df["inv_g"] = np.log(df["inv"]).diff()
    df["ip_g"] = np.log(df["ip"]).diff()
    df["bdi_g"] = np.log(df["bdi"]).diff()
    df["rig_g"] = df["rigs"].pct_change()
    df["prod_g"] = np.log(df["prod"]).diff()
    df["crack_d"] = df["crack"].diff()
    df["slope_d"] = (df["y10"] - df["y3m"]).diff()
    df["vix_d"] = df["vix"].diff()
    df["spx_ret"] = np.log(df["spx"]).diff()
    df["cpi_d"] = df["cpi"].diff()
    net = (df["comm_long"] - df["comm_short"]) / df["oi"]
    df["net_spec_d"] = net.diff()
    df["gas_g"] = np.log(df["gasoline"]).diff()
    df["oil_eq_g"] = np.log(df["oil_eq"]).diff()

    lag_map = {
        "basis_l1": "basis",
        "inv_g_l1": "inv_g",
        "dxy_l1": "dxy",
        "ip_g_l1": "ip_g",
        "bdi_g_l1": "bdi_g",
        "ret_l1": "ret",
        "rig_g_l1": "rig_g",
        "prod_g_l1": "prod_g",
        "crack_d_l1": "crack_d",
        "slope_d_l1": "slope_d",
        "vix_d_l1": "vix_d",
        "spx_l1": "spx_ret",
        "cpi_d_l1": "cpi_d",
        "net_spec_d_l1": "net_spec_d",
        "gas_l1": "gas_g",
        "oil_eq_l1": "oil_eq_g",
    }
    for new, old in lag_map.items():
        df[new] = df[old].shift(1)

    df["date"] = df.index.to_timestamp("M")
    return df


def adf_row(series: pd.Series, regression: str) -> dict:
    s = series.dropna()
    stat, pval, lags, nobs, crit, _ = adfuller(s, autolag="AIC", regression=regression)
    return {
        "adf_stat": float(stat),
        "adf_p": float(pval),
        "adf_lags": int(lags),
        "n": int(nobs),
        "adf_5pct": float(crit["5%"]),
    }


def kpss_row(series: pd.Series, regression: str) -> dict:
    s = series.dropna()
    stat, pval, lags, crit = kpss(s, regression=regression, nlags="auto")
    return {"kpss_stat": float(stat), "kpss_p": float(pval), "kpss_5pct": float(crit["5%"])}


def stationarity_table(df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("CL1 price", df["cl1"], "c"),
        ("CL1 log return", df["ret"], "c"),
        ("Futures basis", df["basis"], "c"),
        ("Inventory growth", df["inv_g"], "c"),
        ("Dollar return", df["dxy"], "c"),
        ("IP growth", df["ip_g"], "c"),
        ("BDI growth", df["bdi_g"], "c"),
        ("CPI inflation", df["cpi"], "c"),
        ("VIX", df["vix"], "c"),
    ]
    rows = []
    for name, series, reg in specs:
        row = {"series": name}
        row.update(adf_row(series, reg))
        row.update(kpss_row(series, reg))
        rows.append(row)
    return pd.DataFrame(rows)


def fit_ols(y: pd.Series, X: pd.DataFrame, hac: bool = True):
    xc = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y, xc, missing="drop")
    if hac:
        return model.fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return model.fit()


def vif_table(X: pd.DataFrame) -> pd.DataFrame:
    xc = sm.add_constant(X, has_constant="add")
    rows = []
    for i, name in enumerate(xc.columns):
        if name == "const":
            continue
        rows.append({"variable": name, "vif": float(variance_inflation_factor(xc.values, i))})
    return pd.DataFrame(rows)


def chow_test(y: pd.Series, X: pd.DataFrame, dates: pd.Series, break_date: pd.Timestamp) -> dict:
    mask = np.asarray(pd.to_datetime(dates) < break_date)
    k = X.shape[1] + 1
    full = fit_ols(y, X, hac=False)
    left = fit_ols(y.iloc[mask], X.iloc[mask], hac=False)
    right = fit_ols(y.iloc[~mask], X.iloc[~mask], hac=False)
    ssr_p, ssr_1, ssr_2 = full.ssr, left.ssr, right.ssr
    n = int(full.nobs)
    df1 = k
    df2 = n - 2 * k
    f_stat = ((ssr_p - ssr_1 - ssr_2) / df1) / ((ssr_1 + ssr_2) / df2)
    from scipy import stats

    pval = 1 - stats.f.cdf(f_stat, df1, df2)
    return {
        "break": str(break_date.date()),
        "F": float(f_stat),
        "p": float(pval),
        "n_left": int(mask.sum()),
        "n_right": int((~mask).sum()),
    }


def select_arima_order(y: np.ndarray) -> tuple[int, int]:
    best = (np.inf, 1, 0)
    for p in range(0, 4):
        for q in range(0, 4):
            if p == 0 and q == 0:
                continue
            try:
                res = ARIMA(y, order=(p, 0, q), trend="c").fit()
                if res.aic < best[0]:
                    best = (float(res.aic), p, q)
            except Exception:
                continue
    return best[1], best[2]


def regression_metrics(y, yhat) -> dict:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    err = y - yhat
    ss_res = np.sum(err**2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return {
        "n": int(len(y)),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
        "hit_rate": float(np.mean(np.sign(yhat[np.sign(yhat) != 0]) == np.sign(y[np.sign(yhat) != 0])))
        if np.any(np.sign(yhat) != 0)
        else float("nan"),
    }


def oos_r2(y, yhat, bench) -> float:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    bench = np.asarray(bench, dtype=float)
    sse_m = np.sum((y - yhat) ** 2)
    sse_b = np.sum((y - bench) ** 2)
    return float(1 - sse_m / sse_b)


def hac_mean_test(d: np.ndarray, lags: int = 0, alternative: str = "two-sided") -> dict:
    d = np.asarray(d, dtype=float)
    d = d[np.isfinite(d)]
    n = len(d)
    mean = d.mean()
    u = d - mean
    gamma0 = np.dot(u, u) / n
    var = gamma0
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        gamma = np.dot(u[lag:], u[:-lag]) / n
        var += 2 * w * gamma
    se = np.sqrt(max(var, 0) / n)
    stat = mean / se if se > 0 else np.nan
    from scipy import stats

    if alternative == "greater":
        pval = 1 - stats.norm.cdf(stat)
    else:
        pval = 2 * (1 - stats.norm.cdf(abs(stat)))
    return {"stat": float(stat), "p": float(pval), "mean": float(mean), "n": int(n)}


def clark_west(y, yhat, bench) -> dict:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    bench = np.asarray(bench, dtype=float)
    # Positive values favour the larger model.
    f = (y - bench) ** 2 - ((y - yhat) ** 2 - (yhat - bench) ** 2)
    return hac_mean_test(f, lags=HAC_LAGS, alternative="greater")


def diebold_mariano(y, yhat, bench) -> dict:
    y = np.asarray(y, dtype=float)
    loss_diff = (y - yhat) ** 2 - (y - bench) ** 2
    # Negative mean means the model has smaller squared error.
    out = hac_mean_test(loss_diff, lags=0, alternative="two-sided")
    return out


def max_drawdown(wealth: pd.Series) -> float:
    peak = wealth.cummax()
    dd = wealth / peak - 1
    return float(dd.min())


def trading_stats(simple: pd.Series, position: pd.Series, cost: float = COST) -> dict:
    turnover = position.diff().abs()
    turnover.iloc[0] = abs(float(position.iloc[0]))
    net = position * simple - cost * turnover
    wealth = (1 + net).cumprod()
    mu = float(net.mean())
    sd = float(net.std(ddof=1))
    sharpe = mu / sd * np.sqrt(12) if sd > 0 else np.nan
    return {
        "ann_return": float((1 + mu) ** 12 - 1),
        "ann_vol": float(sd * np.sqrt(12)),
        "sharpe": float(sharpe),
        "hit_when_in_market": float(np.mean((position * simple) > 0)),
        "max_drawdown": max_drawdown(wealth),
        "total_return": float(wealth.iloc[-1] - 1),
        "avg_turnover": float(turnover.mean()),
        "wealth": wealth,
        "net": net,
    }


def expanding_forecasts(work: pd.DataFrame, order: tuple[int, int]) -> tuple[pd.DataFrame, dict]:
    y = work["ret"]
    simple = work["simple"]
    dates = work["date"]
    Xp = work[PRIMARY]
    Xw = work[WIDE]
    n = len(work)
    p, q = order

    records = []
    failures = {"arima": 0, "arimax": 0, "lasso": 0, "ridge": 0}
    last_lasso = None

    alphas = np.logspace(-4, 1, 40)
    tscv = TimeSeriesSplit(n_splits=5)

    for t in range(MIN_TRAIN, n):
        y_train = y.iloc[:t]
        y_true = float(y.iloc[t])
        row = {
            "date": dates.iloc[t],
            "ret": y_true,
            "simple": float(simple.iloc[t]),
            "naive_zero": 0.0,
            "naive_mean": float(y_train.mean()),
        }

        # Economic OLS
        ols = fit_ols(y_train, Xp.iloc[:t], hac=False)
        row["ols"] = float(ols.predict(sm.add_constant(Xp.iloc[[t]], has_constant="add")).iloc[0])

        # ARIMA on returns only
        try:
            ar = ARIMA(y_train.to_numpy(), order=(p, 0, q), trend="c").fit()
            row["arima"] = float(np.asarray(ar.forecast(1))[0])
        except Exception:
            failures["arima"] += 1
            row["arima"] = row["naive_mean"]

        # ARIMAX with the same five predictors, already lagged inside X.
        try:
            ax = ARIMA(
                y_train.to_numpy(),
                order=(p, 0, q),
                exog=Xp.iloc[:t].to_numpy(),
                trend="c",
            ).fit()
            row["arimax"] = float(np.asarray(ax.forecast(1, exog=Xp.iloc[[t]].to_numpy()))[0])
        except Exception:
            failures["arimax"] += 1
            row["arimax"] = row["ols"]

        # Penalised models on the wider set. Scale inside the training window.
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(Xw.iloc[:t])
        x_now = scaler.transform(Xw.iloc[[t]])
        try:
            las = LassoCV(alphas=alphas, cv=tscv, max_iter=20000, random_state=0).fit(
                X_tr, y_train.to_numpy()
            )
            row["lasso"] = float(las.predict(x_now)[0])
            last_lasso = {
                "alpha": float(las.alpha_),
                "coef": dict(zip(WIDE, [float(c) for c in las.coef_])),
                "date": str(dates.iloc[t].date()),
            }
        except Exception:
            failures["lasso"] += 1
            row["lasso"] = row["naive_mean"]
        try:
            rid = RidgeCV(alphas=alphas, cv=tscv).fit(X_tr, y_train.to_numpy())
            row["ridge"] = float(rid.predict(x_now)[0])
        except Exception:
            failures["ridge"] += 1
            row["ridge"] = row["naive_mean"]

        if (t - MIN_TRAIN) % 40 == 0:
            print(f"  forecast {t - MIN_TRAIN + 1} of {n - MIN_TRAIN}", flush=True)
        records.append(row)

    fc = pd.DataFrame.from_records(records)
    return fc, {"failures": failures, "last_lasso": last_lasso, "order": {"p": p, "q": q}}


def evaluate(fc: pd.DataFrame) -> pd.DataFrame:
    y = fc["ret"].to_numpy()
    rows = []
    for name in ["naive_zero", "naive_mean", "ols", "arima", "arimax", "lasso", "ridge"]:
        yhat = fc[name].to_numpy()
        m = regression_metrics(y, yhat)
        m["model"] = name
        m["oos_r2_vs_zero"] = oos_r2(y, yhat, fc["naive_zero"])
        m["oos_r2_vs_mean"] = oos_r2(y, yhat, fc["naive_mean"])
        if name not in ("naive_zero", "naive_mean"):
            cw = clark_west(y, yhat, fc["naive_mean"])
            dm = diebold_mariano(y, yhat, fc["naive_mean"])
            m["clark_west_stat"] = cw["stat"]
            m["clark_west_p"] = cw["p"]
            m["dm_stat_vs_mean"] = dm["stat"]
            m["dm_p_vs_mean"] = dm["p"]
        rows.append(m)
    return pd.DataFrame(rows)


def make_plots(df: pd.DataFrame, work: pd.DataFrame, fc: pd.DataFrame, ols_full, rec: pd.DataFrame) -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "regular",
        }
    )
    blue, red, green, grey = "#1f4e79", "#b85c38", "#2f6f4e", "#6b7280"

    # Price and return
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True)
    axes[0].plot(df["date"], df["cl1"], color=blue, lw=1.2)
    axes[0].set_ylabel("USD per barrel")
    axes[0].set_title("Front-month WTI futures price (CL1)")
    axes[1].plot(df["date"], df["ret"] * 100, color=grey, lw=0.8)
    axes[1].axhline(0, color="black", lw=0.6)
    axes[1].set_ylabel("Log return (%)")
    axes[1].set_title("Monthly CL1 log return")
    axes[1].set_xlabel("Month")
    fig.tight_layout()
    fig.savefig(OUT / "fig1_price_and_returns.png", dpi=160)
    plt.close()

    # OOS forecast comparison: RMSE bars
    order = ["naive_zero", "naive_mean", "arima", "ols", "arimax", "lasso", "ridge"]
    labels = ["Zero", "Hist. mean", "ARIMA", "OLS", "ARIMAX", "LASSO", "Ridge"]
    rmses = [regression_metrics(fc["ret"], fc[m])["rmse"] * 100 for m in order]
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    colors = [grey, grey, blue, red, blue, blue, blue]
    bars = ax.bar(labels, rmses, color=colors, width=0.72)
    ax.set_ylabel("Out-of-sample RMSE (percentage points)")
    ax.set_title("One-step monthly forecast error, expanding window")
    ax.set_ylim(0, max(rmses) + 2.0)
    for b, v in zip(bars, rmses):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + 0.18,
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#1f2937",
        )
    fig.tight_layout()
    fig.savefig(OUT / "fig2_oos_rmse.png", dpi=160)
    plt.close()

    # Cumulative trading wealth
    simple = fc.set_index("date")["simple"]
    pos_ls = np.sign(fc.set_index("date")["ols"]).replace(0, 1.0)
    pos_lf = (fc.set_index("date")["ols"] > 0).astype(float)
    pos_bh = pd.Series(1.0, index=simple.index)
    w_ls = trading_stats(simple, pos_ls)["wealth"]
    w_lf = trading_stats(simple, pos_lf)["wealth"]
    w_bh = trading_stats(simple, pos_bh, cost=0.0)["wealth"]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(w_bh.index, w_bh, color=grey, lw=1.3, label="Buy and hold CL1")
    ax.plot(w_lf.index, w_lf, color=blue, lw=1.5, label="Long / flat on OLS sign")
    ax.plot(w_ls.index, w_ls, color=red, lw=1.5, label="Long / short on OLS sign")
    ax.axhline(1, color="black", lw=0.5)
    ax.set_ylabel("Growth of $1")
    ax.set_xlabel("Month")
    ax.set_title("Out-of-sample trading rules based on the OLS forecast")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_trading_wealth.png", dpi=160)
    plt.close()

    # Predicted vs realised
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    ax.scatter(fc["ols"] * 100, fc["ret"] * 100, s=16, color=blue, alpha=0.75)
    lims = [
        min(fc["ols"].min(), fc["ret"].min()) * 100,
        max(fc["ols"].max(), fc["ret"].max()) * 100,
    ]
    ax.plot(lims, lims, color=grey, lw=0.8, label="Perfect forecast")
    ax.axhline(0, color="black", lw=0.4)
    ax.axvline(0, color="black", lw=0.4)
    ax.set_xlabel("OLS forecast (%)")
    ax.set_ylabel("Realised CL1 log return (%)")
    ax.set_title("Out-of-sample forecasts against realised returns")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig4_pred_vs_actual.png", dpi=160)
    plt.close()

    # Recursive coefficients
    fig, ax = plt.subplots(figsize=(10, 5.2))
    palette = ["#1f4e79", "#b85c38", "#2f6f4e", "#7a5c12", "#5c4d7a"]
    for col, color in zip(PRIMARY, palette):
        ax.plot(rec["date"], rec[col], color=color, lw=1.2, label=PRETTY[col])
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("Coefficient")
    ax.set_xlabel("Forecast origin (expanding sample ends here)")
    ax.set_title("Expanding-window OLS coefficients")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "fig5_recursive_coefficients.png", dpi=160)
    plt.close()

    # CUSUM
    resid = ols_full.resid
    cusum = breaks_cusumolsresid(resid, ddof=len(ols_full.params))
    # The helper returns a statistic. Build the plot from cumulative residuals ourselves.
    e = np.asarray(resid, dtype=float)
    ddof = len(ols_full.params)
    nobssigma2 = (e**2).sum() / (len(e) - ddof) * len(e)
    path = np.cumsum(e) / np.sqrt(nobssigma2)
    bound = 1.36  # 5% critical value of the OLS-residual CUSUM test
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(work["date"], path, color=blue, lw=1.3, label="CUSUM of OLS residuals")
    ax.axhline(bound, color=red, ls="--", lw=0.9, label="Approx. 5% bound")
    ax.axhline(-bound, color=red, ls="--", lw=0.9)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_title(f"CUSUM stability check (test p-value {cusum[1]:.3f})")
    ax.set_ylabel("Scaled cumulative residual")
    ax.set_xlabel("Month")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig6_cusum.png", dpi=160)
    plt.close()


def coef_frame(result) -> pd.DataFrame:
    ci = result.conf_int()
    out = pd.DataFrame(
        {
            "variable": result.params.index,
            "coef": result.params.values,
            "se": result.bse.values,
            "t": result.tvalues.values,
            "p": result.pvalues.values,
            "ci_low": ci[0].values,
            "ci_high": ci[1].values,
        }
    )
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Monthly CL1 return forecast")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="Reload outputs/oos_forecasts.csv instead of refitting the expanding window",
    )
    args = parser.parse_args()

    raw = build_panel()
    needed = ["ret", "simple", "date"] + WIDE
    work = raw.dropna(subset=needed).copy()
    work = work.reset_index(drop=True)

    stat = stationarity_table(raw)
    stat.to_csv(OUT / "table_stationarity.csv", index=False)

    y = work["ret"]
    X = work[PRIMARY]
    ols = fit_ols(y, X, hac=True)
    coefs = coef_frame(ols)
    coefs.to_csv(OUT / "table_ols_hac.csv", index=False)
    vifs = vif_table(X)
    vifs.to_csv(OUT / "table_vif.csv", index=False)

    bg = acorr_breusch_godfrey(ols, nlags=6)
    bp = het_breuschpagan(ols.resid, ols.model.exog)
    jb = jarque_bera(ols.resid)
    dw = durbin_watson(ols.resid)
    from statsmodels.stats.diagnostic import acorr_ljungbox

    lb = acorr_ljungbox(ols.resid, lags=[6, 12], return_df=True)

    chow = [
        chow_test(y, X, work["date"], pd.Timestamp("2008-09-30")),
        chow_test(y, X, work["date"], pd.Timestamp("2014-07-31")),
        chow_test(y, X, work["date"], pd.Timestamp("2020-03-31")),
    ]

    # ARIMA order from the first training window only, then held fixed.
    order = select_arima_order(y.iloc[:MIN_TRAIN].to_numpy())
    print(f"ARIMA order selected on first {MIN_TRAIN} months: ({order[0]}, 0, {order[1]})")

    # Recursive coefficients while producing forecasts, stored from the OLS fit.
    # Recomputed here so forecast loop stays focused; same sample construction.
    rec_rows = []
    for t in range(MIN_TRAIN, len(work)):
        res = fit_ols(y.iloc[:t], X.iloc[:t], hac=False)
        rec = {"date": work["date"].iloc[t - 1]}
        for name in ["const"] + PRIMARY:
            rec[name] = float(res.params[name])
        rec_rows.append(rec)
    rec = pd.DataFrame(rec_rows)
    rec.to_csv(OUT / "recursive_coefficients.csv", index=False)

    cache = OUT / "oos_forecasts.csv"
    if args.reuse and cache.exists():
        print("Reusing saved expanding-window forecasts...")
        fc = pd.read_csv(cache, parse_dates=["date"])
        extra = {
            "failures": {"arima": 0, "arimax": 0, "lasso": 0, "ridge": 0},
            "last_lasso": None,
            "order": {"p": order[0], "q": order[1]},
        }
    else:
        print("Running expanding-window forecasts...")
        fc, extra = expanding_forecasts(work, order)
        fc.to_csv(cache, index=False)
    metrics = evaluate(fc)
    metrics.to_csv(OUT / "table_oos_metrics.csv", index=False)

    # In-sample fit on the same rows the first model sees, for the overfit contrast.
    ins = fit_ols(y.iloc[:MIN_TRAIN], X.iloc[:MIN_TRAIN], hac=True)
    ins_pred = ins.predict(sm.add_constant(X.iloc[:MIN_TRAIN], has_constant="add"))
    ins_metrics = regression_metrics(y.iloc[:MIN_TRAIN], ins_pred)

    # Trading rules on the OOS simple returns.
    simple = fc.set_index("date")["simple"]
    rules = {
        "buy_hold": pd.Series(1.0, index=simple.index),
        "long_flat": (fc.set_index("date")["ols"] > 0).astype(float),
        "long_short": np.sign(fc.set_index("date")["ols"]).replace(0, 1.0),
    }
    trade_rows = []
    wealths = {}
    for name, pos in rules.items():
        # Buy and hold is the passive benchmark: do not charge the model a cost it does not incur.
        cost = 0.0 if name == "buy_hold" else COST
        stats = trading_stats(simple, pos, cost=cost)
        wealths[name] = stats.pop("wealth")
        net = stats.pop("net")
        stats["rule"] = name
        trade_rows.append(stats)
        net.to_csv(OUT / f"net_returns_{name}.csv", header=["net_return"])
    trades = pd.DataFrame(trade_rows)
    trades.to_csv(OUT / "table_trading.csv", index=False)

    make_plots(raw, work, fc, ols, rec)

    # LASSO selection frequency across the OOS loop is expensive to store fully.
    # Record the last window, plus how often each wide variable is non-zero
    # by a lighter second pass would double runtime. Store the final fit only,
    # and a full-sample descriptive LASSO for the report.
    scaler = StandardScaler()
    Xw = scaler.fit_transform(work[WIDE])
    las_full = LassoCV(
        alphas=np.logspace(-4, 1, 40),
        cv=TimeSeriesSplit(n_splits=5),
        max_iter=20000,
        random_state=0,
    ).fit(Xw, y.to_numpy())
    lasso_full = pd.DataFrame(
        {
            "variable": WIDE,
            "standardized_coef": las_full.coef_,
            "selected": np.abs(las_full.coef_) > 1e-12,
        }
    )
    lasso_full.to_csv(OUT / "table_lasso_fullsample.csv", index=False)

    # Correlation of primary predictors, for the data section.
    corr = work[PRIMARY + ["ret"]].corr()
    corr.to_csv(OUT / "table_corr.csv")

    # Mincer-Zarnowitz: realised return on the out-of-sample OLS forecast.
    mz_x = fc[["ols"]].rename(columns={"ols": "forecast"})
    mz = fit_ols(fc["ret"], mz_x, hac=True)
    mz_wald = mz.wald_test("const = 0, forecast = 1", scalar=True)

    err2 = (fc["ret"] - fc["ols"]) ** 2
    may = fc["date"] == pd.Timestamp("2020-05-31")
    may_share = float(err2[may].sum() / err2.sum()) if may.any() else None
    keep = ~may
    rmse_ex_may = float(np.sqrt(np.mean((fc.loc[keep, "ret"] - fc.loc[keep, "ols"]) ** 2)))
    rmse_mean_ex_may = float(np.sqrt(np.mean((fc.loc[keep, "ret"] - fc.loc[keep, "naive_mean"]) ** 2)))

    desc = work[PRIMARY + ["ret", "basis"]].agg(["mean", "std"]).T
    desc.to_csv(OUT / "table_descriptive.csv")

    summary = {
        "sample_start": str(work["date"].iloc[0].date()),
        "sample_end": str(work["date"].iloc[-1].date()),
        "n_regression": int(len(work)),
        "min_train": MIN_TRAIN,
        "oos_start": str(fc["date"].iloc[0].date()),
        "oos_end": str(fc["date"].iloc[-1].date()),
        "n_oos": int(len(fc)),
        "ols_r2": float(ols.rsquared),
        "ols_r2_adj": float(ols.rsquared_adj),
        "ols_n": int(ols.nobs),
        "ols_dw": float(dw),
        "bg_lm": float(bg[0]),
        "bg_p": float(bg[1]),
        "bp_lm": float(bp[0]),
        "bp_p": float(bp[1]),
        "jb_stat": float(jb[0]),
        "jb_p": float(jb[1]),
        "lb_p_6": float(lb.loc[6, "lb_pvalue"]),
        "lb_p_12": float(lb.loc[12, "lb_pvalue"]),
        "chow": chow,
        "insample_first_window": ins_metrics,
        "arima_order": {"p": order[0], "d": 0, "q": order[1]},
        "failures": extra["failures"],
        "lasso_alpha_full": float(las_full.alpha_),
        "lasso_nonzero_full": int(np.sum(np.abs(las_full.coef_) > 1e-12)),
        "last_lasso": extra["last_lasso"],
        "mean_ret_monthly": float(y.mean()),
        "std_ret_monthly": float(y.std(ddof=1)),
        "ann_mean": float((1 + work["simple"].mean()) ** 12 - 1),
        "ann_vol": float(work["simple"].std(ddof=1) * np.sqrt(12)),
        "cl1_start": float(raw.loc[raw["cl1"].first_valid_index(), "cl1"]) if False else float(raw["cl1"].dropna().iloc[0]),
        "cl1_end": float(raw["cl1"].dropna().iloc[-1]),
        "price_start_date": str(raw.loc[raw["cl1"].first_valid_index(), "date"].date()),
        "price_end_date": str(raw.loc[raw["cl1"].last_valid_index(), "date"].date()),
        "up_month_share_oos": float((fc["ret"] > 0).mean()),
        "mz_const": float(mz.params["const"]),
        "mz_slope": float(mz.params["forecast"]),
        "mz_slope_p": float(mz.pvalues["forecast"]),
        "mz_wald_stat": float(np.asarray(mz_wald.statistic).item()),
        "mz_wald_p": float(np.asarray(mz_wald.pvalue).item()),
        "may2020_share_of_ols_sse": may_share,
        "rmse_ols_ex_may2020": rmse_ex_may,
        "rmse_mean_ex_may2020": rmse_mean_ex_may,
        "corr_with_ret": {k: float(corr.loc[k, "ret"]) for k in PRIMARY},
        "predictor_mean": {k: float(work[k].mean()) for k in PRIMARY},
        "predictor_std": {k: float(work[k].std(ddof=1)) for k in PRIMARY},
    }
    # Attach metric records
    summary["oos_metrics"] = metrics.to_dict(orient="records")
    summary["coefs"] = coefs.to_dict(orient="records")
    summary["vif"] = vifs.to_dict(orient="records")
    summary["trading"] = trades.to_dict(orient="records")
    summary["stationarity"] = stat.to_dict(orient="records")

    def convert(obj):
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (pd.Timestamp,)):
            return str(obj.date())
        raise TypeError(type(obj))

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=convert), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in [
        "sample_start", "sample_end", "n_regression", "oos_start", "oos_end", "n_oos",
        "ols_r2", "ols_r2_adj", "bg_p", "bp_p", "jb_p", "lb_p_6", "arima_order", "failures"
    ]}, indent=2, default=convert))
    print(metrics[["model", "rmse", "mae", "hit_rate", "oos_r2_vs_mean"]].to_string(index=False))
    print(coefs.to_string(index=False))
    print(trades.drop(columns=[], errors="ignore").to_string(index=False))
    print("Wrote outputs to", OUT)


if __name__ == "__main__":
    main()
