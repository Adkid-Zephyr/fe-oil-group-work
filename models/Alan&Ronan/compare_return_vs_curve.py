"""
Alan & Ronan: the return model (LASSO/Ridge) vs the curve model (CL2-CL1 spread).

The return model forecasts next month's oil futures return.
The curve model forecasts the shape of the futures curve: how the CL2-CL1 spread moves.

Both are tested on the VALIDATION window only: forecasts for Jan 2005 to Dec 2014.
The shared TEST window (Jan 2015 to Jun 2024) is not used anywhere in this file,
so whichever model we choose can still be tested honestly on it once.

Method in one line: at each month-end, fit the model on all earlier months only,
forecast the next month, step forward, repeat (expanding window). Some variants
use a rolling 10-year window instead.

Run from the repository root:
    python "models/Alan&Ronan/compare_return_vs_curve.py"
Outputs go to data/results/Alan&Ronan/comparison/.
"""

from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan, het_white, breaks_cusumolsresid
from statsmodels.stats.stattools import durbin_watson
from statsmodels.stats.outliers_influence import variance_inflation_factor
from sklearn.linear_model import Lasso, Ridge, LassoCV, RidgeCV, LassoLarsIC
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402

OUT = F.ROOT / "data" / "results" / "Alan&Ronan" / "comparison"
OUT.mkdir(parents=True, exist_ok=True)

T, X = F.build()
X["dxy_lag1"] = X["dxy_ret"].shift(1)        # Felix lags the dollar one extra month

# Origins whose TARGET month falls in the validation window (Jan 2005 to Dec 2014)
VAL_FIRST, VAL_LAST = pd.Period("2004-12", "M"), pd.Period("2014-11", "M")
HALF_SPLIT = pd.Period("2009-11", "M")      # origins up to here forecast 2005-2009
ROLL = 120                                   # rolling window length in months


# ---------------------------------------------------------------------------
# Forecasting engine
# ---------------------------------------------------------------------------
def run(target, cols, method, window=None):
    """Return (forecast Series over validation origins, list of LASSO selections)."""
    cols = cols or []
    data = (X[cols].join(T[target].rename("y")) if cols else T[[target]].rename(columns={target: "y"})).dropna()
    idx = data.index
    val_pos = np.where((idx >= VAL_FIRST) & (idx <= VAL_LAST))[0]
    Xa = data[cols].values if cols else None
    ya = data["y"].values
    preds, selections = [], []

    if method == "zero":
        return pd.Series(0.0, index=idx[val_pos]), selections

    if method == "arima":
        # Order chosen once by BIC on the data before the validation window
        best = None
        for p in range(3):
            for q in range(3):
                try:
                    bic = ARIMA(ya[:val_pos[0]], order=(p, 0, q), trend="c").fit().bic
                except Exception:
                    continue
                if best is None or bic < best[0]:
                    best = (bic, (p, 0, q))
        order = best[1]
        for i in val_pos:
            lo = max(0, i - window) if window else 0
            preds.append(float(ARIMA(ya[lo:i], order=order, trend="c").fit().forecast(1)[0]))
        s = pd.Series(preds, index=idx[val_pos])
        s.attrs["order"] = order
        return s, selections

    alpha = None
    for n, i in enumerate(val_pos):
        lo = max(0, i - window) if window else 0
        ytr = ya[lo:i]
        if method == "mean":
            preds.append(ytr.mean())
            continue
        Xtr, xte = Xa[lo:i], Xa[i:i + 1]
        if method == "pool":
            # Forecast pooling: one small OLS per predictor, then average the forecasts
            fs = []
            for j in range(Xtr.shape[1]):
                A = np.column_stack([np.ones(len(Xtr)), Xtr[:, j]])
                b = np.linalg.lstsq(A, ytr, rcond=None)[0]
                fs.append(b[0] + b[1] * xte[0, j])
            preds.append(float(np.mean(fs)))
            continue
        if method == "ols":
            A = np.column_stack([np.ones(len(Xtr)), Xtr])
            beta = np.linalg.lstsq(A, ytr, rcond=None)[0]
            preds.append(float(np.r_[1.0, xte[0]] @ beta))
            continue

        # Penalised models: predictors standardised on the training data only
        sc = StandardScaler().fit(Xtr)
        Z, z = sc.transform(Xtr), sc.transform(xte)
        # Tune the penalty once a year with time-series cross-validation
        if method in ("lasso_cv", "post_lasso", "ridge_cv") and n % 12 == 0:
            if method == "ridge_cv":
                alpha = RidgeCV(alphas=np.logspace(-2, 5, 60), cv=TimeSeriesSplit(n_splits=5)).fit(Z, ytr).alpha_
            else:
                alpha = LassoCV(cv=TimeSeriesSplit(n_splits=5), alphas=50, max_iter=50000).fit(Z, ytr).alpha_
        if method == "ridge_cv":
            preds.append(float(Ridge(alpha=alpha).fit(Z, ytr).predict(z)[0]))
        elif method == "lasso_cv":
            mdl = Lasso(alpha=alpha, max_iter=50000).fit(Z, ytr)
            selections.append(mdl.coef_ != 0)
            preds.append(float(mdl.predict(z)[0]))
        elif method in ("lasso_bic", "lasso_aic"):
            mdl = LassoLarsIC(criterion=method.split("_")[1]).fit(Z, ytr)
            selections.append(mdl.coef_ != 0)
            preds.append(float(mdl.predict(z)[0]))
        elif method == "post_lasso":
            # Use LASSO to choose predictors, then plain OLS on the chosen ones
            keep = Lasso(alpha=alpha, max_iter=50000).fit(Z, ytr).coef_ != 0
            selections.append(keep)
            if keep.sum() == 0:
                preds.append(ytr.mean())
            else:
                A = np.column_stack([np.ones(len(Xtr)), Xtr[:, keep]])
                beta = np.linalg.lstsq(A, ytr, rcond=None)[0]
                preds.append(float(np.r_[1.0, xte[0, keep]] @ beta))
    return pd.Series(preds, index=idx[val_pos]), selections


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def oos_r2(y, f):
    return 100 * (1 - np.sum((y - f) ** 2) / np.sum(y ** 2))


