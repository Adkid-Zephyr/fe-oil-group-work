"""
Build the shared daily CL1/CL2 file: data/clean/oil_daily_cl1_cl2.csv

The monthly clean file has no daily prices. Daily prices are needed for
  - the weekly-versus-monthly evidence (exploration/), and
  - a trading rule on contracts you can actually hold (switch at expiry).

Source: sheet Industry_D of data/raw/Oil Data.xlsx. Prices are not altered.
Rows with no date or no CL1/CL2 (trailing Brent-only rows) are dropped.

Added columns
  spread                 CL1 - CL2, $/bbl (above zero = backwardation)
  cl1_last_trading_day   1 on the estimated last trading day of the CL1 contract
  days_to_cl1_expiry     trading days until that day (0 on the day itself)
  cl1_rolled             1 on the first day CL1 is the next contract. On these
                         days the change in the generic spread compares two
                         different contract pairs and is not a tradeable P&L.

Expiry rule (NYMEX WTI): trading stops 3 business days before the 25th of the
month before delivery, or 4 if the 25th is not a business day. The file's own
trading days stand in for the exchange calendar, so a date can be off by a
day around holidays that fall on weekdays.

Run from the repository root or from this folder:  python build_daily_clean.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw" / "Oil Data.xlsx"
OUT = REPO / "data" / "clean" / "oil_daily_cl1_cl2.csv"
MONTHLY = REPO / "data" / "clean" / "oil_monthly_clean.csv"

d = pd.read_excel(RAW, sheet_name="Industry_D")
d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
d = (d.dropna(subset=["Date", "CL1", "CL2"]).sort_values("Date")
       .rename(columns={"Date": "date", "CL1": "cl1", "CL2": "cl2"})[["date", "cl1", "cl2"]]
       .reset_index(drop=True))
assert d["date"].is_unique
d["spread"] = (d["cl1"] - d["cl2"]).round(4)

days = pd.DatetimeIndex(d["date"])
expiries = []
for year in range(days[0].year, days[-1].year + 1):
    for month in range(1, 13):
        d25 = pd.Timestamp(year, month, 25)
        before = days[(days < d25) & (days >= d25 - pd.Timedelta(days=20))]
        k = 3 if d25 in days else 4
        if len(before) >= k and d25 <= days[-1] + pd.Timedelta(days=10):
            expiries.append(before[-k])
expiries = pd.DatetimeIndex(expiries)

pos = np.arange(len(days))
exp_pos = np.searchsorted(days, expiries)
nxt = np.searchsorted(exp_pos, pos, side="left")           # next expiry on or after each day
d["cl1_last_trading_day"] = np.isin(pos, exp_pos).astype(int)
d["days_to_cl1_expiry"] = np.where(nxt < len(exp_pos), exp_pos[nxt.clip(max=len(exp_pos) - 1)] - pos, np.nan)
d["days_to_cl1_expiry"] = d["days_to_cl1_expiry"].astype("Int64")
d["cl1_rolled"] = d["cl1_last_trading_day"].shift(1, fill_value=0)

# Checks
m = pd.read_csv(MONTHLY, parse_dates=["date"])
last = d.groupby(d["date"].dt.to_period("M")).last()
chk = m.assign(per=m["date"].dt.to_period("M")).join(last[["cl1", "cl2"]], on="per", rsuffix="_d")
gap = max((chk.cl1 - chk.cl1_d).abs().max(), (chk.cl2 - chk.cl2_d).abs().max())
assert gap < 1e-9, "daily month-end prices do not match the monthly clean file"
chg = d["spread"].diff().abs()
print(f"{len(d)} trading days, {d.date.min().date()} to {d.date.max().date()}")
print(f"Daily month-end prices match the monthly clean file (max gap {gap:.2g})")
print(f"Median |daily spread change|: {chg[d.cl1_rolled == 1].median():.3f} on roll days, "
      f"{chg[d.cl1_rolled == 0].median():.3f} on other days ({len(expiries)} expiries)")
d.to_csv(OUT, index=False, date_format="%Y-%m-%d")
print("Wrote", OUT.relative_to(REPO))
