"""
Alan & Ronan: a LASSO predictive regression for monthly oil futures returns.

The question we answer for the trader
-------------------------------------
"Do fundamentals and macro data help forecast next month's oil futures return?"

How the script is laid out
--------------------------
STEP 1  Load the data, and say what we leave out and why
STEP 2  Build the target (what we forecast)
STEP 3  Build 29 candidate predictors, each lagged to when it was published
STEP 4  Stationarity check, and fix the predictors that fail it
STEP 5  Split time into training, validation and test
STEP 6  Look inside LASSO on the pre-2015 data
STEP 7  Validation run, Jan 2005 to Dec 2014, month by month
STEP 8  Diagnostics
STEP 9  Test run, Jan 2015 to Jun 2024  (SWITCHED OFF until the group agrees the target)

Rules we follow
---------------
- Every predictor in row t was known at the END of month t. Targets are what happens after t.
- Models are refitted each month on earlier data only (expanding window).
- The test window (2015-2024) is not touched unless RUN_TEST is switched on.
  We get to look at it once, after the specification is frozen in README.md.

Run from the repository root:
    python "models/Alan&Ronan/lasso_model.py"              # steps 1 to 8
    python "models/Alan&Ronan/lasso_model.py" --run-test   # adds step 9, run once only
"""

from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from statsmodels.stats.diagnostic import (acorr_ljungbox, het_breuschpagan, het_white,
                                          breaks_cusumolsresid)
from statsmodels.stats.outliers_influence import variance_inflation_factor
from sklearn.linear_model import Lasso, Ridge, LassoCV, RidgeCV, LassoLarsIC, lasso_path
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 70)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "data" / "results" / "Alan&Ronan" / "lasso_model"
OUT.mkdir(parents=True, exist_ok=True)

RUN_TEST = "--run-test" in sys.argv        # step 9 only runs when asked for explicitly
MAIN_TARGET = "ret_held"                   # tradable return; "ret_cont" is the raw CL1 change
ADF_CUTOFF = 0.10                          # predictors with ADF p-value above this get differenced
ROLL = 120                                 # rolling window for the robustness check (10 years)

# A forecast made at the end of month t is for month t+1, so origins run one month earlier.
TRAIN_END = pd.Period("2014-11", "M")      # last origin used for anything before the test
VAL_ORIGINS = (pd.Period("2004-12", "M"), pd.Period("2014-11", "M"))   # forecasts Jan 2005 - Dec 2014
TEST_ORIGINS = (pd.Period("2014-12", "M"), pd.Period("2024-05", "M"))  # forecasts Jan 2015 - Jun 2024


def step(n, title):
    print("\n" + "=" * 90 + f"\nSTEP {n}  {title}\n" + "=" * 90)


# ===========================================================================
step(1, "Load the data")
# ===========================================================================
# We use the group's shared cleaned tables, the only version with all three frequencies.
# The monthly numbers are identical to Mike's monthly file.
daily = pd.read_csv(CLEAN / "industry_daily.csv", parse_dates=["date"]).set_index("date")
weekly = pd.read_csv(CLEAN / "industry_weekly.csv", parse_dates=["date"]).set_index("date")
m = pd.read_csv(CLEAN / "monthly_observations.csv")
m["month"] = pd.PeriodIndex(m["month"], freq="M")
m = m.set_index("month")
idx = m.index
month_end = idx.to_timestamp(how="end").normalize()

print(f"Monthly : {len(m)} months, {idx[0]} to {idx[-1]} (Industry_M, Macro_M)")
print(f"Weekly  : {len(weekly)} weeks, {weekly.index[0].date()} to {weekly.index[-1].date()} (Industry_W)")
print(f"Daily   : {len(daily)} days, {daily.index[0].date()} to {daily.index[-1].date()} (Industry_D, CL1 and CL2 only)")
print("""
Left out, and why:
  - Daily Brent, crack spread, BDI : do not line up with their monthly versions; 534 undated Brent rows
  - 'Total Open Interest'          : it is just commercial long + short, not a separate measure
  - Shell share price              : 127 missing months at the start
  - Oil company shares, gasoline   : mostly move with oil itself, so little new information""")


