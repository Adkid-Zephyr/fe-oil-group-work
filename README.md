# Monthly CL1-CL2 spread model

We forecast next month's change in the CL1-CL2 calendar spread. This is a different target from the CL1 return models in this repo, so **our RMSE and MAE cannot be ranked against them or against the shared CL1 no-change benchmark.** We compare against a no-change forecast of the spread instead, on the same 114 test months.

Everything is in `spread_model.ipynb` (tasks 1-3: data and repo setup, evaluation and test run, stationarity and data checks). It runs top to bottom on a fresh clone.

## The model in one paragraph

The spread is `S = CL1 - CL2` in $/bbl at month-end. Above zero is backwardation, below zero is contango. (The brief writes CL2 - CL1; ours is the same quantity with the opposite sign.) When the spread is near its normal level it does not mean-revert. When it is more than one standard deviation from its historical mean, it moves back with a half-life of about two months. So the model only expects a move when the spread is stretched.

```
dS(t+1) = a + b_in * S(t) * inside + b_out * S(t) * outside + d * outside
```

`outside` is 1 when `S(t)` is outside mean ± 1 sd, with the mean and sd taken from past data only. Fitted on data to December 2014: `b_in = +0.14` (t = 1.93, no reversion inside the band), `b_out = -0.25` (t = -4.61), the two slopes differ (Wald p = 0.0001), band about -$0.96 to +$0.68, 28% of months outside. Newey-West standard errors (3 lags).

`dS = a + b*S` is the Dickey-Fuller regression, so t-statistics on spread slopes are compared with Dickey-Fuller critical values (-2.86 at 5%, -3.43 at 1%), not the normal table. `b_out` passes at 1%.

## Frozen specification

| Item | Choice |
| --- | --- |
| Target | `S(t+1) - S(t)`, $/bbl, month-end to month-end |
| Frequency | Monthly |
| Data | `data/clean/oil_monthly_clean.csv` only (`cl1`, `cl2`) |
| Predictors | The spread itself. No macro or industry predictor (see below) |
| Band | Mean ± 1.0 sd of the spread, expanding, past data only |
| Estimation | OLS, expanding window, re-estimated every month, at least 30 training months |
| Benchmarks | No change; plain mean reversion `dS = a + b*S`; ARMA(p,q) on the spread, p,q ≤ 3, order by BIC on pre-window data, Ljung-Box on residuals |
| Validation | Target months Jan 2005 to Dec 2014 (120) |
| Test | Target months Jan 2015 to Jun 2024 (114), run once |

## Data decisions

Taken in the shared cleaning step and kept here:

- **Brent is not used.** Daily Brent in `Industry_D` is out of line with its dates (534 extra rows; the July 2008 peak sits against February 2008). The lecturer confirmed it is a known data error. Daily crack spread and Baltic Dry are shifted the same way, so only their monthly values are used.
- **Monthly sheets only.** Weekly rigs, positioning and inventories are defined differently from the monthly ones (rigs about 2.4x, positioning about 1.8x, monthly inventories include products), so the two are never mixed.
- **Total Open Interest is dropped:** every cell is Long + Short. The "commercial" long/short columns probably cover all reporting traders, not commercials only.
- **April 2020:** CL1 settled at -37.63 on 20 April, the day before the May contract expired. No month-end price is negative (30 April CL1 = 18.84). The daily file keeps the price as traded.
- **Stress periods are kept** (2008-09, 2014-16 price war, 2020, 2022). They are real market events.

## Outliers in the target

Spread changes more than 4 sd from the training mean (sd $0.39) are flagged, not removed. Dummies are left to the diagnostics and robustness tasks, each tied to its event.

| Target month | Change ($) | z | Event |
| --- | ---: | ---: | --- |
| Dec 2008 | -2.60 | -6.6 | Financial crisis: demand collapse, storage filling, deep contango |
| Feb 2009 | +2.32 | +5.9 | Contango unwinds from its January 2009 extreme |
| Apr 2010 | -1.79 | -4.6 | Cushing stocks high, front-month weakness |
| Feb 2015 | -1.63 | -4.2 | 2014-16 OPEC price war: oversupply widens contango |
| Mar 2020 | -3.85 | -9.8 | COVID demand collapse and OPEC+ breakdown |
| May 2020 | +2.66 | +6.8 | Rebound after the negative-price episode |

