"""
Monthly CL1-CL2 spread model: data, forecasts and the evaluation function.

Everything reads the shared clean file data/clean/oil_monthly_clean.csv.
That file already applies release lags (row t holds what was known at the
end of month t; e.g. ip_index in row t is the index for month t-1).

Definitions
    S_t     = CL1_t - CL2_t in $/bbl at month-end t.  S > 0 backwardation,
              S < 0 contango.
    target  = S_{t+1} - S_t, next month's change in the spread ($/bbl).
    origin  = month-end t, when the forecast is made.
    month   = t+1, the target month (same key as the shared benchmark).

Models (all one-step, expanding window, re-estimated every month)
    no_change  forecast 0: the spread stays where it is.
    ar         plain mean reversion:  dS_{t+1} = a + b*S_t
    arma       ARMA(p,q) on the spread level, order picked by BIC
    band       FINAL MODEL. Mean reversion with a band:
               dS_{t+1} = a + b_in*S_t*inside + b_out*S_t*outside + d*outside
               "outside" = S_t is more than BAND_K standard deviations from
               its mean, both measured on past data only.
               No other predictor: none adds to this on validation data
               (see exploration/monthly_predictor_check.py).
"""
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.stats.diagnostic import acorr_ljungbox

REPO = Path(__file__).resolve().parents[2]
CLEAN_MONTHLY = REPO / "data" / "clean" / "oil_monthly_clean.csv"
RESULTS = REPO / "data" / "results" / "Alan&Ronan"

# ---------------------------------------------------------------- frozen spec
BAND_K = 1.0          # band half-width in standard deviations
ARMA_MAX = 3          # ARMA orders searched: p, q = 0..3
ARMA_IC = "bic"       # criterion used to pick the ARMA order
MIN_TRAIN = 30        # minimum training rows before a forecast is made


# ---------------------------------------------------------------- data
def load_monthly(last_target_month):
    """Clean monthly data up to and including `last_target_month` ('YYYY-MM').

    Rows after that month are dropped before anything is estimated, so a
    validation run cannot see test-period outcomes.
    """
    df = pd.read_csv(CLEAN_MONTHLY, parse_dates=["date"])
    df["S"] = df["cl1"] - df["cl2"]
    df["y"] = df["S"].shift(-1) - df["S"]              # change from t to t+1
    # ip_index in row t is the index for month t-1 (release lag already
    # applied), so this is the latest growth rate known at month-end t.
    # Not in the final model; kept for the predictor check in exploration/.
    df["ip_growth"] = 100 * df["ip_index"].pct_change()
    df = df[df["target_month"].notna() & (df["target_month"] <= last_target_month)]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- forecasts
def _ols_predict(X, y, i):
    """Fit OLS on rows before i (complete rows only) and predict row i."""
    Xi, yi = X[:i], y[:i]
    ok = ~np.isnan(Xi).any(axis=1) & ~np.isnan(yi)
    if ok.sum() < MIN_TRAIN or np.isnan(X[i]).any():
        return np.nan
    beta, *_ = np.linalg.lstsq(Xi[ok], yi[ok], rcond=None)
    return float(X[i] @ beta)


def forecast_ar(df, origins):
    X = np.column_stack([np.ones(len(df)), df["S"].values])
    return np.array([_ols_predict(X, df["y"].values, i) for i in origins])


def band_at(df, i, k=BAND_K):
    """Band (lower, upper) from spread values strictly before row i."""
    past = df["S"].values[:i]
    return past.mean() - k * past.std(), past.mean() + k * past.std()


def band_design(df, i, k=BAND_K):
    """Design matrix for the band model as seen from origin row i."""
    S = df["S"].values
    lo, hi = band_at(df, i, k)
    out = (S < lo) | (S > hi)
    return np.column_stack([np.ones(len(df)), S * ~out, S * out, out.astype(float)]), out