# ===========================================================================
step(2, "Build the target")
# ===========================================================================
# CL1 is always the nearest contract. Each month the old one expires and CL1 switches.
# The contract that is CL2 at the end of month t is CL1 at the end of t+1, so:
#   tradable return = CL1(t+1) / CL2(t) - 1     (what a trader holding one contract earns)
#   raw CL1 change  = CL1(t+1) / CL1(t) - 1     (the group's shared target, includes the switch)
c1, c2 = m["industry__cl1"], m["industry__cl2"]
held = 100 * (c1 / c2.shift() - 1)
cont = 100 * (c1 / c1.shift() - 1)
T = pd.DataFrame({"ret_held": held.shift(-1), "ret_cont": cont.shift(-1)}, index=idx)

ex = pd.Period("2014-12", "M")
print(f"Example, end of Dec 2014: CL1 = {c1[ex]:.2f}, CL2 = {c2[ex]:.2f}. End of Jan 2015: CL1 = {c1[ex + 1]:.2f}")
print(f"  raw CL1 change : {T.loc[ex, 'ret_cont']:+.2f}%   (compares two different contracts)")
print(f"  tradable return: {T.loc[ex, 'ret_held']:+.2f}%   (same contract, start to end)")
print(f"\nAverage gap between the two, per month: {(T.ret_cont - T.ret_held).mean():+.2f} percentage points")
print(f"Correlation between the two: {T[['ret_cont', 'ret_held']].corr().iloc[0, 1]:.3f}")
print(f"Monthly volatility: tradable {T.ret_held.std():.1f}%, raw {T.ret_cont.std():.1f}%")


# ===========================================================================
step(3, "Build 29 candidate predictors")
# ===========================================================================
X = pd.DataFrame(index=idx)
info = []   # (name, group, source, lag rule)


def add(name, series, group, source, lag):
    X[name] = series
    info.append((name, group, source, lag))


spread = 100 * (c2 / c1 - 1)                      # >0 contango, <0 backwardation
inv = m["industry__inventories_source_units"]
long_, short_ = m["industry__commercial_long"], m["industry__commercial_short"]
net = 100 * (long_ - short_) / (long_ + short_)
y3, y10 = m["macro__treasury_3m_yield_pct"], m["macro__treasury_10y_yield_pct"]

# Prices: known exactly at month-end, so no lag
add("ret", held, "price", "monthly", "0: last month's return (momentum)")
add("ret_lag2", held.shift(1), "price", "monthly", "0: return two months ago")
add("ret_lag3", held.shift(2), "price", "monthly", "0: return three months ago")
add("mom12", 100 * ((1 + held / 100).rolling(12).apply(np.prod, raw=True) - 1), "price", "monthly", "0: 12-month return")
add("spread", spread, "price", "monthly", "0: curve slope, contango +")
add("d_spread_last", spread.diff(), "price", "monthly", "0: change in curve slope")
add("brent_wti", 100 * (m["industry__brent"] / c1 - 1), "price", "monthly", "0: Brent premium over WTI")
add("crack_chg", m["industry__crack_spread_321"].diff(), "price", "monthly", "0: change in refining margin")
add("bdi_chg", 100 * m["industry__baltic_dry_index"].pct_change(), "price", "monthly", "0: shipping demand")

# Market and macro
add("vix", m["macro__vix"], "market", "monthly", "0: equity fear gauge, level")
add("vix_chg", m["macro__vix"].diff(), "market", "monthly", "0: change in VIX")
add("spx_ret", 100 * m["macro__sp500_index"].pct_change(), "market", "monthly", "0: S&P 500 return")
add("dxy_ret", m["macro__dxy_return_pct"], "market", "monthly", "0: dollar index return")
add("ip_growth", 100 * m["macro__industrial_production_index"].pct_change().shift(1), "macro", "monthly", "1: published mid next month")
add("cpi_chg", m["macro__cpi_yoy_pct"].diff().shift(1), "macro", "monthly", "1: published mid next month")
add("y3m", y3.shift(2), "macro", "monthly", "2: yields are labelled a month early")
add("y3m_chg", y3.diff().shift(2), "macro", "monthly", "2: yields are labelled a month early")
add("term_spread", (y10 - y3).shift(2), "macro", "monthly", "2: yields are labelled a month early")

