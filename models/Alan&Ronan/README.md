# Alan and Ronan: monthly CL1-CL2 spread model

We forecast next month's change in the CL1-CL2 calendar spread. This is a different target from the CL1 return models in this repo, so **our RMSE and MAE cannot be ranked against them or against the shared CL1 no-change benchmark.** We compare against a no-change forecast of the spread instead, on the same 114 test months.

## The model in one paragraph

The spread is `S = CL1 - CL2` in $/bbl at month-end. Above zero is backwardation, below zero is contango. (The brief writes CL2 - CL1. Ours is the same number with the sign flipped.) When the spread is near its normal level it does not mean-revert. When it is more than one standard deviation from its historical mean, it moves back with a half-life of about two months. So the model only expects a move when the spread is stretched.

```
dS(t+1) = a + b_in * S(t) * inside + b_out * S(t) * outside + d * outside
```

`outside` is 1 when `S(t)` is outside mean ± 1 sd, with the mean and sd taken from past data only. Fitted on data to December 2014: `b_in = +0.14` (p = 0.05, no reversion inside the band), `b_out = -0.25` (p < 0.001), the two slopes differ (Wald p = 0.0001), band about -$0.96 to +$0.68, 28% of months outside. Newey-West standard errors.

## Frozen specification

| Item | Choice |
| --- | --- |
| Target | `S(t+1) - S(t)`, $/bbl, month-end to month-end |
| Frequency | Monthly |
| Data | `data/clean/oil_monthly_clean.csv` only (`cl1`, `cl2`) |
| Predictors | The spread itself. No macro or industry predictor (see below) |
| Band | Mean ± 1.0 sd of the spread, expanding, past data only |
| Estimation | OLS, expanding window, re-estimated every month |
| Benchmarks | No change; plain mean reversion `dS = a + b*S`; ARMA(p,q) on the spread, p,q ≤ 3, order by BIC on pre-window data |
| Validation | Target months Jan 2005 to Dec 2014 (120) |
| Test | Target months Jan 2015 to Jun 2024 (114), run once |

No release lags are needed for the final model: CL1 and CL2 are known at the month-end close.

## Files

| File | What it does |
| --- | --- |
| `spread_model.py` | Data loading, the four forecasts, Clark-West and Diebold-Mariano tests, and `evaluate()`, the evaluation function |
| `run_validation.py` | Runs `evaluate()` on 2005-2014. Test rows are dropped on load |
| `run_test.py` | Runs the frozen model on 2015-2024. Refuses to run twice. `--reproduce` checks saved numbers |
| `build_daily_clean.py` | Builds `data/clean/oil_daily_cl1_cl2.csv` from the raw workbook, with expiry flags |
| `exploration/` | Everything we tried before choosing this model, with saved outputs |

Run from this folder:

```bash
python -m pip install -r requirements.txt
python build_daily_clean.py
python run_validation.py
python run_test.py --reproduce
```

Outputs go to `data/results/Alan&Ronan/`: `forecasts_<window>.csv` (`month`, `origin`, `actual_change`, one `pred_*` column per model, `outside_band`, band limits), `metrics_<window>.csv`, `arma_order_<window>.csv` and two charts.

## Validation results (2005-2014)

Out-of-sample R² is measured against the no-change forecast. Above zero beats it.

| Model | RMSE ($) | OOS R² | 2005-09 | 2010-14 | Direction | Clark-West p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No change | 0.581 | | | | | |
| Plain mean reversion | 0.576 | 1.8% | -2.4% | 10.5% | 57.5% | 0.059 |
| ARMA(2,0) | 0.584 | -0.9% | | | 55.8% | 0.122 |
| **Band mean reversion (final)** | **0.561** | **6.8%** | **2.8%** | **15.4%** | 54.2% | **0.009** |
| Final model, outside-band months only (54) | 0.665 | 10.2% | | | 64.8% | |

The band model also beats plain mean reversion (Clark-West p = 0.004). Diebold-Mariano against no-change is not significant (p = 0.22). That test is known to be conservative for nested models, and 120 months is a small sample.

## Why monthly and not weekly

Tested on validation data only, same grid at both frequencies (`exploration/`).

- CL1 changes contract around the 20th of each month. Month-end always falls 11 to 16 trading days before expiry, so the monthly spread is close to a constant-maturity measure. Fridays fall anywhere from 0 to 22 days before expiry.
- 23% of weekly changes span a roll and compare two different contract pairs. Those weeks are 70% more volatile. Excess kurtosis of weekly changes is 45, against 5 monthly.
- Weekly models look strong when roll weeks are included (OOS R² up to 32%). That is the mechanical jump when CL1 switches contract. Nobody can earn it.
- On weeks with no roll, where the change is a real P&L: 1,240 specification runs, none beats no-change in both halves of validation. LASSO sets every coefficient to zero.
- ARIMA (17 orders, AIC and BIC selection), band models, asymmetric slopes and seasonal terms all fail weekly as well.
- Daily was not run. It has the same roll problem every month, and no predictor in the workbook is daily.

## Why no other predictor

`exploration/monthly_predictor_check.py` adds each of 18 candidates to the model on the clean dataset: inventories, production, rigs, positioning, CL1 return, crack spread, Baltic Dry, dollar, VIX, yield curve, CPI, IP growth, equities, gasoline. One of 18 (gasoline price change) improves both halves of validation, which is what chance alone would give. LASSO and Ridge on all predictors lose to no-change. Seasonal dummies and separate contango/backwardation slopes do not help. We kept the model with no extra predictor.

**Correction to an earlier result.** Our first search reported lagged industrial production growth as a robust predictor. That came from a timing slip: monthly macro data was timed against the last trading day, which gave an extra month of lag in the 30% of months that end on a weekend or holiday. Nothing looked ahead, but the lag was not the same every month. With a consistent lag, IP growth does not help (plain mean reversion + IP: -0.2%). The exploration scripts are fixed and their saved outputs rerun. IP growth is not in the final model.

## Limits

- The target is the shape of the curve, not a tradeable return. The front contract expires inside every month. A trading rule has to switch contract pairs at expiry. Use `oil_daily_cl1_cl2.csv` for that.
- About 28% of months give a signal, so the evidence rests on a few dozen calls.
- We searched many specifications on validation data before settling on this one. The split-half checks and the single test run are the guard against that.
- 2008-09 and 2020 dominate the squared errors. April 2020 is in the test window.
- The expiry calendar in the daily file is estimated from the file's own trading days.
