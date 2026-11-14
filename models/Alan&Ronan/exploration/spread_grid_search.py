"""
Full specification grid for the CL1-CL2 spread: weekly vs monthly, tested the
same way.

Grid
  Frequency      : weekly (Friday close), weekly (Wednesday close, the EIA
                   release day), monthly (month-end close)
  Target         : next-period change in $ spread  S = CL1 - CL2
                   next-period change in % spread  s = 100*(CL1/CL2 - 1)
  Window         : expanding; rolling (5 years)
  Weekly sample  : all weeks (base model includes roll-week terms)
                   non-roll weeks only (same two contracts, so a tradeable change)
  Specifications : constant only; AR on level (base); base + every single
                   predictor; base + every pair of predictors; base + all
                   predictors (kitchen sink); LASSO and Ridge on all predictors

Every forecast uses only data released before the forecast date (lags below).
Evaluation is on the VALIDATION period 2005-2014 only. The 2015-2024 test
period is not used, so nothing here peeks at it.

Because we try ~150 specifications per setting, the best one will look good
by luck. So we also pick the best spec on 2005-2009 and check it on 2010-2014.

Run from models/Alan&Ronan/exploration:  python spread_grid_search.py   (reads data/raw/Oil Data.xlsx)
"""
from spread_data import *  # data, release lags, panel(), ols_forecasts(), shrink_forecasts()
import itertools

# ------------------------------------------------------------------ grid
FREQS = {"Weekly (Fri)": "W-FRI", "Weekly (Wed)": "W-WED", "Monthly": "ME"}
rows, best_rows, all_scores = [], [], []
for fname, rule in FREQS.items():
    P = panel(rule)
    monthly = rule == "ME"
    per_year = 12 if monthly else 52
    for target in ["S", "s_pct"]:
        P["lev"] = P[target]
        P["dlev"] = P[target].diff()
        P["y"] = P[target].diff().shift(-1)            # change from t to t+1
        preds = [c for c in PRED if c in P and P[c].notna().sum() > 100]
        samples = ["non-roll weeks"] if monthly else ["non-roll weeks", "all weeks"]
        if monthly:
            samples = ["all months"]
        for sample in samples:
            P2 = P.dropna(subset=["y", "lev"]).copy()
            y = P2.y.values
            base = ["lev"]
            if sample == "all weeks":
                P2["rn"] = P2.roll_next.astype(float)
                P2["lev_x_rn"] = P2.lev * P2.rn
                base = ["lev", "rn", "lev_x_rn"]
            train_mask = np.ones(len(P2), bool)
            if sample == "non-roll weeks":
                train_mask = ~P2.roll_next.astype(bool).values
            in_val = (P2.index >= VAL[0]) & (P2.index <= VAL[1])
            origins = np.where(in_val & train_mask)[0]
            yv = y[origins]
            first = P2.index[origins] <= HALF
            for window_name, window in [("expanding", None), ("rolling 5y", 5 * per_year)]:
                def run(cols):
                    X = np.column_stack([np.ones(len(P2))] + [P2[c].values for c in cols])
                    return ols_forecasts(X, y, origins, window, train_mask)
                specs = {"constant only": [], "AR base": base}
                for c in preds:
                    specs[f"base + {c}"] = base + [c]
                for a, b in itertools.combinations(preds, 2):
                    specs[f"base + {a} + {b}"] = base + [a, b]
                specs["kitchen sink"] = base + preds
                res = {}
                for name, cols in specs.items():
                    res[name] = run(cols)
                Xall = P2[base + preds].values.astype(float)
                refit = per_year if not monthly else 12
                res["LASSO (all)"] = shrink_forecasts(Xall, y, origins, window, train_mask, "lasso", refit)
                res["Ridge (all)"] = shrink_forecasts(Xall, y, origins, window, train_mask, "ridge", refit)
                # score every spec on the same forecast dates
                common = np.ones(len(origins), bool)
                for f in res.values():
                    common &= ~np.isnan(f)
                score = {}
                for name, f in res.items():
                    full = 1 - ((yv[common] - f[common]) ** 2).sum() / (yv[common] ** 2).sum()
                    h1 = common & first; h2 = common & ~first
                    a1 = 1 - ((yv[h1] - f[h1]) ** 2).sum() / (yv[h1] ** 2).sum()
                    a2 = 1 - ((yv[h2] - f[h2]) ** 2).sum() / (yv[h2] ** 2).sum()
                    hit = (np.sign(f[common]) == np.sign(yv[common]))[yv[common] != 0].mean()
                    score[name] = (full, a1, a2, hit)
                sc = pd.DataFrame(score, index=["R2", "R2_0509", "R2_1014", "hit"]).T
                all_scores.append(sc.assign(freq=fname, target=target, sample=sample, window=window_name))
                grid = sc.drop(["LASSO (all)", "Ridge (all)", "constant only"])
                pick = grid.R2_0509.idxmax()
                tag = dict(freq=fname, target="$ spread" if target == "S" else "% spread",
                           sample=sample, window=window_name, n=int(common.sum()))
                rows.append({**tag,
                    "specs": len(grid),
                    "share beating no-change": (grid.R2 > 0).mean(),
                    "AR base R2": sc.loc["AR base", "R2"],
                    "median spec R2": grid.R2.median(),
                    "best spec R2": grid.R2.max(),
                    "best spec": grid.R2.idxmax(),
                    "LASSO R2": sc.loc["LASSO (all)", "R2"],
                    "Ridge R2": sc.loc["Ridge (all)", "R2"],
                    "picked on 05-09": pick,
                    "its R2 05-09": sc.loc[pick, "R2_0509"],
                    "its R2 10-14": sc.loc[pick, "R2_1014"],
                    "AR base R2 10-14": sc.loc["AR base", "R2_1014"]})
                print(f"done: {fname} | {tag['target']} | {sample} | {window_name}", flush=True)
                # keep per-predictor single results for the report
                for c in preds:
                    best_rows.append({**tag, "predictor": c,
                                      "R2 base+pred": sc.loc[f"base + {c}", "R2"],
                                      "gain vs base": sc.loc[f"base + {c}", "R2"] - sc.loc["AR base", "R2"]})

out = pd.DataFrame(rows)
singles = pd.DataFrame(best_rows)
out.to_csv(OUT / "grid_summary.csv", index=False)
pd.concat(all_scores).rename_axis("spec").to_csv(OUT / "grid_all_specs.csv")
singles.to_csv(OUT / "grid_single_predictors.csv", index=False)
pd.set_option("display.width", 250, "display.max_columns", 30,
              "display.float_format", lambda v: f"{v:.3f}")
print("\n=== Summary, validation 2005-2014, OOS R2 vs no-change ===")
print(out.drop(columns=["best spec", "picked on 05-09"]).to_string(index=False))
print("\n=== Best and picked specs ===")
print(out[["freq", "target", "sample", "window", "best spec", "picked on 05-09"]].to_string(index=False))