# Monthly fundamentals: published after month-end, so lagged one month
add("inv_chg", 100 * inv.pct_change().shift(1), "fundamental", "monthly", "1: inventories, monthly change")
add("inv_yoy", 100 * inv.pct_change(12).shift(1), "fundamental", "monthly", "1: inventories vs a year ago")
seasonal = sum(inv.shift(12 * k) for k in (1, 2, 3)) / 3
add("inv_vs_seasonal", (100 * (inv / seasonal - 1)).shift(1), "fundamental", "monthly", "1: vs same month, last 3 years")
add("prod_chg", 100 * m["industry__crude_production_source_units"].pct_change().shift(1), "fundamental", "monthly", "1: production change")
add("rig_chg", 100 * m["industry__rig_count"].pct_change().shift(1), "fundamental", "monthly", "1: rig count change")
add("hedging_pressure", net.shift(1), "fundamental", "monthly", "1: hedgers' net position")
add("hedging_pressure_chg", net.diff().shift(1), "fundamental", "monthly", "1: change in hedgers' position")

# Weekly data turned into one number per month.
# Only weeks dated at least 7 days before month-end, because EIA stock data come out
# the following Wednesday and CFTC positions on the Friday after.
cut = month_end - pd.Timedelta(days=7)
wnet = 100 * (weekly["commercial_long_unimputed"] - weekly["commercial_short"]) / \
       (weekly["commercial_long_unimputed"] + weekly["commercial_short"])
inv_now, hp_now, rig_now = [], [], []
for i, c in enumerate(cut):
    lo = cut[i - 1] if i > 0 else c - pd.Timedelta(days=31)
    inv_now.append(weekly.loc[(weekly.index > lo) & (weekly.index <= c),
                              "crude_stock_change_source_units"].sum(min_count=1))
    known_net = wnet.loc[wnet.index <= c].dropna()
    hp_now.append(known_net.iloc[-1] if len(known_net) else np.nan)
    rigs = weekly.loc[weekly.index <= c, "rig_count"].dropna()
    rig_now.append(100 * (rigs.iloc[-1] / rigs.iloc[-5] - 1) if len(rigs) > 5 else np.nan)
add("inv_nowcast_weekly", inv_now, "weekly", "weekly", "7 days: stock changes published by month-end")
add("hedging_pressure_weekly", hp_now, "weekly", "weekly", "7 days: latest CFTC net position")
add("rig_chg_weekly", rig_now, "weekly", "weekly", "7 days: rig count change, last 4 weeks")

# Daily CL1 turned into one number per month: realised volatility.
# On roll days the return uses yesterday's CL2, because CL1 has switched contract.
# 20-21 April 2020 are skipped: CL1 settled at -37.63 and % returns break.
td = daily.index
roll_days = []
for p in pd.period_range(td.min().to_period("M"), td.max().to_period("M"), freq="M"):
    d25 = pd.Timestamp(p.year, p.month, 25)
    last_trade = d25 - pd.offsets.BDay(3 if d25.dayofweek < 5 else 4)
    after = td[td > last_trade]
    if len(after):
        roll_days.append(after[0])
is_roll = td.isin(roll_days)
dret = pd.Series(np.where(is_roll, daily["cl1"] / daily["cl2"].shift() - 1,
                          daily["cl1"] / daily["cl1"].shift() - 1), index=td)
dret = dret.drop(pd.to_datetime(["2020-04-20", "2020-04-21"]), errors="ignore")
rv = dret.groupby(dret.index.to_period("M")).std() * np.sqrt(252) * 100
add("realised_vol", rv.reindex(idx), "daily", "daily", "0: volatility of daily CL1 this month")