def forecast_band(df, origins, k=BAND_K):
    """Returns forecasts, outside-band flags and the band used at each origin."""
    f, flag, lo_hi = [], [], []
    for i in origins:
        X, out = band_design(df, i, k)
        f.append(_ols_predict(X, df["y"].values, i))
        flag.append(bool(out[i]))
        lo_hi.append(band_at(df, i, k))
    return np.array(f), np.array(flag), np.array(lo_hi)


def select_arma_order(S):
    """AIC/BIC table for ARMA(p,q) on the spread level, p,q = 0..ARMA_MAX."""
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in range(ARMA_MAX + 1):
            for q in range(ARMA_MAX + 1):
                try:
                    m = ARIMA(S, order=(p, 0, q), trend="c").fit()
                    lb = acorr_ljungbox(m.resid, lags=[12], model_df=p + q)
                    rows.append({"p": p, "q": q, "aic": m.aic, "bic": m.bic,
                                 "ljung_box_p_12": float(lb["lb_pvalue"].iloc[0])})
                except Exception:
                    pass
    return pd.DataFrame(rows)


def forecast_arma(df, origins, order):
    """Refit ARMA on the spread up to each origin and forecast the change."""
    S = df["S"].values
    f = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i in origins:
            m = ARIMA(S[: i + 1], order=(order[0], 0, order[1]), trend="c").fit()
            f.append(float(m.forecast(1)[0]) - S[i])
    return np.array(f)


# ---------------------------------------------------------------- tests
def clark_west(y, f_bench, f_model):
    """Clark-West (2007) test that the larger model beats the nested benchmark.
    One-sided: small p means the model adds forecasting power."""
    adj = (y - f_bench) ** 2 - ((y - f_model) ** 2 - (f_bench - f_model) ** 2)
    t = adj.mean() / (adj.std(ddof=1) / np.sqrt(len(adj)))
    return t, 1 - stats.norm.cdf(t)


def diebold_mariano(y, f_a, f_b):
    """Diebold-Mariano test on squared errors with the small-sample correction
    of Harvey, Leybourne and Newbold (h = 1). Positive = model b is better.
    Two-sided p. Conservative when the models are nested."""
    d = (y - f_a) ** 2 - (y - f_b) ** 2
    n = len(d)
    dm = d.mean() / np.sqrt(d.var(ddof=0) / n) * np.sqrt((n - 1) / n)
    return dm, 2 * (1 - stats.t.cdf(abs(dm), n - 1))


def oos_r2(y, f_model, f_bench):
    return 1 - ((y - f_model) ** 2).sum() / ((y - f_bench) ** 2).sum()