Use one dummy per month, not a single outlier dummy: the moves have opposite signs and would cancel. Dummies only correct the in-sample fit and residual diagnostics; they are zero when forecasting, since nobody knows in advance that a month will be extreme.

## Release lags

Row `t` of the clean file holds what was known at the end of month `t`. Market prices (CL1, CL2, crack, Baltic Dry, equities, dollar, VIX) are used in their own month. Macro and industry data (IP, CPI, production, inventories, rigs, positioning, gasoline) are published the following month, so row `t` holds month `t-1`. Treasury yields are dated one month early in the workbook and are lagged one month too. The final model uses only CL1 and CL2, so it needs no release lag.

## Running it

```bash
python -m pip install numpy pandas scipy statsmodels matplotlib openpyxl jupyter
jupyter nbconvert --to notebook --execute --inplace models/Alan\&Ronan/spread_model.ipynb
```

The notebook needs `data/raw/Oil Data.xlsx` and `data/clean/oil_monthly_clean.csv`. It writes:

| Output | Content |
| --- | --- |
| `data/clean/oil_daily_cl1_cl2.csv` | Shared daily CL1/CL2 with `spread`, `cl1_last_trading_day`, `days_to_cl1_expiry`, `cl1_rolled` |
| `data/results/Alan&Ronan/forecasts_<window>.csv` | `month`, `origin`, `actual_change`, one `pred_*` column per model, `outside_band`, band limits |
| `metrics_<window>.csv`, `arma_order_<window>.csv` | Evaluation table and ARMA order search |
| `stationarity_tests_*.csv`, `stationarity_decisions.csv` | ADF, KPSS, ACF and the decision per series |
| `target_outliers.csv` | Flagged target months with their events |
| `cumulative_sse_*.png`, `spread_band_*.png`, `stationarity_acf.png` | Charts, 300 dpi |

The test window is run once. If `forecasts_test.csv` exists, the notebook reruns the test without saving and stops if the forecasts differ.

## Validation results (2005-2014)

Out-of-sample R² is measured against the no-change forecast. Above zero beats it.

| Model | RMSE ($) | OOS R² | Direction | Clark-West p |
| --- | ---: | ---: | ---: | ---: |
| No change | 0.581 | | | |
| Plain mean reversion | 0.576 | 1.8% | 57.5% | 0.059 |
| ARMA(2,0) | 0.584 | -0.9% | 55.8% | 0.122 |
| **Band mean reversion (final)** | **0.561** | **6.8%** | 54.2% | **0.009** |
| Final model, outside-band months only (54) | 0.665 | 10.2% | 64.8% | |

The band model also beats plain mean reversion (Clark-West p = 0.004). Diebold-Mariano against no-change is not significant (p = 0.22). That test is known to be conservative for nested models, and 120 months is a small sample.

## Test results (Jan 2015 to Jun 2024, 114 months, run once on 14 Nov 2026)

The specification was committed before the test window was opened (commit `f963e99`).

| Model | RMSE ($) | MAE ($) | OOS R² vs no-change | Direction | Clark-West p |
| --- | ---: | ---: | ---: | ---: | ---: |
| No change | 0.678 | 0.397 | | | |
| Plain mean reversion | 0.641 | 0.373 | 10.5% | 56.2% | 0.011 |
| ARMA(1,0) | 0.641 | 0.373 | 10.6% | 56.2% | 0.011 |
| **Band mean reversion (final)** | **0.622** | **0.368** | **15.7%** | 56.2% | **0.003** |
| Final model, outside-band months only (26) | 0.724 | 0.553 | 36.6% | 76.9% | |

- The band model beats plain mean reversion by 5.8% (Clark-West p = 0.004).
- Diebold-Mariano against no-change: p = 0.069. Conservative for nested models.
- Not driven by 2020: without that year the OOS R² is 13.6%. It is 16.2% over 2015-19 and 15.5% over 2020-24.
- BIC picks ARMA(1,0) on pre-2015 data, which is plain mean reversion, so the two benchmarks are the same model here.
- The largest miss is March 2020 (spread fell $3.85, forecast about zero). The model does not see shocks coming. It says what tends to happen after the spread is already stretched.
- The 77% direction rate rests on 26 months. Treat it as indicative.

## Stationarity

ADF (H0 unit root; constant for series without a trend, constant + trend for trending log levels; up to 12 lags by BIC; Fuller 5% critical values) and KPSS (H0 stationary) on data to December 2014, full sample as a check, combined as in the Unit Roots lecture: ADF rejects and KPSS does not = stationary; the reverse = unit root.