def clark_west_p(y, f):
    """One-sided test that the model beats the zero forecast (Clark and West, 2007)."""
    if np.allclose(f, 0):
        return np.nan
    adj = y ** 2 - ((y - f) ** 2 - f ** 2)
    res = sm.OLS(adj, np.ones(len(adj))).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return 1 - stats.norm.cdf(res.tvalues[0])


def dm_mae_p(y, f):
    """Two-sided Diebold-Mariano test on absolute errors vs the zero forecast."""
    if np.allclose(f, 0):
        return np.nan
    d = np.abs(y) - np.abs(y - f)
    res = sm.OLS(d, np.ones(len(d))).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return 2 * (1 - stats.norm.cdf(abs(res.tvalues[0])))


def block_bootstrap_ci(y, f, block=6, draws=2000, seed=0):
    """90% interval for out-of-sample R2 using a moving block bootstrap."""
    rng = np.random.default_rng(seed)
    n = len(y)
    starts = np.arange(n - block + 1)
    out = []
    for _ in range(draws):
        pick = np.concatenate([np.arange(s, s + block) for s in rng.choice(starts, n // block + 1)])[:n]
        out.append(oos_r2(y[pick], f[pick]))
    return np.percentile(out, [5, 95])


def score(y_series, f_series):
    y, f = y_series.values, f_series.values
    first = y_series.index <= HALF_SPLIT
    lo, hi = block_bootstrap_ci(y, f) if not np.allclose(f, 0) else (0.0, 0.0)
    return {
        "n": len(y),
        "rmse": np.sqrt(np.mean((y - f) ** 2)),
        "mae": np.mean(np.abs(y - f)),
        "mae_gain_pct": 100 * (1 - np.mean(np.abs(y - f)) / np.mean(np.abs(y))),
        "dm_mae_p": dm_mae_p(y, f),
        "oos_r2_pct": oos_r2(y, f),
        "oos_r2_2005_09": oos_r2(y[first], f[first]),
        "oos_r2_2010_14": oos_r2(y[~first], f[~first]),
        "r2_ci90_low": lo,
        "r2_ci90_high": hi,
        "hit_rate_pct": 100 * np.mean(np.sign(f) == np.sign(y)) if not np.allclose(f, 0) else np.nan,
        "clark_west_p": clark_west_p(y, f),
    }


def trading(y_series, f_series):
    """Go long when the forecast is positive, short when negative, monthly."""
    y, f = y_series.values, f_series.values
    pos = np.sign(f)
    strat = pos * y
    wealth = np.cumprod(1 + strat / 100)
    drawdown = 1 - wealth / np.maximum.accumulate(wealth)
    return {
        "share_months_long": 100 * np.mean(pos > 0),
        "ann_return_pct": 12 * strat.mean(),
        "ann_vol_pct": np.sqrt(12) * strat.std(ddof=1),
        "sharpe": (12 * strat.mean()) / (np.sqrt(12) * strat.std(ddof=1)) if strat.std() > 0 else np.nan,
        "max_drawdown_pct": 100 * drawdown.max(),
    }


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------
THEORY_RET = ["ret", "spread", "hedging_pressure", "inv_vs_seasonal"]   # momentum, roll yield, hedging pressure, inventories
FELIX = ["ret", "spread", "dxy_lag1"]
STORAGE = ["spread", "inv_vs_seasonal"]

RETURN_VARIANTS = [
    ("No change", None, "zero", None),
    ("Historical mean", None, "mean", None),
    ("ARIMA by BIC", None, "arima", None),
    ("AR(1)", ["ret"], "ols", None),
    ("Felix spec (OLS)", FELIX, "ols", None),
    ("Theory OLS: momentum, roll yield, hedging, inventories", THEORY_RET, "ols", None),
    ("LASSO CV, core 16", F.CORE, "lasso_cv", None),
    ("LASSO BIC, core 16", F.CORE, "lasso_bic", None),
    ("Ridge CV, core 16", F.CORE, "ridge_cv", None),
    ("LASSO CV, wide 29", F.WIDE, "lasso_cv", None),
    ("LASSO AIC, wide 29", F.WIDE, "lasso_aic", None),
    ("LASSO BIC, wide 29", F.WIDE, "lasso_bic", None),
    ("Ridge CV, wide 29", F.WIDE, "ridge_cv", None),
    ("Post-LASSO OLS, wide 29", F.WIDE, "post_lasso", None),
    ("LASSO CV, wide 29, rolling 10y", F.WIDE, "lasso_cv", ROLL),
    ("Ridge CV, wide 29, rolling 10y", F.WIDE, "ridge_cv", ROLL),
    ("Theory OLS, rolling 10y", THEORY_RET, "ols", ROLL),
    ("Pooled one-predictor forecasts, wide 29", F.WIDE, "pool", None),
]

CURVE_VARIANTS = [
    ("No change", None, "zero", None),
    ("Historical mean", None, "mean", None),
    ("ARIMA by BIC", None, "arima", None),
    ("Mean reversion: spread only", ["spread"], "ols", None),
    ("Storage: spread + inventories vs seasonal", STORAGE, "ols", None),
    ("Storage + interest rate", STORAGE + ["y3m"], "ols", None),
    ("Storage + weekly inventory nowcast", STORAGE + ["inv_nowcast_weekly"], "ols", None),
    ("Storage + realised volatility", STORAGE + ["realised_vol"], "ols", None),
    ("Storage + rate + volatility", STORAGE + ["y3m", "realised_vol"], "ols", None),
    ("LASSO CV, wide 29", F.WIDE, "lasso_cv", None),
    ("LASSO BIC, wide 29", F.WIDE, "lasso_bic", None),
    ("Ridge CV, wide 29", F.WIDE, "ridge_cv", None),
    ("Post-LASSO OLS, wide 29", F.WIDE, "post_lasso", None),
    ("Storage, rolling 10y", STORAGE, "ols", ROLL),
    ("LASSO CV, wide 29, rolling 10y", F.WIDE, "lasso_cv", ROLL),
    ("Pooled one-predictor forecasts, wide 29", F.WIDE, "pool", None),
]

RUNS = [("Return model", "ret_held", RETURN_VARIANTS),
        ("Return model (raw CL1, shared target)", "ret_cont",
         [v for v in RETURN_VARIANTS if v[0] in ("No change", "Historical mean", "Felix spec (OLS)",
                                                 "Theory OLS: momentum, roll yield, hedging, inventories",
                                                 "LASSO CV, wide 29", "Ridge CV, wide 29",
                                                 "Pooled one-predictor forecasts, wide 29")]),
        ("Curve model: slope change", "d_spread", CURVE_VARIANTS),
        ("Curve model: tradable calendar spread", "spread_pnl", CURVE_VARIANTS)]

rows, trade_rows, sel_rows, forecasts = [], [], [], {}
for option, target, variants in RUNS:
    print(f"Running {option} ...", flush=True)
    for name, cols, method, window in variants:
        f, sel = run(target, cols, method, window)
        y = T[target].loc[f.index]
        assert len(y) == 120 and y.notna().all(), (name, len(y))
        label = name + (f" {f.attrs['order']}" if "order" in f.attrs else "")
        rows.append({"option": option, "target": target, "variant": label,
                     "n_predictors": len(cols) if cols else 0, **score(y, f)})
        forecasts[(target, label)] = f
        if target in ("ret_held", "spread_pnl") and method != "zero":
            trade_rows.append({"option": option, "target": target, "variant": label, **trading(y, f)})
        if sel:
            share = np.mean(sel, axis=0) * 100
            for c, s in zip(cols, share):
                sel_rows.append({"target": target, "variant": label, "predictor": c, "kept_pct": s})
    # Buy-and-hold reference for the tradable targets
    if target in ("ret_held", "spread_pnl"):
        y = T[target].loc[forecasts[(target, "No change")].index]
        trade_rows.append({"option": option, "target": target, "variant": "Always long (reference)",
                           **trading(y, pd.Series(1.0, index=y.index))})

results = pd.DataFrame(rows)
trades = pd.DataFrame(trade_rows)
selections = pd.DataFrame(sel_rows)
results.to_csv(OUT / "variants_validation.csv", index=False)
trades.to_csv(OUT / "trading_validation.csv", index=False)
selections.to_csv(OUT / "lasso_selection.csv", index=False)

# Cumulative error advantage over no change, scaled so the last value equals OOS R2 (%)
cum = {}
for (target, label), f in forecasts.items():
    y = T[target].loc[f.index]
    cum[f"{target} | {label}"] = 100 * np.cumsum(y ** 2 - (y - f) ** 2) / np.sum(y ** 2)
pd.DataFrame(cum).to_csv(OUT / "cumulative_advantage.csv")


# ---------------------------------------------------------------------------
# Diagnostics on the interpretable lead specification of each option
# (fitted on all origins before the test window, i.e. targets up to Dec 2014)
# ---------------------------------------------------------------------------
def chow_test(y, Xc, split_pos):
    def rss(yy, XX):
        return sm.OLS(yy, XX).fit().ssr
    k = Xc.shape[1]
    r_all = rss(y, Xc)
    r1, r2 = rss(y[:split_pos], Xc[:split_pos]), rss(y[split_pos:], Xc[split_pos:])
    Fstat = ((r_all - r1 - r2) / k) / ((r1 + r2) / (len(y) - 2 * k))
    return Fstat, 1 - stats.f.cdf(Fstat, k, len(y) - 2 * k)


def diagnostics(target, cols, name):
    data = X[cols].join(T[target].rename("y")).dropna().loc[:VAL_LAST]
    y, Xc = data["y"].values, sm.add_constant(data[cols].values)
    ols = sm.OLS(y, Xc).fit()
    hac = sm.OLS(y, Xc).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    resid = ols.resid
    split = int(np.searchsorted(data.index.values, pd.Period("2008-12", "M")))
    chow_F, chow_p = chow_test(y, Xc, split)
    coef = pd.DataFrame({"coef": ols.params, "se_ols": ols.bse, "p_ols": ols.pvalues,
                         "se_newey_west": hac.bse, "p_newey_west": hac.pvalues},
                        index=["const"] + cols)
    coef["vif"] = [np.nan] + [variance_inflation_factor(Xc, j) for j in range(1, Xc.shape[1])]
    tests = {
        "sample": f"{data.index[0]} to {data.index[-1]} (n={len(y)})",
        "r2_in_sample": ols.rsquared,
        "adf_p_target": adfuller(y, autolag="AIC")[1],
        **{f"adf_p_{c}": adfuller(data[c].values, autolag="AIC")[1] for c in cols},
        "ljung_box_12_p": acorr_ljungbox(resid, lags=[12])["lb_pvalue"].iloc[0],
        "durbin_watson": durbin_watson(resid),
        "breusch_pagan_p": het_breuschpagan(resid, Xc)[1],
        "white_p": het_white(resid, Xc)[1],
        "chow_dec2008_p": chow_p,
        "cusum_p": breaks_cusumolsresid(resid, ddof=Xc.shape[1])[1],
        "arch_lm_p": acorr_ljungbox(resid ** 2, lags=[12])["lb_pvalue"].iloc[0],
    }
    coef.to_csv(OUT / f"diagnostics_coefficients_{name}.csv")
    pd.Series(tests).to_csv(OUT / f"diagnostics_tests_{name}.csv")
    return coef, tests


diag = {
    "return_theory": diagnostics("ret_held", THEORY_RET, "return_theory"),
    "curve_storage_slope": diagnostics("d_spread", STORAGE, "curve_storage_slope"),
    "curve_storage_tradable": diagnostics("spread_pnl", STORAGE, "curve_storage_tradable"),
}


# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------
pd.set_option("display.width", 220, "display.max_columns", 30, "display.max_colwidth", 60)
show = ["variant", "oos_r2_pct", "oos_r2_2005_09", "oos_r2_2010_14", "r2_ci90_low", "r2_ci90_high",
        "mae_gain_pct", "dm_mae_p", "hit_rate_pct", "clark_west_p"]
for option in results["option"].unique():
    print(f"\n=== {option} (validation 2005-2014, 120 months) ===")
    print(results.loc[results.option == option, show].round(2).to_string(index=False))
print("\n=== Simple long/short trading rule (validation) ===")
print(trades.round(2).to_string(index=False))
if len(selections):
    print("\n=== LASSO: share of refits keeping each predictor (top 6 per variant) ===")
    top = selections.sort_values("kept_pct", ascending=False).groupby(["target", "variant"]).head(6)
    print(top.round(0).to_string(index=False))
for k, (coef, tests) in diag.items():
    print(f"\n=== Diagnostics: {k} ===")
    print(coef.round(3).to_string())
    print(pd.Series(tests).to_string())
