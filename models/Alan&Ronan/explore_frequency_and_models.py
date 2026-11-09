"""
Alan & Ronan: frequency choice and model shortlist (exploration only).

What this script does
---------------------
1. Builds CL1 return series at daily, weekly and monthly frequency.
   Two versions of each:
     - "continuous": the % change in the CL1 series itself (the shared target).
     - "held": the % change from holding the same futures contract, which removes
       the jump that appears when CL1 switches to the next contract (the roll).
2. Compares how returns behave at each frequency (volatility, fat tails,
   autocorrelation, stationarity, 2020, roll effect).
3. Tests simple predictability at each frequency with expanding-window forecasts.
4. Compares candidate monthly models (module methods only).

Look-ahead rules used here
--------------------------
- All model comparison uses a VALIDATION window, Jan 2005 to Dec 2014.
  The shared TEST window (Jan 2015 to Jun 2024) is never touched, so it stays
  a genuine out-of-sample test for the final model.
- Every predictor is lagged to when it would have been known (see LAGS below).
- Models are refitted each period on data up to the forecast origin only.

Run from the repository root:
    python "models/Alan&Ronan/explore_frequency_and_models.py"
"""

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller, acf
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.arima.model import ARIMA
import statsmodels.api as sm
from sklearn.linear_model import LassoCV, RidgeCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"
OUT = ROOT / "data" / "results" / "Alan&Ronan" / "exploration"
OUT.mkdir(parents=True, exist_ok=True)

VAL_START, VAL_END = "2005-01-01", "2014-12-31"   # validation window (model choice)
PERIODS_PER_YEAR = {"daily": 252, "weekly": 52, "monthly": 12}
LB_LAGS = {"daily": 20, "weekly": 13, "monthly": 12}   # roughly one month / quarter / year


# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
daily = pd.read_csv(CLEAN / "industry_daily.csv", parse_dates=["date"]).set_index("date")
weekly_raw = pd.read_csv(CLEAN / "industry_weekly.csv", parse_dates=["date"]).set_index("date")
monthly = pd.read_csv(CLEAN / "monthly_observations.csv")
monthly["month"] = pd.PeriodIndex(monthly["month"], freq="M")
monthly = monthly.set_index("month")


