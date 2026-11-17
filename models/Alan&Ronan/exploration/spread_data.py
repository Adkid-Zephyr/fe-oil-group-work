"""Shared data and helpers for the CL1-CL2 spread scripts (release lags, expiries, panels)."""

import sys, itertools, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV, RidgeCV
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings("ignore")
XLSX = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[3] / "data" / "raw" / "Oil Data.xlsx")
OUT = Path(__file__).parent
VAL = ("2005-01-01", "2014-12-31")
HALF = "2009-12-31"


def load(sheet):
    df = pd.read_excel(XLSX, sheet_name=sheet)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.dropna(subset=["Date"]).sort_values("Date").set_index("Date")


# ------------------------------------------------------------------ raw data
daily = load("Industry_D").rename(columns={"CRKS321C Index": "crack", "BDIY Index": "bdi"})
daily = daily[["CL1", "CL2", "Brent", "crack", "bdi"]].dropna(subset=["CL1", "CL2"])
wk = load("Industry_W").rename(columns={
    "Weekly Prod Crude": "prod", "Weekly Rig Count": "rigs",
    "Weekly change in Crude Stock": "dstock", "Weekly Commercial Long": "cl",
    "Weekly Commercial Short": "cs", "Weekly Total Open Interest": "oi"})
mi = load("Industry_M"); mi.index = mi.index.to_period("M").to_timestamp("M")
ma = load("Macro_M"); ma.index = ma.index.to_period("M").to_timestamp("M")

# ------------------------------------------------------------------ expiries
tdays = daily.index


def expiry_for(y, m):
    d25 = pd.Timestamp(y, m, 25)
    before = tdays[(tdays < d25) & (tdays >= d25 - pd.Timedelta(days=20))]
    k = 3 if d25 in tdays else 4
    return before[-k] if len(before) >= k else pd.NaT


expiries = pd.DatetimeIndex([expiry_for(y, m) for y in range(1990, 2025)
                             for m in range(1, 13)]).dropna()

# ------------------------------------------------------------------ weekly fundamentals (native weekly)
# Release timing, conservative:
#   EIA stocks and production: week ending Friday F published Wednesday F+5
#   COT positions and rig count: treat as usable 7 days after the sheet date
wk["net_comm"] = 100 * (wk.cl - wk.cs) / wk.oi
native = pd.DataFrame({
    "inv1": wk.dstock / 1000,                       # mn bbl, latest week
    "inv4": wk.dstock.rolling(4).sum() / 1000,      # mn bbl, last 4 weeks
    "prod1": wk["prod"].diff(), "prod4": wk["prod"].diff(4),
    "rig1": wk.rigs.diff(), "rig4": wk.rigs.diff(4),
    "cot1": wk.net_comm, "dcot1": wk.net_comm.diff(), "dcot4": wk.net_comm.diff(4),
    "oi1": 100 * wk.oi.pct_change(), "oi4": 100 * wk.oi.pct_change(4),
})
release_days = {"inv1": 5, "inv4": 5, "prod1": 5, "prod4": 5}   # others 7


def known_at(dates, col):
    lag = pd.Timedelta(days=release_days.get(col, 7))
    s = native[col].dropna()
    pos = np.searchsorted(s.index, pd.DatetimeIndex(dates) - lag, side="right") - 1
    out = np.where(pos >= 0, s.values[pos.clip(0)], np.nan)
    return out


# monthly macro: usable after month-end plus the dictionary's release lag
macro = pd.DataFrame({
    "dxy": 100 * ma["DXY returns"], "vix": ma["VIX"],
    "term": ma["10Y Yield"] - ma["3M Yield"],
    "ipg": 100 * ma["IndustrialProduction Index"].pct_change(),
})
macro_lag = {"dxy": 0, "vix": 0, "term": 1, "ipg": 1}


def macro_known(dates, col):
    s = macro[col].dropna()
    avail = s.index + pd.offsets.MonthEnd(macro_lag[col])
    pos = np.searchsorted(avail, pd.DatetimeIndex(dates), side="right") - 1
    return np.where(pos >= 0, s.values[pos.clip(0)], np.nan)