info = pd.DataFrame(info, columns=["predictor", "group", "source", "lag (months) and meaning"]).set_index("predictor")
info["first month"] = [str(X[c].first_valid_index()) for c in info.index]
print(info.to_string())


# ===========================================================================
step(4, "Stationarity check (ADF test, pre-2015 data only)")
# ===========================================================================
# A predictor that wanders (non-stationary) can create fake relationships with returns.
# Rule: if the ADF test cannot reject a unit root at 10%, use its monthly change instead.
# If its change is already in the list, just drop the level.
already_have_change = {"y3m": "y3m_chg", "vix": "vix_chg", "spread": "d_spread_last",
                       "hedging_pressure": "hedging_pressure_chg"}
pre = X.loc[:TRAIN_END]
adf_rows, final_cols = [], []
for c in X.columns:
    p = adfuller(pre[c].dropna(), autolag="AIC")[1]
    if p <= ADF_CUTOFF:
        action, keep = "keep", c
    elif c in already_have_change:
        action, keep = f"drop (already have {already_have_change[c]})", None
    else:
        X[c + "_d"] = X[c].diff()
        action, keep = f"use monthly change ({c}_d)", c + "_d"
        info.loc[c + "_d"] = [info.loc[c, "group"], info.loc[c, "source"], "change in " + c, ""]
    adf_rows.append({"predictor": c, "adf_p": round(p, 3), "action": action})
    if keep:
        final_cols.append(keep)
adf = pd.DataFrame(adf_rows)
p_target = adfuller(T[MAIN_TARGET].loc[:TRAIN_END].dropna(), autolag="AIC")[1]
print(f"Target ({MAIN_TARGET}) ADF p-value: {p_target:.4f} -> stationary\n")
print(adf[adf.action != "keep"].to_string(index=False))
print(f"\n{(adf.action == 'keep').sum()} predictors pass as they are. Final candidate list: {len(final_cols)} predictors.")
adf.to_csv(OUT / "step4_stationarity.csv", index=False)
PREDICTORS = final_cols


# ===========================================================================
step(5, "Split time into training, validation and test")
# ===========================================================================
data = X[PREDICTORS].join(T).dropna(subset=PREDICTORS + ["ret_held"])
first = data.index[0]
n_val = ((data.index >= VAL_ORIGINS[0]) & (data.index <= VAL_ORIGINS[1])).sum()
n_test = ((data.index >= TEST_ORIGINS[0]) & (data.index <= TEST_ORIGINS[1])).sum()
print(f"First month with every predictor available: {first} (the seasonal inventory measure needs 3 years of history)")
print(f"Training before validation : {first} to {VAL_ORIGINS[0] - 1} -> {(data.index < VAL_ORIGINS[0]).sum()} months")
print(f"Validation forecasts        : Jan 2005 to Dec 2014 -> {n_val} months  (used to compare and choose)")
print(f"Test forecasts              : Jan 2015 to Jun 2024 -> {n_test} months  (used once, at the end)")
print("Expanding window: each forecast is fitted on every earlier month, never on later ones.")


# ===========================================================================
step(6, "Look inside LASSO on the pre-2015 data")
# ===========================================================================
# LASSO minimises: squared errors + lambda * sum(|beta|). Predictors are standardised first
# so the penalty treats them equally. Lambda is chosen by time-series cross-validation:
# train on the early part, test on the next block, repeat, pick the lambda with lowest error.
pre = data.loc[:TRAIN_END]
sc = StandardScaler().fit(pre[PREDICTORS])
Z, y = sc.transform(pre[PREDICTORS]), pre[MAIN_TARGET].values
cv = LassoCV(cv=TimeSeriesSplit(n_splits=5), alphas=50, max_iter=50000).fit(Z, y)
alphas, coefs, _ = lasso_path(Z, y - y.mean(), n_alphas=200)
entry = []
for j, c in enumerate(PREDICTORS):
    nz = np.nonzero(coefs[j])[0]
    entry.append({"predictor": c, "enters_at_lambda": alphas[nz[0]] if len(nz) else 0.0,
                  "sign": "+" if len(nz) and coefs[j, nz[0]] > 0 else ("-" if len(nz) else "")})
