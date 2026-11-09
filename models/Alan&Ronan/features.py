"""
Alan & Ronan: shared monthly targets and predictors.

Every predictor is lined up so that the value in row t was known at the END of
month t (the forecast origin). Targets in row t are what happens AFTER t.

Imported by compare_return_vs_curve.py. Can also be run on its own to print a
summary of the feature table.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"


# ---------------------------------------------------------------------------
# Load the three cleaned sources
# ---------------------------------------------------------------------------
def load_sources():
    daily = pd.read_csv(CLEAN / "industry_daily.csv", parse_dates=["date"]).set_index("date")
    weekly = pd.read_csv(CLEAN / "industry_weekly.csv", parse_dates=["date"]).set_index("date")
    monthly = pd.read_csv(CLEAN / "monthly_observations.csv")
    monthly["month"] = pd.PeriodIndex(monthly["month"], freq="M")
    return daily, weekly, monthly.set_index("month")


# ---------------------------------------------------------------------------
# Roll dates for CL1 (exchange rule, holidays ignored)
# ---------------------------------------------------------------------------
# WTI stops trading 3 business days before the 25th of the month (4 if the 25th
# is not a business day). CL1 switches to the next contract the day after.
def roll_days(trading_days):
    out = {}
    for p in pd.period_range(trading_days.min().to_period("M"),
                             trading_days.max().to_period("M"), freq="M"):
        d25 = pd.Timestamp(p.year, p.month, 25)
        last_trade = d25 - pd.offsets.BDay(3 if d25.dayofweek < 5 else 4)
        after = trading_days[trading_days > last_trade]
        if len(after):
            out[p] = after[0]
    return pd.Series(out)


def build():
    daily, weekly, m = load_sources()
    idx = m.index
    month_end = idx.to_timestamp(how="end").normalize()
    c1, c2 = m["industry__cl1"], m["industry__cl2"]

    T = pd.DataFrame(index=idx)    # targets (what happens after month t)
    X = pd.DataFrame(index=idx)    # predictors (known at end of month t)

    # ---- Returns -----------------------------------------------------------
    # The contract that is CL2 at the end of month t is CL1 at the end of t+1,
    # so the return from holding one contract is CL1_{t+1} / CL2_t - 1.
    held = 100 * (c1 / c2.shift() - 1)
    cont = 100 * (c1 / c1.shift() - 1)
    T["ret_held"] = held.shift(-1)          # tradable return next month
    T["ret_cont"] = cont.shift(-1)          # raw CL1 change next month (shared target)

    # ---- Curve -------------------------------------------------------------
    # Spread in % of the front price. Positive = contango (later contract dearer).
    spread = 100 * (c2 / c1 - 1)
    T["d_spread"] = spread.shift(-1) - spread   # change in curve slope by next month-end

    # Tradable calendar spread: long CL2, short CL1 at month-end t, closed
    # 5 trading days before CL1 rolls in month t+1, so both legs are the same
    # contracts throughout. P&L in % of the front-month price at entry.
    rolls = roll_days(daily.index)
    td = daily.index
    pnl = {}
    for i, p in enumerate(idx[:-1]):
        nxt = idx[i + 1]
        if nxt not in rolls.index:
            continue
        entry_day = td[td <= month_end[i]]
        before_roll = td[td < rolls[nxt]]
        if len(entry_day) == 0 or len(before_roll) < 6:
            continue
        e, x = entry_day[-1], before_roll[-5]
        if x <= e:
            continue
        s0 = daily.at[e, "cl2"] - daily.at[e, "cl1"]
        s1 = daily.at[x, "cl2"] - daily.at[x, "cl1"]
        pnl[p] = 100 * (s1 - s0) / daily.at[e, "cl1"]
    T["spread_pnl"] = pd.Series(pnl)

    # ---- Price-based predictors (known at month-end) ---------------------
    X["ret"] = held                                      # last month's return
    X["ret_lag2"] = held.shift(1)
    X["ret_lag3"] = held.shift(2)
    X["mom12"] = 100 * ((1 + held / 100).rolling(12).apply(np.prod, raw=True) - 1)
    X["spread"] = spread                                 # contango (+) / backwardation (-)
    X["d_spread_last"] = spread.diff()
    X["brent_wti"] = 100 * (m["industry__brent"] / c1 - 1)
    X["crack_chg"] = m["industry__crack_spread_321"].diff()
    X["bdi_chg"] = 100 * m["industry__baltic_dry_index"].pct_change()

    # Realised volatility of daily CL1 returns inside month t (annualised %).
    # Daily CL1/CL2 match the monthly sheet exactly, unlike Brent/crack/BDI.
    is_roll = td.isin(rolls.values)
    dret = pd.Series(np.where(is_roll, daily["cl1"] / daily["cl2"].shift() - 1,
                              daily["cl1"] / daily["cl1"].shift() - 1), index=td)
    dret = dret.drop(pd.to_datetime(["2020-04-20", "2020-04-21"]), errors="ignore")
    X["realised_vol"] = (dret.groupby(dret.index.to_period("M")).std() * np.sqrt(252) * 100).reindex(idx)

    # ---- Market and macro --------------------------------------------------
    X["vix"] = m["macro__vix"]
    X["vix_chg"] = m["macro__vix"].diff()
    X["spx_ret"] = 100 * m["macro__sp500_index"].pct_change()
    X["dxy_ret"] = m["macro__dxy_return_pct"]
    X["ip_growth"] = 100 * m["macro__industrial_production_index"].pct_change().shift(1)  # released mid next month
    X["cpi_chg"] = m["macro__cpi_yoy_pct"].diff().shift(1)
    # Treasury yields are labelled one month EARLY in the workbook (label t = end of t+1),
    # so we lag them two labels to be safe.
    y3, y10 = m["macro__treasury_3m_yield_pct"], m["macro__treasury_10y_yield_pct"]
    X["y3m"] = y3.shift(2)
    X["y3m_chg"] = y3.diff().shift(2)
    X["term_spread"] = (y10 - y3).shift(2)

    # ---- Monthly fundamentals (published after month-end, so lagged 1) ----
    inv = m["industry__inventories_source_units"]
    X["inv_chg"] = 100 * inv.pct_change().shift(1)
    X["inv_yoy"] = 100 * inv.pct_change(12).shift(1)
    seasonal_avg = sum(inv.shift(12 * k) for k in (1, 2, 3)) / 3      # same month, last 3 years
    X["inv_vs_seasonal"] = (100 * (inv / seasonal_avg - 1)).shift(1)
    X["prod_chg"] = 100 * m["industry__crude_production_source_units"].pct_change().shift(1)
    X["rig_chg"] = 100 * m["industry__rig_count"].pct_change().shift(1)
    long_, short_ = m["industry__commercial_long"], m["industry__commercial_short"]
    net = 100 * (long_ - short_) / (long_ + short_)
    X["hedging_pressure"] = net.shift(1)                # commercials' net position, % of their total
    X["hedging_pressure_chg"] = net.diff().shift(1)

    # ---- Weekly data turned into monthly predictors ------------------------
    # Only weekly observations dated at least 7 days before month-end are used,
    # because EIA and CFTC data come out several days after the date they cover.
    cut = month_end - pd.Timedelta(days=7)
    prev_cut = cut.to_series().shift(1).values
    stock_now, net_now, rig_now = [], [], []
    wnet = 100 * (weekly["commercial_long_unimputed"] - weekly["commercial_short"]) / \
           (weekly["commercial_long_unimputed"] + weekly["commercial_short"])
    for i, c in enumerate(cut):
        lo = prev_cut[i] if i > 0 else c - pd.Timedelta(days=31)
        window = weekly.loc[(weekly.index > lo) & (weekly.index <= c)]
        known = weekly.loc[weekly.index <= c]
        stock_now.append(window["crude_stock_change_source_units"].sum(min_count=1))
        net_now.append(wnet.loc[wnet.index <= c].dropna().iloc[-1] if wnet.loc[wnet.index <= c].notna().any() else np.nan)
        r = known["rig_count"].dropna()
        rig_now.append(100 * (r.iloc[-1] / r.iloc[-5] - 1) if len(r) > 5 else np.nan)
    X["inv_nowcast_weekly"] = stock_now          # weekly stock changes published by month-end
    X["hedging_pressure_weekly"] = net_now       # latest weekly CFTC net position
    X["rig_chg_weekly"] = rig_now                # rig count change over the last 4 weeks

    return T, X


# Predictor groups used by the comparison script
CORE = ["ret", "spread", "brent_wti", "crack_chg", "bdi_chg", "vix_chg", "spx_ret", "dxy_ret",
        "inv_chg", "prod_chg", "rig_chg", "hedging_pressure_chg", "ip_growth", "cpi_chg",
        "term_spread", "y3m_chg"]
WIDE = CORE + ["ret_lag2", "ret_lag3", "mom12", "d_spread_last", "realised_vol", "vix", "y3m",
               "inv_yoy", "inv_vs_seasonal", "hedging_pressure", "inv_nowcast_weekly",
               "hedging_pressure_weekly", "rig_chg_weekly"]

if __name__ == "__main__":
    T, X = build()
    print(T.describe().round(2).T)
    print(X[WIDE].describe().round(2).T)
