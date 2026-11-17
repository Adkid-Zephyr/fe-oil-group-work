"""
Does any predictor add to mean reversion on the monthly spread?

Rerun of the monthly predictor search on the SHARED clean dataset, where every
release lag is applied the same way in every month. Validation window only
(target months 2005-01 to 2014-12), split into two halves.

Why this exists: the first search (spread_grid_search.py) timed monthly macro
data against the last TRADING day of each month. In the ~30% of months whose
last trading day falls before the calendar month-end, macro values were lagged
one month more than intended. Nothing looked ahead, but the lag was not the
same every month. Lagged industrial production growth looked robust under that
mixed lag. With a consistent lag it does not, as this script shows.

Run from models/Alan&Ronan:  python exploration/monthly_predictor_check.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spread_model as sm

df = sm.load_monthly("2014-12")
pc = lambda c: 100 * df[c].pct_change()
cands = {
    "last spread change": df["S"].diff(),
    "IP growth": df["ip_growth"],
    "IP growth, one more month's lag": df["ip_growth"].shift(1),
    "inventory growth": pc("inventories"),
    "production growth": pc("production"),
    "rig count change": df["rig_count"].diff(),
    "net commercial position (% of long+short)": 100 * (df.comm_long - df.comm_short) / (df.comm_long + df.comm_short),
    "CL1 return": df["cl1_pct"],
    "crack spread level": df["crack_321"],
    "crack spread change": df["crack_321"].diff(),
    "Baltic Dry change": pc("bdi"),
    "dollar return": 100 * df["dxy_ret"],
    "VIX": df["vix"],
    "yield curve (10y - 3m)": df["y10y"] - df["y3m"],
    "CPI inflation": df["cpi_yoy"],
    "S&P 500 return": pc("spx"),
    "oil & gas equity return": pc("dj_oil_gas"),
    "gasoline price change": pc("gasoline"),
}
origins = np.where(df["target_month"] >= "2005-01")[0]
y = df["y"].values[origins]
first = df["target_month"].values[origins] <= "2009-12"


def r2(f):
    return [1 - ((y[m] - f[m]) ** 2).sum() / (y[m] ** 2).sum() for m in (first | ~first, first, ~first)]


def run(extra, band):
    f = []
    for i in origins:
        if band:
            X, _ = sm.band_design(df, i)
        else:
            X = np.column_stack([np.ones(len(df)), df["S"].values])
        if extra is not None:
            X = np.column_stack([X, extra.values])
        f.append(sm._ols_predict(X, df["y"].values, i))
    return r2(np.array(f))


rows = []
for base, band in [("plain mean reversion", False), ("band mean reversion", True)]:
    b = run(None, band)
    rows.append({"base": base, "added predictor": "(none)", "R2": b[0], "R2 2005-09": b[1],
                 "R2 2010-14": b[2], "beats base in both halves": ""})
    for name, x in cands.items():
        r = run(x, band)
        rows.append({"base": base, "added predictor": name, "R2": r[0], "R2 2005-09": r[1],
                     "R2 2010-14": r[2],
                     "beats base in both halves": "yes" if r[1] > b[1] and r[2] > b[2] else "no"})
out = pd.DataFrame(rows)
out.to_csv(Path(__file__).parent / "monthly_predictor_check.csv", index=False)
with pd.option_context("display.width", 200, "display.float_format", lambda v: f"{v:.3f}"):
    print(out.to_string(index=False))