entry = pd.DataFrame(entry).sort_values("enters_at_lambda", ascending=False).reset_index(drop=True)
entry.index += 1
print(f"Lambda chosen by cross-validation: {cv.alpha_:.3f}. Largest lambda on the path: {alphas[0]:.3f}")
print(f"Predictors kept at that lambda: {int(np.sum(cv.coef_ != 0))} of {len(PREDICTORS)}")
print("\nOrder in which predictors enter as the penalty is relaxed (first = strongest signal):")
print(entry.head(8).round(3).to_string())
entry.to_csv(OUT / "step6_lasso_entry_order.csv")
TOP4 = entry["predictor"].head(4).tolist()


# ===========================================================================
# Forecasting engine (used by steps 7 and 9)
# ===========================================================================
def forecast(df, target, cols, method, origins, window=None):
    """Expanding (or rolling) window, one forecast per origin. Penalty re-tuned once a year."""
    pos = np.where((df.index >= origins[0]) & (df.index <= origins[1]))[0]
    Xa, ya = df[cols].values, df[target].values
    out, kept, alpha = [], [], None
    for n, i in enumerate(pos):
        lo = max(0, i - window) if window else 0
        Xtr, ytr, xte = Xa[lo:i], ya[lo:i], Xa[i:i + 1]
        ok = ~np.isnan(ytr)                      # the latest target may not be known yet
        Xtr, ytr = Xtr[ok], ytr[ok]
        if method == "zero":
            out.append(0.0); continue
        if method == "mean":
            out.append(ytr.mean()); continue
        if method == "ols":
            A = np.column_stack([np.ones(len(Xtr)), Xtr])
            b = np.linalg.lstsq(A, ytr, rcond=None)[0]
            out.append(float(np.r_[1.0, xte[0]] @ b)); continue
        s = StandardScaler().fit(Xtr)
        Ztr, zte = s.transform(Xtr), s.transform(xte)
        if method in ("lasso", "ridge") and n % 12 == 0:
            alpha = (RidgeCV(alphas=np.logspace(-2, 5, 60), cv=TimeSeriesSplit(n_splits=5)).fit(Ztr, ytr).alpha_
                     if method == "ridge" else
                     LassoCV(cv=TimeSeriesSplit(n_splits=5), alphas=50, max_iter=50000).fit(Ztr, ytr).alpha_)
        if method == "lasso":
            mdl = Lasso(alpha=alpha, max_iter=50000).fit(Ztr, ytr)
            kept.append(mdl.coef_ != 0)
        elif method == "ridge":
            mdl = Ridge(alpha=alpha).fit(Ztr, ytr)
        elif method == "lasso_bic":
            mdl = LassoLarsIC(criterion="bic").fit(Ztr, ytr)
            kept.append(mdl.coef_ != 0)
        out.append(float(mdl.predict(zte)[0]))
    return pd.Series(out, index=df.index[pos]), kept


def oos_r2(y, f):
    return 100 * (1 - np.sum((y - f) ** 2) / np.sum(y ** 2))


