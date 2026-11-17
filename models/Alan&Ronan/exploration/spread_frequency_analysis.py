"""
Weekly vs monthly: which frequency suits a CL1-CL2 calendar spread model?

Starts from the raw workbook (Oil Data.xlsx). Builds the spread at Friday and
month-end sampling, checks its econometric properties, measures how contract
rolls contaminate each series, and runs three small forecasting models on the
VALIDATION period only (2005-2014). The 2015-2024 test period is never touched,
so choosing a frequency here does not peek at the test sample.

Spread definition: S = CL1 - CL2 in $/bbl.
    S > 0  backwardation (prompt barrel dearer, tight market)
    S < 0  contango (prompt barrel cheaper, ample storage)

Run from models/Alan&Ronan/exploration:  python spread_frequency_analysis.py   (reads data/raw/Oil Data.xlsx)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, kpss, acf
from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
import warnings

warnings.filterwarnings("ignore")
XLSX = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[3] / "data" / "raw" / "Oil Data.xlsx")
OUT = Path(__file__).parent
TRAIN_START = "1995-01-01"   # first year all inputs exist
VAL_START, VAL_END = "2005-01-01", "2014-12-31"   # group's validation window


def load(sheet):
    df = pd.read_excel(XLSX, sheet_name=sheet)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Date"]).sort_values("Date").set_index("Date")


# ---------------------------------------------------------------- 1. data
daily = load("Industry_D")[["CL1", "CL2"]].dropna()
weekly_fund = load("Industry_W")
monthly_ind = load("Industry_M")

# ---------------------------------------------------------------- 2. expiries
# NYMEX WTI rule: trading stops 3 business days before the 25th calendar day
# of the month before delivery (4 business days if the 25th is not a business
# day). Trading days in the daily file stand in for the business calendar.
tdays = daily.index


def expiry_for(year, month):
    d25 = pd.Timestamp(year, month, 25)
    before = tdays[(tdays < d25) & (tdays >= d25 - pd.Timedelta(days=20))]
    k = 3 if d25 in tdays else 4
    return before[-k] if len(before) >= k else pd.NaT


expiries = pd.DatetimeIndex(
    [expiry_for(y, m) for y in range(1990, 2025) for m in range(1, 13)]
).dropna()
expiries = expiries[(expiries >= tdays[0]) & (expiries <= tdays[-1])]

# Cross-check: the day after each computed expiry should show a jump in the
# generic spread (CL1 switches contract). Compare |change in S| on those days
# with all other days.
dS_daily = (daily.CL1 - daily.CL2).diff().abs()
roll_days = tdays[np.searchsorted(tdays, expiries, side="right").clip(max=len(tdays) - 1)]
is_roll = dS_daily.index.isin(roll_days)
print(f"Expiry calendar check: median |daily change in S| is "
      f"{dS_daily[is_roll].median():.3f} on roll days vs "
      f"{dS_daily[~is_roll].median():.3f} on other days ({len(expiries)} expiries)\n")


def days_to_expiry(dates):
    """Trading days from each date to the expiry of the contract CL1 holds."""
    idx = np.searchsorted(expiries, dates, side="left")
    e = expiries[idx.clip(max=len(expiries) - 1)]
    return np.array([((tdays > d) & (tdays <= x)).sum() for d, x in zip(dates, e)])


def rolled_between(prev, cur):
    """True if CL1 changed contract between two sampling dates."""
    return np.array([((expiries >= p) & (expiries < c)).any() for p, c in zip(prev, cur)])


# ---------------------------------------------------------------- 3. sampling
def sample(rule):
    s = daily.resample(rule).last().dropna()
    last_day = daily["CL1"].resample(rule).apply(lambda x: x.index[-1] if len(x) else pd.NaT)
    s["obs_date"] = last_day.reindex(s.index)
    s["S"] = s.CL1 - s.CL2
    s["dS"] = s.S.diff()
    s["dte"] = days_to_expiry(pd.DatetimeIndex(s.obs_date))
    prev = s.obs_date.shift()
    s["roll"] = np.r_[False, rolled_between(prev.iloc[1:], s.obs_date.iloc[1:])]
    return s.loc[TRAIN_START:"2024-06-30"]


W = sample("W-FRI")
M = sample("ME")

pre = lambda df: df.loc[:"2014-12-31"]   # diagnostics use pre-test data only


# ---------------------------------------------------------------- 4. properties
def props(df, label, per_year):
    d = pre(df)
    S, dS = d.S, d.dS.dropna()
    out = {}
    out["obs (1995-2014)"] = len(d)
    out["obs in test window 2015-Jun24"] = len(df.loc["2015":"2024-06"])
    out["mean S ($)"] = S.mean()
    out["sd S ($)"] = S.std()
    out["sd dS ($)"] = dS.std()
    out["ADF p, level S"] = adfuller(S, autolag="AIC")[1]
    out["KPSS p, level S"] = kpss(S, nlags="auto")[1]
    out["ADF p, dS"] = adfuller(dS, autolag="AIC")[1]
    rho = sm.OLS(S.values[1:], sm.add_constant(S.values[:-1])).fit().params[1]
    out["AR(1) rho on level"] = rho
    out["half-life (periods)"] = np.log(0.5) / np.log(rho)
    out["half-life (weeks)"] = out["half-life (periods)"] * 52 / per_year
    a = acf(dS, nlags=4)
    for k in (1, 2, 4):
        out[f"ACF dS lag {k}"] = a[k]
    out["Ljung-Box p (4 lags) dS"] = acorr_ljungbox(dS, lags=[4]).lb_pvalue.iloc[0]
    out["ARCH-LM p (4 lags) dS"] = het_arch(dS - dS.mean(), nlags=4)[1]
    out["excess kurtosis dS"] = dS.kurt()
    out["share of changes spanning a roll"] = d.roll.iloc[1:].mean()
    out["sd dS roll periods"] = d.loc[d.roll, "dS"].std()
    out["sd dS non-roll periods"] = d.loc[~d.roll, "dS"].std()
    nr = d.loc[~d.roll, "dS"].dropna()
    out["ACF dS lag 1, non-roll only"] = nr.autocorr(1) if len(nr) > 10 else np.nan
    out["days-to-expiry range"] = f"{d.dte.min()}-{d.dte.max()}"
    return pd.Series(out, name=label)


table = pd.concat([props(W, "Weekly", 52), props(M, "Monthly", 12)], axis=1)
pd.set_option("display.float_format", lambda v: f"{v:,.3f}")
print("=== Spread properties, 1995-2014 ===")
print(table.to_string(), "\n")

# Does the weekly spread level depend on where we are in the roll cycle?
d = pre(W).copy()
d["bucket"] = pd.cut(d.dte, [-1, 5, 10, 15, 25], labels=["0-5", "6-10", "11-15", "16+"])
print("=== Weekly: spread by trading days to CL1 expiry (1995-2014) ===")
print(d.groupby("bucket", observed=True).agg(n=("S", "size"), mean_S=("S", "mean"),
                                             sd_dS=("dS", "std")).to_string(), "\n")
r = sm.OLS(d.S, sm.add_constant(d[["dte"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
print(f"S on days-to-expiry: slope {r.params['dte']:.4f} $/day, HAC p = {r.pvalues['dte']:.3f}\n")

# Big outliers and where they fall
for lab, df in (("Weekly", W), ("Monthly", M)):
    z = (df.dS - df.dS.mean()) / df.dS.std()
    big = df.loc[z.abs() > 4, ["S", "dS", "roll", "dte"]]
    print(f"{lab}: {len(big)} changes beyond 4 sd (full sample to Jun 2024); "
          f"{int(big.roll.sum())} of them span a roll")
    print(big.round(2).to_string(), "\n")

# ---------------------------------------------------------------- 5. predictors
# Weekly: EIA crude stock change for week ending Friday t is published the
# following Wednesday, so at Friday t we can only use week t-1. Lag 1 week.
wf = weekly_fund.rename(columns={"Weekly change in Crude Stock": "dstock"})
W["dstock_lag"] = wf["dstock"].reindex(W.index, method="ffill").shift(1) / 1000  # mn bbl
# Monthly: inventories released with ~1 month lag (group dictionary).
inv = monthly_ind["Inventories"].copy()
inv.index = inv.index.to_period("M").to_timestamp("M")
M["inv_growth_lag"] = (100 * inv.pct_change()).reindex(M.index).shift(1)


# ---------------------------------------------------------------- 6. forecasts
def evaluate(df, xcols, label, drop_roll=False):
    # drop_roll=True: train AND evaluate only on weeks where CL1 does not
    # change contract, so the target is the P&L of holding the same spread.
    """Expanding-window one-step forecasts of next period's spread change."""
    data = df.copy()
    data["y"] = data.dS.shift(-1)          # change from t to t+1
    data["roll_next"] = data.roll.shift(-1)
    data = data.dropna(subset=["y"] + xcols)
    val = data.loc[VAL_START:VAL_END]
    preds = []
    for t in val.index:
        tr = data.loc[:t].iloc[:-1]        # targets known by t only
        tr = tr[tr.index < t]
        if drop_roll:
            tr = tr[~tr.roll_next.astype(bool)]
        # the last training row's target (dS at t) is known at t: fine
        X = sm.add_constant(tr[xcols]) if xcols else np.ones((len(tr), 1))
        b = sm.OLS(tr.y.values, X).fit().params
        x_t = np.r_[1.0, data.loc[t, xcols].values.astype(float)] if xcols else np.array([1.0])
        preds.append(x_t @ b)
    val = val.assign(pred=preds)
    if drop_roll:
        val = val[~val.roll_next.astype(bool)]
    e_m, e_0 = val.y - val.pred, val.y
    r2 = 1 - (e_m ** 2).sum() / (e_0 ** 2).sum()
    hit = (np.sign(val.pred) == np.sign(val.y))[val.y != 0].mean()
    return {"model": label, "n": len(val), "RMSE model": np.sqrt((e_m ** 2).mean()),
            "RMSE no-change": np.sqrt((e_0 ** 2).mean()), "OOS R2 vs no-change": r2,
            "direction hit": hit}