| Series | ADF | KPSS (5% cv 0.463 / 0.146 with trend) | ACF lag 1 → 12 | Use |
| --- | ---: | ---: | --- | --- |
| Spread S | -4.90 | 0.59 | 0.82 → 0.19 | level |
| ΔS | -12.07 | 0.06 | -0.07 → -0.03 | |
| log CL1 (with trend) | -1.84 | 0.18 | 0.99 → 0.82 | 100·Δlog |
| CL1 return | -13.48 | 0.11 | 0.12 → -0.07 | |
| log IP (with trend) | -3.13 | 0.33 | 0.98 → 0.68 | 100·Δlog |
| IP growth | -3.72 | 0.23 | 0.24 → -0.04 | |

- **Spread:** both tests reject before 2015, the conflicting case. It is treated as stationary and modelled in levels: the ACF dies out within about a year, the full sample is clearly stationary (both tests agree), and Zivot-Andrews rejects a unit root once a level break is allowed (-6.08 against -4.81 at 5%, break in September 2004). The spread is a forward premium, a series the lecture flags as close to a unit root, where ADF has low power.
- **CL1 price has a unit root, returns and the spread do not.** Regressing on the price would be spurious; this backs modelling the spread (or the return), not the price.
- Every candidate predictor has a decision and transformation in `stationarity_decisions.csv`: log-differences for prices, indices and quantities; plain differences for rates, the yield curve, net positioning, the crack spread and CPI inflation; VIX and dollar returns in levels. Crack spread and production changes are flagged because KPSS also rejects. Inventories and gasoline are seasonal.

## Data checks

- Every date in the clean file is a calendar month-end, with no missing or extra month.
- Daily month-end CL1 and CL2 match the monthly clean file exactly.
- Five month-ends checked against the raw workbook (Sep 2008, Nov 2014, Apr 2020, Feb 2022, Jun 2024): CL1 and CL2 equal the raw last-trading-day prices, and IP in row `t` equals the raw value for month `t-1`. The -37.63 settlement on 20 April 2020 is not a month-end; April 2020 uses 30 April.

## Why monthly and not weekly

Tested on validation data only, same grid at both frequencies, during exploration.

- CL1 changes contract around the 20th of each month. Month-end always falls 11 to 16 trading days before expiry, so the monthly spread is close to a constant-maturity measure. Fridays fall anywhere from 0 to 22 days before expiry.
- 23% of weekly changes span a roll and compare two different contract pairs. Those weeks are 70% more volatile. Excess kurtosis of weekly changes is 45, against 5 monthly.
- Weekly models look strong when roll weeks are included (OOS R² up to 32%). That is the mechanical jump when CL1 switches contract. Nobody can earn it.
- On weeks with no roll, where the change is a real P&L: 1,240 specification runs, none beats no-change in both halves of validation. LASSO sets every coefficient to zero.
- ARIMA (17 orders, AIC and BIC selection), band models, asymmetric slopes and seasonal terms all fail weekly as well.
- Daily was not run. It has the same roll problem every month, and no predictor in the workbook is daily.

## Why no other predictor

Each of 18 candidates was added to the model on the clean dataset: inventories, production, rigs, positioning, CL1 return, crack spread, Baltic Dry, dollar, VIX, yield curve, CPI, IP growth, equities, gasoline. One of 18 (gasoline price change) improves both halves of validation, which is what chance alone would give. LASSO and Ridge on all predictors lose to no-change. Seasonal dummies and separate contango/backwardation slopes do not help. We kept the model with no extra predictor.

**Correction to an earlier result.** Our first search reported lagged industrial production growth as a robust predictor. That came from a timing slip: monthly macro data was timed against the last trading day, which gave an extra month of lag in the 30% of months that end on a weekend or holiday. Nothing looked ahead, but the lag was not the same every month. With a consistent lag, IP growth does not help (plain mean reversion + IP: -0.2%). IP growth is not in the final model.

## Limits

- The target is the shape of the curve, not a tradeable return. The front contract expires inside every month. A trading rule has to switch contract pairs at expiry. Use `oil_daily_cl1_cl2.csv` for that.
- About 28% of months give a signal, so the evidence rests on a few dozen calls.
- We searched many specifications on validation data before settling on this one. The split-half checks and the single test run are the guard against that.
- 2008-09 and 2020 dominate the squared errors. April 2020 is in the test window.
- The expiry calendar in the daily file is estimated from the file's own trading days.