def scores(y, f):
    y, f = np.asarray(y), np.asarray(f)
    flat = np.allclose(f, 0)
    half = len(y) // 2
    d_mae = np.abs(y) - np.abs(y - f)
    cw = y ** 2 - ((y - f) ** 2 - f ** 2)
    hac = lambda v: sm.OLS(v, np.ones(len(v))).fit(cov_type="HAC", cov_kwds={"maxlags": 6}).tvalues[0]
    return {"RMSE": np.sqrt(np.mean((y - f) ** 2)), "MAE": np.mean(np.abs(y - f)),
            "R2_oos_%": oos_r2(y, f),
            "R2_first_half_%": oos_r2(y[:half], f[:half]), "R2_second_half_%": oos_r2(y[half:], f[half:]),
            "MAE_gain_%": 100 * (1 - np.mean(np.abs(y - f)) / np.mean(np.abs(y))),
            "DM_MAE_p": np.nan if flat else 2 * (1 - stats.norm.cdf(abs(hac(d_mae)))),
            "ClarkWest_p": np.nan if flat else 1 - stats.norm.cdf(hac(cw)),
            "hit_%": np.nan if flat else 100 * np.mean(np.sign(f) == np.sign(y))}


FELIX = ["ret", "spread", "dxy_lag1"]
data["dxy_lag1"] = X["dxy_ret"].shift(1).reindex(data.index)
MODELS = [  # (label, columns, method, window, column name in the forecast file)
    ("No change (benchmark)", PREDICTORS, "zero", None, "no_change"),
    ("Historical mean", PREDICTORS, "mean", None, "hist_mean"),
    ("LASSO, CV  [MAIN]", PREDICTORS, "lasso", None, "ar_lasso_cv"),
    ("Ridge, CV  [check]", PREDICTORS, "ridge", None, "ar_ridge_cv"),
    ("LASSO, BIC [check]", PREDICTORS, "lasso_bic", None, "ar_lasso_bic"),
    ("LASSO, CV, rolling 10y [check]", PREDICTORS, "lasso", ROLL, "ar_lasso_cv_rolling"),
    ("Felix spec, OLS [comparison]", FELIX, "ols", None, "felix_spec_ols"),
]


def run_window(origins, targets):
    rows, fcs, kept_log = [], {}, {}
    for target in targets:
        for label, cols, method, window, _ in MODELS:
            f, kept = forecast(data, target, cols, method, origins, window)
            y = data[target].loc[f.index]
            rows.append({"target": target, "model": label, **scores(y, f)})
            fcs[(target, label)] = f
            if kept:
                kept_log[(target, label)] = pd.Series(np.mean(kept, axis=0) * 100, index=cols)
    return pd.DataFrame(rows), fcs, kept_log


# ===========================================================================
step(7, "Validation run: forecasts for Jan 2005 to Dec 2014")
# ===========================================================================
val, val_fc, val_kept = run_window(VAL_ORIGINS, ["ret_held", "ret_cont"])
cols_show = ["model", "R2_oos_%", "R2_first_half_%", "R2_second_half_%", "MAE_gain_%", "DM_MAE_p", "ClarkWest_p", "hit_%"]
for target in ["ret_held", "ret_cont"]:
    print(f"\nTarget: {target}  ({'tradable return' if target == 'ret_held' else 'raw CL1 change, shared target'})")
    print(val.loc[val.target == target, cols_show].round(2).to_string(index=False))
k = val_kept[("ret_held", "LASSO, CV  [MAIN]")].sort_values(ascending=False)
print(f"\nMain LASSO: predictors kept in at least one monthly refit (tradable target): "
      f"{', '.join(f'{c} {v:.0f}%' for c, v in k[k > 0].items()) or 'none'}")
print(f"Average number of predictors kept per month: {k.sum() / 100:.2f}")
val.to_csv(OUT / "step7_validation_scores.csv", index=False)


# ===========================================================================
step(8, "Diagnostics")
# ===========================================================================
# 8a. A small OLS with the first four predictors to enter the LASSO path (from step 6).
#     LASSO itself has no standard errors, so this readable companion regression is where
#     we run the classic tests. Fitted on pre-2015 data only.
pre = data.loc[:TRAIN_END].dropna(subset=[MAIN_TARGET])
yv, Xc = pre[MAIN_TARGET].values, sm.add_constant(pre[TOP4].values)
ols = sm.OLS(yv, Xc).fit()
nw = sm.OLS(yv, Xc).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
coef = pd.DataFrame({"coef": ols.params, "p (plain OLS)": ols.pvalues,
                     "p (Newey-West)": nw.pvalues}, index=["const"] + TOP4)