# ---------------------------------------------------------------------------
# 2. Roll dates
# ---------------------------------------------------------------------------
# CL1 is a rolling front-month series. WTI futures stop trading 3 business days
# before the 25th of the month (4 if the 25th is not a business day). The day
# after that, CL1 switches to the contract that used to be CL2.
# The workbook gives no roll calendar, so we apply the exchange rule
# (ignoring holidays). This is an approximation for daily and weekly data.
def roll_days(trading_days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    out = []
    for p in pd.period_range(trading_days.min().to_period("M"),
                             trading_days.max().to_period("M"), freq="M"):
        d25 = pd.Timestamp(p.year, p.month, 25)
        n = 3 if d25.dayofweek < 5 else 4
        last_trade = d25 - pd.offsets.BDay(n)
        after = trading_days[trading_days > last_trade]
        if len(after):
            out.append(after[0])
    return pd.DatetimeIndex(out)


ROLLS = roll_days(daily.index)


# ---------------------------------------------------------------------------
# 3. Return series at each frequency (in %)
# ---------------------------------------------------------------------------
def daily_returns() -> pd.DataFrame:
    c1, c2 = daily["cl1"], daily["cl2"]
    is_roll = daily.index.isin(ROLLS)
    cont = 100 * (c1 / c1.shift() - 1)
    held = 100 * pd.Series(np.where(is_roll, c1 / c2.shift() - 1, c1 / c1.shift() - 1),
                           index=daily.index)
    df = pd.DataFrame({"cont": cont, "held": held, "cl1": c1, "cl2": c2})
    # 20-21 April 2020: CL1 settled at -37.63. Simple % returns across a negative
    # price are meaningless, so these two days are dropped from daily analysis.
    bad = df.index.isin(pd.to_datetime(["2020-04-20", "2020-04-21"]))
    return df.loc[~bad].iloc[1:]


def weekly_returns() -> pd.DataFrame:
    # Weekly sheet dates are Fridays. Take the last daily close on or before each Friday.
    fridays = weekly_raw.index
    px = daily[["cl1", "cl2"]].reindex(daily.index.union(fridays)).ffill().loc[fridays]
    # Did a roll happen during the week (previous Friday, this Friday]?
    roll_in_week = pd.Series(False, index=fridays)
    for i in range(1, len(fridays)):
        roll_in_week.iloc[i] = ((ROLLS > fridays[i - 1]) & (ROLLS <= fridays[i])).any()
    cont = 100 * (px["cl1"] / px["cl1"].shift() - 1)
    held = 100 * pd.Series(np.where(roll_in_week, px["cl1"] / px["cl2"].shift() - 1,
                                    px["cl1"] / px["cl1"].shift() - 1), index=fridays)
    df = pd.DataFrame({"cont": cont, "held": held, "cl1": px["cl1"], "cl2": px["cl2"]})
    return df.join(weekly_raw).iloc[1:]


def monthly_returns() -> pd.DataFrame:
    c1, c2 = monthly["industry__cl1"], monthly["industry__cl2"]
    # At each month-end, CL1 expires around the 20th of the following month.
    # So the contract that is CL2 at the end of month t is CL1 at the end of t+1.
    # That makes the held-contract return exact at monthly frequency.
    cont = 100 * (c1 / c1.shift() - 1)
    held = 100 * (c1 / c2.shift() - 1)
    df = pd.DataFrame({"cont": cont, "held": held, "cl1": c1, "cl2": c2})
    return df.join(monthly.drop(columns=["industry__cl1", "industry__cl2"])).iloc[1:]


R = {"daily": daily_returns(), "weekly": weekly_returns(), "monthly": monthly_returns()}


# ---------------------------------------------------------------------------
# 4. Descriptive comparison across frequencies
# ---------------------------------------------------------------------------
def year_of(index) -> np.ndarray:
    return index.year if isinstance(index, pd.DatetimeIndex) else index.year


rows = []
for freq, df in R.items():
    for kind in ["cont", "held"]:
        r = df[kind].dropna()
        log_level = np.log(df["cl1"].clip(lower=0.01))
        sq = r ** 2
        rows.append({
            "frequency": freq,
            "target": kind,
            "n_obs": len(r),
            "obs_per_year": PERIODS_PER_YEAR[freq],
            "obs_before_2015": int((year_of(r.index) < 2015).sum()),
            "sd_pct": r.std(),
            "annualised_vol_pct": r.std() * np.sqrt(PERIODS_PER_YEAR[freq]),
            "skew": stats.skew(r),
            "excess_kurtosis": stats.kurtosis(r),
            "acf_lag1": acf(r, nlags=1)[1],
            "ljungbox_p": acorr_ljungbox(r, lags=[LB_LAGS[freq]])["lb_pvalue"].iloc[0],
            "ljungbox_sq_p": acorr_ljungbox(sq, lags=[LB_LAGS[freq]])["lb_pvalue"].iloc[0],
            "adf_p_returns": adfuller(r, autolag="AIC")[1],
            "adf_p_log_price": adfuller(log_level.dropna(), autolag="AIC")[1],
            "share_sq_returns_2020": sq[year_of(sq.index) == 2020].sum() / sq.sum(),
            "roll_gap_var_share": ((df["cont"] - df["held"]).var() / df["cont"].var())
                                  if kind == "cont" else np.nan,
        })
desc = pd.DataFrame(rows)
desc.to_csv(OUT / "frequency_descriptives.csv", index=False)


# ---------------------------------------------------------------------------
# 5. Predictors at each frequency, lagged to when they were known
# ---------------------------------------------------------------------------
# LAGS (number of periods between the observation's label and the forecast origin):
# daily  : only CL1/CL2 are usable. Daily Brent, crack and BDI do not line up with
#          their monthly versions at any shift and the sheet has 534 undated Brent rows.
# weekly : EIA stocks/production come out the Wednesday after the week ends, and
#          CFTC positions on Friday after the close, so fundamentals are lagged 1 week.
# monthly: market prices (CL1, CL2, Brent, crack, BDI, VIX, SPX, DXY) known at month-end, lag 0.
#          Inventories, production, rigs, positions, CPI, IP lagged 1 month (release delay).
#          Treasury yields are labelled one month EARLY in the workbook (the value
#          labelled t is the end of t+1), so they are lagged 2 labels.
def daily_predictors(df):
    X = pd.DataFrame(index=df.index)
    X["own_ret"] = df["held"]
    X["carry"] = 100 * (df["cl1"] / df["cl2"] - 1)       # >0 backwardation, <0 contango
    return X


def weekly_predictors(df):
    X = pd.DataFrame(index=df.index)
    X["own_ret"] = df["held"]
    X["carry"] = 100 * (df["cl1"] / df["cl2"] - 1)
    X["stock_chg"] = df["crude_stock_change_source_units"].shift(1)
    X["prod_chg"] = df["crude_production_source_units"].pct_change().mul(100).shift(1)
    X["rig_chg"] = df["rig_count"].pct_change().mul(100).shift(1)
    net = (df["commercial_long_unimputed"] - df["commercial_short"]) / \
          (df["commercial_long_unimputed"] + df["commercial_short"])
    X["net_comm_chg"] = net.diff().mul(100).shift(1)
    return X


def monthly_predictors(df):
    X = pd.DataFrame(index=df.index)
    X["own_ret"] = df["held"]
    X["carry"] = 100 * (df["cl1"] / df["cl2"] - 1)
    X["brent_wti"] = 100 * (df["industry__brent"] / df["cl1"] - 1)
    X["crack_chg"] = df["industry__crack_spread_321"].diff()
    X["bdi_chg"] = df["industry__baltic_dry_index"].pct_change().mul(100)
    X["vix_chg"] = df["macro__vix"].diff()
    X["spx_ret"] = df["macro__sp500_index"].pct_change().mul(100)
    X["dxy_ret"] = df["macro__dxy_return_pct"]
    X["inv_chg"] = df["industry__inventories_source_units"].pct_change().mul(100).shift(1)
    X["prod_chg"] = df["industry__crude_production_source_units"].pct_change().mul(100).shift(1)
    X["rig_chg"] = df["industry__rig_count"].pct_change().mul(100).shift(1)
    net = (df["industry__commercial_long"] - df["industry__commercial_short"]) / \
          (df["industry__commercial_long"] + df["industry__commercial_short"])
    X["net_comm_chg"] = net.diff().mul(100).shift(1)
    X["ip_growth"] = df["macro__industrial_production_index"].pct_change().mul(100).shift(1)
    X["cpi_chg"] = df["macro__cpi_yoy_pct"].diff().shift(1)
    X["term_spread"] = (df["macro__treasury_10y_yield_pct"]
                        - df["macro__treasury_3m_yield_pct"]).shift(2)
    X["y3m_chg"] = df["macro__treasury_3m_yield_pct"].diff().shift(2)
    return X


PRED = {"daily": daily_predictors(R["daily"]),
        "weekly": weekly_predictors(R["weekly"]),
        "monthly": monthly_predictors(R["monthly"])}


# ---------------------------------------------------------------------------
# 6. Expanding-window forecasting helpers
# ---------------------------------------------------------------------------
def target_dates(freq):
    """Date of the period being forecast from each origin (the next row)."""
    idx = R[freq].index
    ts = idx.to_timestamp(how="end") if isinstance(idx, pd.PeriodIndex) else idx
    return pd.Series(ts, index=idx).shift(-1)


def make_xy(freq, target, cols):
    """Row t holds predictors known at t and the return over the NEXT period."""
    X = PRED[freq][cols]
    y_next = R[freq][target].shift(-1).rename("y_next")
    return X.join(y_next).dropna()


def in_window(index, start, end, freq=None):
    """True where the forecast TARGET period falls inside [start, end]."""
    freq = freq or ("monthly" if isinstance(index, pd.PeriodIndex)
                    else ("weekly" if (pd.Series(index).diff().dt.days.median() >= 6) else "daily"))
    td = target_dates(freq).reindex(index)
    return ((td >= pd.Timestamp(start)) & (td <= pd.Timestamp(end) + pd.Timedelta(hours=23))).values


def expanding_forecasts(data, fit_predict, val_mask):
    """For each origin t in the validation window, fit on rows < t, predict row t."""
    preds = pd.Series(np.nan, index=data.index)
    X = data.drop(columns="y_next").values
    y = data["y_next"].values
    for i in np.where(val_mask)[0]:
        preds.iloc[i] = fit_predict(X[:i], y[:i], X[i:i + 1])
    return preds


def ols_fp(Xtr, ytr, Xte):
    A = np.column_stack([np.ones(len(Xtr)), Xtr])
    beta = np.linalg.lstsq(A, ytr, rcond=None)[0]
    return float(np.r_[1.0, Xte[0]] @ beta)


def mean_fp(Xtr, ytr, Xte):
    return float(ytr.mean())


def clark_west_p(y, f_model):
    """One-sided Clark-West test of model vs the zero forecast (HAC errors)."""
    e0, e1 = y, y - f_model
    adj = e0 ** 2 - (e1 ** 2 - f_model ** 2)
    res = sm.OLS(adj, np.ones(len(adj))).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    return 1 - stats.norm.cdf(res.tvalues[0])


def score(y, f):
    e = y - f
    return {"n": len(y),
            "rmse": np.sqrt(np.mean(e ** 2)),
            "mae": np.mean(np.abs(e)),
            "oos_r2_vs_zero_pct": 100 * (1 - np.sum(e ** 2) / np.sum(y ** 2)),
            "hit_rate_pct": 100 * np.mean(np.sign(f) == np.sign(y)) if np.any(f != 0) else np.nan,
            "clark_west_p": clark_west_p(y, f) if np.any(f != 0) else np.nan}


# ---------------------------------------------------------------------------
# 7. Predictability by frequency (validation window only)
# ---------------------------------------------------------------------------
pred_rows = []
for freq in ["daily", "weekly", "monthly"]:
    all_cols = list(PRED[freq].columns)
    specs = {"AR(1)": ["own_ret"], "Carry only": ["carry"], "All predictors OLS": all_cols}
    for target in ["held", "cont"]:
        base = make_xy(freq, target, all_cols)
        mask = in_window(base.index, VAL_START, VAL_END, freq)
        y = base["y_next"][mask].values
        pred_rows.append({"frequency": freq, "target": target, "model": "No change",
                          **score(y, np.zeros_like(y))})
        for name, cols in specs.items():
            data = base[cols + ["y_next"]]
            f = expanding_forecasts(data, ols_fp, mask)[mask].values
            pred_rows.append({"frequency": freq, "target": target, "model": name,
                              "n_predictors": len(cols), **score(y, f)})
predictability = pd.DataFrame(pred_rows)
predictability.to_csv(OUT / "predictability_by_frequency.csv", index=False)


# ---------------------------------------------------------------------------
# 8. Candidate monthly models (validation window only)
# ---------------------------------------------------------------------------
ALL_M = list(PRED["monthly"].columns)
SUPPLY_DEMAND = ["own_ret", "inv_chg", "prod_chg", "rig_chg", "crack_chg", "ip_growth"]


def lasso_fp_factory(selection_log):
    def fp(Xtr, ytr, Xte):
        model = make_pipeline(StandardScaler(),
                              LassoCV(cv=TimeSeriesSplit(n_splits=5), alphas=60,
                                      max_iter=20000, random_state=0))
        model.fit(Xtr, ytr)
        selection_log.append(model[-1].coef_ != 0)
        return float(model.predict(Xte)[0])
    return fp


def ridge_fp(Xtr, ytr, Xte):
    model = make_pipeline(StandardScaler(),
                          RidgeCV(alphas=np.logspace(-2, 4, 60),
                                  cv=TimeSeriesSplit(n_splits=5)))
    model.fit(Xtr, ytr)
    return float(model.predict(Xte)[0])


def arima_order_by_bic(y_train):
    best = None
    for p in range(3):
        for q in range(3):
            try:
                bic = ARIMA(y_train, order=(p, 0, q), trend="c").fit().bic
            except Exception:
                continue
            if best is None or bic < best[0]:
                best = (bic, (p, 0, q))
    return best[1]


model_rows, lasso_tables = [], {}
for target in ["held", "cont"]:
    base = make_xy("monthly", target, ALL_M)
    mask = in_window(base.index, VAL_START, VAL_END, "monthly")
    y = base["y_next"][mask].values
    first_val = np.where(mask)[0][0]

    results = {"No change": np.zeros_like(y)}
    results["Historical mean"] = expanding_forecasts(base[["own_ret", "y_next"]], mean_fp, mask)[mask].values
    results["AR(1)"] = expanding_forecasts(base[["own_ret", "y_next"]], ols_fp, mask)[mask].values

    # ARIMA: order chosen by BIC on the pre-validation sample, re-estimated each month
    order = arima_order_by_bic(base["y_next"].values[:first_val])
    f_arima = []
    yy = base["y_next"].values
    for i in np.where(mask)[0]:
        fit = ARIMA(yy[:i], order=order, trend="c").fit()
        f_arima.append(float(fit.forecast(1)[0]))
    results[f"ARIMA{order} by BIC"] = np.array(f_arima)

    felix = PRED["monthly"][["own_ret", "carry"]].assign(dxy_lag=PRED["monthly"]["dxy_ret"].shift(1))
    felix = felix.join(R["monthly"][target].shift(-1).rename("y_next")).dropna().loc[base.index]
    results["Felix spec (OLS)"] = expanding_forecasts(felix, ols_fp, mask)[mask].values
    results["Supply-demand ARX"] = expanding_forecasts(base[SUPPLY_DEMAND + ["y_next"]], ols_fp, mask)[mask].values
    results["All predictors OLS"] = expanding_forecasts(base, ols_fp, mask)[mask].values

    log = []
    results["LASSO (time-series CV)"] = expanding_forecasts(base, lasso_fp_factory(log), mask)[mask].values
    lasso_tables[target] = pd.Series(np.mean(log, axis=0) * 100, index=ALL_M).sort_values(ascending=False)
    results["Ridge (time-series CV)"] = expanding_forecasts(base, ridge_fp, mask)[mask].values

    for name, f in results.items():
        model_rows.append({"target": target, "model": name, **score(y, f)})

models = pd.DataFrame(model_rows)
models.to_csv(OUT / "monthly_model_validation.csv", index=False)
lasso_sel = pd.DataFrame(lasso_tables).rename(columns=lambda c: f"selected_pct_{c}")
lasso_sel.to_csv(OUT / "lasso_selection_frequency.csv")

# ---------------------------------------------------------------------------
# 8b. LASSO extras: which predictors enter first, and AIC/BIC tuning
# ---------------------------------------------------------------------------
# The LASSO path shows the order in which predictors enter as the penalty is
# relaxed. The first to enter are the ones with the strongest (if weak) signal.
# Uses data up to Nov 2014 only, so the test window is still untouched.
from sklearn.linear_model import lasso_path, LassoLarsIC

entry_rows, ic_rows = [], []
for target in ["held", "cont"]:
    base = make_xy("monthly", target, ALL_M)
    pre = base.loc[:pd.Period("2014-11", "M")]
    Xs = StandardScaler().fit_transform(pre[ALL_M].values)
    ys = pre["y_next"].values - pre["y_next"].mean()
    alphas, coefs, _ = lasso_path(Xs, ys, n_alphas=200)
    for j, c in enumerate(ALL_M):
        nz = np.nonzero(coefs[j])[0]
        entry_rows.append({"target": target, "predictor": c,
                           "entry_penalty": alphas[nz[0]] if len(nz) else 0.0,
                           "sign_when_entering": np.sign(coefs[j, nz[0]]) if len(nz) else 0})
    mask = in_window(base.index, VAL_START, VAL_END, "monthly")
    y = base["y_next"][mask].values
    for crit in ["aic", "bic"]:
        kept = []

        def ic_fp(Xtr, ytr, Xte, crit=crit, kept=kept):
            sc = StandardScaler().fit(Xtr)
            m = LassoLarsIC(criterion=crit).fit(sc.transform(Xtr), ytr)
            kept.append(np.sum(m.coef_ != 0))
            return float(m.predict(sc.transform(Xte))[0])

        f = expanding_forecasts(base, ic_fp, mask)[mask].values
        ic_rows.append({"target": target, "model": f"LASSO ({crit.upper()})",
                        "avg_predictors_kept": np.mean(kept), **score(y, f)})

lasso_entry = (pd.DataFrame(entry_rows)
               .sort_values(["target", "entry_penalty"], ascending=[True, False]))
lasso_entry.to_csv(OUT / "lasso_entry_order.csv", index=False)
lasso_ic = pd.DataFrame(ic_rows)
lasso_ic.to_csv(OUT / "lasso_ic_validation.csv", index=False)

# Stationarity of the monthly predictors (ADF p-values, full sample)
adf_x = {c: adfuller(PRED["monthly"][c].dropna(), autolag="AIC")[1] for c in ALL_M}
pd.Series(adf_x, name="adf_p").to_csv(OUT / "monthly_predictor_adf.csv")


# ---------------------------------------------------------------------------
# 9. Print a summary
# ---------------------------------------------------------------------------
pd.set_option("display.width", 200, "display.max_columns", 30)
print("\n=== Return behaviour by frequency ===")
print(desc.round(3).to_string(index=False))
print("\n=== Predictability by frequency (validation 2005-2014) ===")
print(predictability.round(3).to_string(index=False))
print("\n=== Monthly candidate models (validation 2005-2014) ===")
print(models.round(3).to_string(index=False))
print("\n=== LASSO: % of monthly refits in which each predictor was kept ===")
print(lasso_sel.round(0).to_string())
print("\n=== LASSO entry order (first rows = strongest signal) ===")
print(lasso_entry.groupby("target").head(6).round(3).to_string(index=False))
print("\n=== LASSO tuned by AIC / BIC (validation 2005-2014) ===")
print(lasso_ic.round(3).to_string(index=False))
print("\n=== ADF p-values, monthly predictors ===")
print(pd.Series(adf_x).round(4).to_string())
