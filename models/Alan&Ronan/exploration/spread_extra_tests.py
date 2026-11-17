"""
Extra angles for the CL1-CL2 spread, weekly vs monthly, tested the same way
as spread_grid_search.py (validation 2005-2014 only, split-half check).

1. ARIMA / ARIMAX
   All orders p in {0,1,2}, d in {0,1}, q in {0,1,2} on the $ spread level,
   plus the order picked each year by AIC and by BIC (lecture 4b).
   Parameters re-estimated each January on data before that year; within the
   year the Kalman filter updates with each new observation, so every
   forecast uses only past data. Weekly ARIMAX adds a dummy for "a contract
   roll happens this week" (the expiry calendar is known in advance).
   Monthly ARIMAX adds IP growth known at the forecast date.

2. Mean reversion only at extremes
   a) Band model: separate slope inside and outside mean +/- k sd (k = 1, 1.5, 2),
      band set on training data only.
   b) Extremes-only forecast: AR forecast when outside the band, zero otherwise.
   c) Asymmetric: separate slopes in contango (S<0) and backwardation (S>0).
      Storage theory says contango is capped by storage cost, backwardation is not.

3. Seasonality
   a) 11 month-of-year dummies.  b) Quarter dummies.  c) One annual sine/cosine pair.

Each is run alone on top of the AR base and, for monthly, also with lagged
industrial production growth (the one robust predictor from the grid).

Run from models/Alan&Ronan/exploration:  python spread_extra_tests.py   (reads data/raw/Oil Data.xlsx)
"""
import sys, warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from spread_data import panel, ols_forecasts, VAL, HALF, OUT

warnings.filterwarnings("ignore")


def score(y, f, dates, mask=None):
    m = ~np.isnan(f) if mask is None else (~np.isnan(f) & mask)
    first = dates <= pd.Timestamp(HALF)
    out = {}
    for lab, sel in [("R2", m), ("R2_0509", m & first), ("R2_1014", m & ~first)]:
        out[lab] = 1 - ((y[sel] - f[sel]) ** 2).sum() / (y[sel] ** 2).sum()
    nz = m & (y != 0) & (f != 0)          # zero forecast = no call, excluded
    out["hit"] = (np.sign(f[nz]) == np.sign(y[nz])).mean()
    out["n"] = int(m.sum())
    return out


# ================================================================ setup
setups = {"Weekly (Fri)": "W-FRI", "Monthly": "ME"}
results = []