coef["VIF"] = [np.nan] + [variance_inflation_factor(Xc, j) for j in range(1, Xc.shape[1])]
split = int(np.searchsorted(pre.index.values, pd.Period("2008-12", "M")))
rss = lambda a, b: sm.OLS(a, b).fit().ssr
kx = Xc.shape[1]
chow_F = ((rss(yv, Xc) - rss(yv[:split], Xc[:split]) - rss(yv[split:], Xc[split:])) / kx) / \
         ((rss(yv[:split], Xc[:split]) + rss(yv[split:], Xc[split:])) / (len(yv) - 2 * kx))
tests = pd.Series({
    "R-squared (in sample)": ols.rsquared,
    "Ljung-Box(12) p  [autocorrelation]": acorr_ljungbox(ols.resid, lags=[12])["lb_pvalue"].iloc[0],
    "Breusch-Pagan p  [heteroskedasticity]": het_breuschpagan(ols.resid, Xc)[1],
    "White p          [heteroskedasticity]": het_white(ols.resid, Xc)[1],
    "Chow Dec 2008 p  [break]": 1 - stats.f.cdf(chow_F, kx, len(yv) - 2 * kx),
    "CUSUM p          [stability]": breaks_cusumolsresid(ols.resid, ddof=kx)[1],
})
print(f"8a. Companion OLS, {pre.index[0]} to {pre.index[-1]}, target {MAIN_TARGET}, predictors {TOP4}")
print(coef.round(3).to_string())
print(tests.round(4).to_string())

# 8b. Checks on the main LASSO's validation forecast errors
f = val_fc[("ret_held", "LASSO, CV  [MAIN]")]
err = data["ret_held"].loc[f.index] - f
print("\n8b. Main LASSO validation errors (2005-2014)")
print(f"  Ljung-Box(12) p on errors          : {acorr_ljungbox(err, lags=[12])['lb_pvalue'].iloc[0]:.3f}")
print(f"  Ljung-Box(12) p on squared errors  : {acorr_ljungbox(err ** 2, lags=[12])['lb_pvalue'].iloc[0]:.3f}  (volatility clustering)")
# origins are one month before the forecast month, so 2007-11 is the origin for Dec 2007
print(f"  Typical error (RMSE) 2005-2007 / 2008-2009 / 2010-2014: "
      f"{np.sqrt((err.loc[:'2007-11'] ** 2).mean()):.1f} / {np.sqrt((err.loc['2007-12':'2009-11'] ** 2).mean()):.1f} / "
      f"{np.sqrt((err.loc['2009-12':] ** 2).mean()):.1f} percentage points")
coef.to_csv(OUT / "step8_companion_ols.csv")
tests.to_csv(OUT / "step8_tests.csv")


# ===========================================================================
step(9, "Test run: forecasts for Jan 2015 to Jun 2024")
# ===========================================================================
if not RUN_TEST:
    print("Switched off. Freeze the specification in README.md first, then run once with --run-test.")
else:
    test, test_fc, _ = run_window(TEST_ORIGINS, [MAIN_TARGET, "ret_cont"])
    for target in [MAIN_TARGET, "ret_cont"]:
        print(f"\nTarget: {target}")
        print(test.loc[test.target == target, cols_show].round(2).to_string(index=False))
    test.to_csv(OUT / "step9_test_scores.csv", index=False)
    # Forecasts in the shared format: month = target month, actual, one column per model
    for target in [MAIN_TARGET, "ret_cont"]:
        origins_used = test_fc[(target, MODELS[0][0])].index
        out = pd.DataFrame({"month": [str(p + 1) for p in origins_used],      # month being forecast
                            "actual": data[target].loc[origins_used].values})
        for label, *_, colname in MODELS:
            out[colname] = test_fc[(target, label)].values
        out.to_csv(OUT / f"step9_test_forecasts_{target}.csv", index=False)
    print(f"\nSaved forecasts and scores to {OUT}")