# ---------------------------------------------------------------- evaluation
def evaluate(df, first_month, last_month, label, save=True):
    """Expanding-window evaluation over target months first_month..last_month.

    Returns (forecasts, metrics, arma_table). With save=True writes
    forecasts_<label>.csv, metrics_<label>.csv, arma_order_<label>.csv and
    two charts to data/results/Alan&Ronan/.
    """
    in_win = (df["target_month"] >= first_month) & (df["target_month"] <= last_month)
    origins = np.where(in_win)[0]
    y = df["y"].values[origins]

    # ARMA order picked on data before the window only
    arma_table = select_arma_order(df["S"].values[: origins[0] + 1])
    best = arma_table.sort_values(ARMA_IC).iloc[0]
    order = (int(best.p), int(best.q))

    f_band, outside, bands = forecast_band(df, origins)
    fc = pd.DataFrame({
        "month": df["target_month"].values[origins],
        "origin": df["date"].dt.strftime("%Y-%m").values[origins],
        "spread_at_origin": df["S"].values[origins],
        "actual_spread": df["S"].values[origins] + y,
        "actual_change": y,
        "pred_no_change": 0.0,
        "pred_ar": forecast_ar(df, origins),
        "pred_arma": forecast_arma(df, origins, order),
        "pred_band": f_band,
        "outside_band": outside.astype(int),
        "band_lower": bands[:, 0],
        "band_upper": bands[:, 1],
    })

    zero = fc["pred_no_change"].values
    names = {"pred_no_change": "No change", "pred_ar": "Plain mean reversion (AR)",
             "pred_arma": f"ARMA{order} by {ARMA_IC.upper()}",
             "pred_band": "Band mean reversion (final)"}
    rows = []
    for col, name in names.items():
        f = fc[col].values
        e = y - f
        row = {"model": name, "n": len(y), "rmse": np.sqrt((e ** 2).mean()),
               "mae": np.abs(e).mean()}
        if col != "pred_no_change":
            call = (f != 0) & (y != 0)
            row["oos_r2_vs_no_change"] = oos_r2(y, f, zero)
            row["oos_r2_vs_ar"] = oos_r2(y, f, fc["pred_ar"].values)
            row["oos_r2_vs_arma"] = oos_r2(y, f, fc["pred_arma"].values)
            row["hit_rate"] = (np.sign(f[call]) == np.sign(y[call])).mean()
            row["cw_t_vs_no_change"], row["cw_p_vs_no_change"] = clark_west(y, zero, f)
            row["dm_t_vs_no_change"], row["dm_p_vs_no_change"] = diebold_mariano(y, zero, f)
        if col == "pred_band":
            row["cw_t_vs_ar"], row["cw_p_vs_ar"] = clark_west(y, fc["pred_ar"].values, f)
            row["dm_t_vs_ar"], row["dm_p_vs_ar"] = diebold_mariano(y, fc["pred_ar"].values, f)
        rows.append(row)
    # final model on the months it actually makes a call (spread outside band)
    o = outside
    if o.sum() > 1:
        f = f_band[o]
        rows.append({"model": "Final model, outside-band months only", "n": int(o.sum()),
                     "rmse": np.sqrt(((y[o] - f) ** 2).mean()), "mae": np.abs(y[o] - f).mean(),
                     "oos_r2_vs_no_change": oos_r2(y[o], f, 0 * f),
                     "hit_rate": (np.sign(f) == np.sign(y[o]))[y[o] != 0].mean()})
    metrics = pd.DataFrame(rows)

    if save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        fc.to_csv(RESULTS / f"forecasts_{label}.csv", index=False)
        metrics.to_csv(RESULTS / f"metrics_{label}.csv", index=False)
        arma_table.to_csv(RESULTS / f"arma_order_{label}.csv", index=False)
        _charts(fc, label)
    return fc, metrics, arma_table


def _charts(fc, label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = pd.to_datetime(fc["month"])
    y = fc["actual_change"].values

    # Cumulative squared-error gain over no-change: line rising = model winning.
    fig, ax = plt.subplots(figsize=(9, 4))
    for col, name in [("pred_band", "Band mean reversion (final)"),
                      ("pred_ar", "Plain mean reversion"), ("pred_arma", "ARMA")]:
        ax.plot(x, np.cumsum(y ** 2 - (y - fc[col].values) ** 2), label=name)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_title(f"Cumulative squared-error gain over no-change ({label})")
    ax.set_ylabel("($/bbl)$^2$, above zero = beating no-change")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(RESULTS / f"cumulative_sse_{label}.png", dpi=300); plt.close(fig)

    # Spread with the band and the months the model makes a call.
    fig, ax = plt.subplots(figsize=(9, 4))
    xo = pd.to_datetime(fc["origin"])
    ax.plot(xo, fc["spread_at_origin"], color="black", lw=1, label="CL1 - CL2 spread")
    ax.fill_between(xo, fc["band_lower"], fc["band_upper"], alpha=0.2, label="Band (mean ± 1 sd, past data)")
    o = fc["outside_band"] == 1
    ax.scatter(xo[o], fc["spread_at_origin"][o], s=14, color="tab:red", zorder=3, label="Outside band")
    ax.set_title(f"Spread and band at each forecast origin ({label})")
    ax.set_ylabel("$/bbl (above zero = backwardation)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(RESULTS / f"spread_band_{label}.png", dpi=300); plt.close(fig)


def print_metrics(metrics):
    with pd.option_context("display.width", 250, "display.max_columns", 30,
                           "display.float_format", lambda v: f"{v:.3f}"):
        print(metrics.to_string(index=False))