# ------------------------------------------------------------------ panel per frequency
def panel(rule):
    g = daily.resample(rule)
    p = g.last().dropna(subset=["CL1", "CL2"])
    p["obs"] = daily.index.to_series().resample(rule).last().reindex(p.index)
    p = p.loc["1995":"2024-06-30"]
    obs = pd.DatetimeIndex(p.obs)
    p["S"] = p.CL1 - p.CL2
    p["s_pct"] = 100 * (p.CL1 / p.CL2 - 1)
    roll = [((expiries >= a) & (expiries < b)).any() for a, b in zip(obs[:-1], obs[1:])]
    p["roll"] = [False] + roll                      # roll between t-1 and t
    p["roll_next"] = p.roll.shift(-1)               # known in advance (fixed calendar)
    monthly = rule == "ME"
    sfx = "4" if monthly else "1"
    for c in ["prod", "rig", "dcot", "oi"]:
        p[c] = known_at(obs, c + sfx)
    p["inv"] = known_at(obs, "inv4" if monthly else "inv1")
    if not monthly:
        p["inv4"] = known_at(obs, "inv4")
    p["cot"] = known_at(obs, "cot1")
    p["cl1_ret"] = 100 * p.CL1.pct_change()
    p["crack_lvl"] = p.crack
    p["dcrack"] = p.crack.diff()
    p["brent_wti"] = p.Brent - p.CL1
    p["bdi_chg"] = 100 * p.bdi.pct_change()
    # Monthly: time macro data against the CALENDAR month-end, the same in
    # every month. (Timing against the last trading day gave an extra month of
    # lag whenever that day fell before the calendar month-end.)
    macro_dates = p.index if monthly else obs
    for c in macro:
        p[c] = macro_known(macro_dates, c)
    if monthly:   # crude+products inventories, monthly sheet, 1-month release lag
        p["inv_m"] = (100 * mi.Inventories.pct_change()).reindex(p.index).shift(1)
    return p


PRED = ["dlev", "inv", "inv4", "inv_m", "prod", "rig", "cot", "dcot", "oi",
        "cl1_ret", "crack_lvl", "dcrack", "brent_wti", "bdi_chg",
        "dxy", "vix", "term", "ipg"]


# ------------------------------------------------------------------ recursive OLS forecasts
def ols_forecasts(X, y, origins_idx, window, train_mask):
    """One-step forecasts at each origin using rows strictly before it."""
    preds = np.full(len(origins_idx), np.nan)
    for k, i in enumerate(origins_idx):
        lo = 0 if window is None else max(0, i - window)
        rows = np.arange(lo, i)
        rows = rows[train_mask[rows]]
        Xi = X[rows]
        good = ~np.isnan(Xi).any(1) & ~np.isnan(y[rows])
        if good.sum() < X.shape[1] + 20 or np.isnan(X[i]).any():
            continue
        b, *_ = np.linalg.lstsq(Xi[good], y[rows][good], rcond=None)
        preds[k] = X[i] @ b
    return preds


def shrink_forecasts(Xall, y, origins_idx, window, train_mask, kind, refit_every):
    preds = np.full(len(origins_idx), np.nan)
    model, mu, sd = None, None, None
    for k, i in enumerate(origins_idx):
        if model is None or k % refit_every == 0:
            lo = 0 if window is None else max(0, i - window)
            rows = np.arange(lo, i); rows = rows[train_mask[rows]]
            Xi, yi = Xall[rows], y[rows]
            good = ~np.isnan(Xi).any(1) & ~np.isnan(yi)
            Xi, yi = Xi[good], yi[good]
            mu, sd = Xi.mean(0), Xi.std(0) + 1e-12
            cv = TimeSeriesSplit(5)
            model = (LassoCV(cv=cv, alphas=30, max_iter=5000) if kind == "lasso"
                     else RidgeCV(alphas=np.logspace(-2, 4, 30), cv=cv))
            model.fit((Xi - mu) / sd, yi)
        if not np.isnan(Xall[i]).any():
            preds[k] = model.predict(((Xall[i] - mu) / sd)[None])[0]
    return preds


def r2(y, f):
    m = ~np.isnan(f)
    return 1 - ((y[m] - f[m]) ** 2).sum() / (y[m] ** 2).sum(), m.sum()