rows = []
for lab, df, inv_col in (("Weekly", W, "dstock_lag"), ("Monthly", M, "inv_growth_lag")):
    rows.append({"freq": lab, **evaluate(df, [], "constant only")})
    rows.append({"freq": lab, **evaluate(df, ["S"], "AR on level (mean reversion)")})
    rows.append({"freq": lab, **evaluate(df, ["S", inv_col], "AR + lagged inventory")})
    if lab == "Weekly":
        # Expiry dates are fixed in advance, so knowing next week is a roll
        # week is not look-ahead.
        df["roll_next_x"] = df.roll.shift(-1).astype(float)
        df["S_x_roll"] = df.S * df.roll_next_x
        rows.append({"freq": lab, **evaluate(df, ["S", "roll_next_x", "S_x_roll"], "AR + roll-week terms")})
        rows.append({"freq": lab, **evaluate(df, [], "constant, non-roll weeks only", drop_roll=True)})
        rows.append({"freq": lab, **evaluate(df, ["S"], "AR, non-roll weeks only", drop_roll=True)})
        rows.append({"freq": lab, **evaluate(df, ["S", inv_col], "AR + inventory, non-roll weeks only", drop_roll=True)})
        rows.append({"freq": lab, **evaluate(df, ["dS"], "momentum (last change), non-roll weeks only", drop_roll=True)})
    else:
        rows.append({"freq": lab, **evaluate(df, ["dS"], "momentum (last change)")})
res = pd.DataFrame(rows)
print("=== Validation 2005-2014, expanding window, target = next-period change in S ($) ===")
print(res.to_string(index=False), "\n")
print("Note: RMSE levels are not comparable across frequencies (different horizons).")
print("Compare each model with its own no-change benchmark via OOS R2.")

# Save series for plotting / reuse
W.to_csv(OUT / "spread_weekly.csv")
M.to_csv(OUT / "spread_monthly.csv")