for fname, rule in setups.items():
    monthly = rule == "ME"
    P = panel(rule)
    P["y"] = P.S.diff().shift(-1)                 # change in $ spread, t to t+1
    P = P.dropna(subset=["y", "S"]).copy()
    P["rn"] = P.roll_next.astype(float)
    y = P.y.values
    dates = P.index
    in_val = (dates >= VAL[0]) & (dates <= VAL[1])
    nonroll = ~P.roll_next.astype(bool).values
    # weekly: evaluate on tradeable (non-roll) weeks; monthly: all months
    eval_mask = nonroll if not monthly else np.ones(len(P), bool)
    train_mask = nonroll if not monthly else np.ones(len(P), bool)
    origins = np.where(in_val & eval_mask)[0]
    yv, dv = y[origins], dates[origins]

    def add(model, f, family):
        results.append({"freq": fname, "family": family, "model": model,
                        **score(yv, f, dv)})

    def ols(cols, extra=None):
        X = np.column_stack([np.ones(len(P))] + [P[c].values for c in cols])
        return ols_forecasts(X, y, origins, None, train_mask)

    base = ["S"]
    bases = {"AR": base}
    if monthly:
        bases["AR + IP"] = ["S", "ipg"]

    for bname, b in bases.items():
        add(f"{bname} (reference)", ols(b), "reference")

    # ------------------------------------------------------------ 2. extremes
    for k in (1.0, 1.5, 2.0):
        # band from expanding training data only: recompute per origin
        f_band = {bn: np.full(len(origins), np.nan) for bn in bases}
        f_only = {bn: np.full(len(origins), np.nan) for bn in bases}
        for j, i in enumerate(origins):
            tr = np.arange(i)[train_mask[:i]]
            mu, sd = P.S.values[tr].mean(), P.S.values[tr].std()
            out = np.abs(P.S.values - mu) > k * sd
            for bn, b in bases.items():
                X = np.column_stack([np.ones(len(P)), P.S.values * ~out, P.S.values * out,
                                     out.astype(float)] + [P[c].values for c in b if c != "S"])
                Xi, yi = X[tr], y[tr]
                g = ~np.isnan(Xi).any(1)
                if np.isnan(X[i]).any() or g.sum() < 30:
                    continue
                coef, *_ = np.linalg.lstsq(Xi[g], yi[g], rcond=None)
                f_band[bn][j] = X[i] @ coef
                # extremes-only: plain AR forecast if outside band, else zero
                Xa = np.column_stack([np.ones(len(P))] + [P[c].values for c in b])
                ca, *_ = np.linalg.lstsq(Xa[tr][g], yi[g], rcond=None)
                f_only[bn][j] = (Xa[i] @ ca) if out[i] else 0.0
        for bn in bases:
            add(f"{bn}: band slopes, k={k}", f_band[bn], "extremes")
            add(f"{bn}: forecast only outside band, k={k}", f_only[bn], "extremes")
            # how good is the plain AR on just the extreme dates?
        if k == 1.5:
            ext_flags = np.array([np.abs(P.S.values[i] - P.S.values[np.arange(i)[train_mask[:i]]].mean())
                                  > k * P.S.values[np.arange(i)[train_mask[:i]]].std() for i in origins])
            f_ar = ols(base)
            r = score(yv, f_ar, dv, ext_flags)
            results.append({"freq": fname, "family": "extremes",
                            "model": "AR, scored only on dates outside 1.5 sd band", **r})
    # asymmetric contango / backwardation
    P["S_pos"] = P.S.clip(lower=0)
    P["S_neg"] = P.S.clip(upper=0)
    for bn, b in bases.items():
        add(f"{bn}: asymmetric (contango vs backwardation slopes)",
            ols(["S_pos", "S_neg"] + [c for c in b if c != "S"]), "extremes")

    # ------------------------------------------------------------ 3. seasonality
    mon = P.index.month
    for m_ in range(2, 13):
        P[f"m{m_}"] = (mon == m_).astype(float)
    for q in (2, 3, 4):
        P[f"q{q}"] = (P.index.quarter == q).astype(float)
    P["sin"] = np.sin(2 * np.pi * P.index.dayofyear / 365.25)
    P["cos"] = np.cos(2 * np.pi * P.index.dayofyear / 365.25)
    for bn, b in bases.items():
        add(f"{bn} + month dummies", ols(b + [f"m{m_}" for m_ in range(2, 13)]), "seasonal")
        add(f"{bn} + quarter dummies", ols(b + ["q2", "q3", "q4"]), "seasonal")
        add(f"{bn} + annual sine/cosine", ols(b + ["sin", "cos"]), "seasonal")

    # ------------------------------------------------------------ 1. ARIMA
    # Fit on the full consecutive series (ARMA needs every period, roll weeks
    # included), but score weekly forecasts only on non-roll weeks.
    S = P.S.copy()
    S.index = pd.RangeIndex(len(S))
    # exog for S at row t must be known by t-1:
    #   roll_t (a roll between t-1 and t) is fixed by the expiry calendar
    #   IP growth enters as its value at t-1 (already release-lagged)
    exog_all = P[["roll"]].astype(float).values if not monthly else None
    years = sorted(set(dv.year))
    orders = [(p, d, q) for p in (0, 1, 2) for d in (0, 1) for q in (0, 1, 2)
              if (p, d, q) not in [(0, 1, 0)]]          # (0,1,0) is no-change itself
    variants = [("ARIMA", None)] + ([("ARIMAX (roll dummy)", exog_all)] if not monthly else [])
    if monthly:
        variants.append(("ARIMAX (IP growth)", P[["ipg"]].shift(1).values))
    for vname, ex in variants:
        f_ord = {o: np.full(len(origins), np.nan) for o in orders}
        f_aic = np.full(len(origins), np.nan)
        f_bic = np.full(len(origins), np.nan)
        for yr in years:
            start = np.where(dates.year == yr)[0][0]          # first origin row of the year
            idx_yr = [j for j, i in enumerate(origins) if dates[i].year == yr]
            last = origins[idx_yr[-1]]
            fits = {}
            for o in orders:
                endog_tr = S.iloc[:start]
                ex_tr = None if ex is None else ex[:start]
                g = ~np.isnan(ex_tr).any(1) if ex_tr is not None else np.ones(start, bool)
                first_ok = np.argmax(g) if ex_tr is not None else 0
                try:
                    trend = "c" if o[1] == 0 else "n"
                    m = ARIMA(endog_tr.iloc[first_ok:].values,
                              exog=None if ex is None else ex_tr[first_ok:],
                              order=o, trend=trend).fit()
                except Exception:
                    continue
                fits[o] = m
                # filter through the year with fixed parameters
                full = S.iloc[first_ok:last + 2].values
                ex_full = None if ex is None else ex[first_ok:last + 2]
                r = m.apply(full, exog=ex_full)
                pred_level = r.predict()                        # one-step, past data only
                for j in idx_yr:
                    i = origins[j]
                    # forecast of S at i+1 made at i, minus S at i -> change forecast
                    f_ord[o][j] = pred_level[i + 1 - first_ok] - S.iloc[i]
            if fits:
                oa = min(fits, key=lambda o: fits[o].aic)
                ob = min(fits, key=lambda o: fits[o].bic)
                for j in idx_yr:
                    f_aic[j] = f_ord[oa][j]
                    f_bic[j] = f_ord[ob][j]
        for o in orders:
            add(f"{vname} {o}", f_ord[o], "ARIMA")
        add(f"{vname}, order picked by AIC each year", f_aic, "ARIMA")
        add(f"{vname}, order picked by BIC each year", f_bic, "ARIMA")
    print(f"done {fname}", flush=True)

R = pd.DataFrame(results)
R.to_csv(OUT / "extra_tests_results.csv", index=False)
pd.set_option("display.width", 220, "display.max_rows", 500,
              "display.float_format", lambda v: f"{v:.3f}")
for f in R.freq.unique():
    print(f"\n=== {f}: validation 2005-2014, OOS R2 vs no-change"
          + (" (non-roll weeks only)" if f.startswith("Weekly") else "") + " ===")
    print(R[R.freq == f].drop(columns="freq").to_string(index=False))
