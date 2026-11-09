# Alan and Ronan's model: LASSO forecast of monthly oil futures returns

**Question for the trader:** do fundamentals and macro data help forecast next month's oil futures return?

**Status:** specification frozen on 9 November 2026, before any look at the 2015-2024 test window. The test has not been run. It will be run once, with `--run-test`, after the group agrees the target. Any change to the specification below after that point must be recorded here with a date and reason.

## Specification

| Item | Choice |
|---|---|
| Frequency | Monthly. One forecast per month, one row of data per month. |
| Forecast horizon | One month ahead, made at each month-end. |
| Main target | Tradable return: `CL1(t+1) / CL2(t) - 1`, the return from holding one contract. Avoids the jump when CL1 switches contract. |
| Second target | Raw CL1 change, `CL1(t+1) / CL1(t) - 1`, the group's shared target, reported for comparison. Final choice to be agreed by the group. |
| Main model | LASSO, predictors standardised on training data only, penalty chosen by 5-fold time-series cross-validation, re-tuned every 12 months, coefficients refitted every month. |
| Checks | Ridge (cross-validation), LASSO tuned by BIC, LASSO with a rolling 10-year window. |
| Comparisons | No-change forecast (shared benchmark), historical mean, Felix's specification (momentum, curve spread, dollar lagged one month) fitted on the same sample. |
| Window | Expanding, starting February 1998 (the first month every predictor exists). |
| Validation | Forecasts for January 2005 to December 2014 (120 months). Used for all choices. |
| Test | Forecasts for January 2015 to June 2024 (114 months). Used once. |
| Scores | RMSE, MAE, out-of-sample R-squared against no change (overall and by half), MAE gain with a Diebold-Mariano test, Clark-West test, direction hit rate. |

## Predictors and information timing

29 candidates are built. Lag is the gap between a value's label and the forecast origin, set by when the data would have been known.

| Group | Predictors | Lag |
|---|---|---|
| Prices | last month's return, returns 2 and 3 months ago, 12-month return, curve spread and its change, Brent premium over WTI, change in crack spread, change in Baltic Dry Index | 0 |
| Market | VIX level and change, S&P 500 return, dollar index return | 0 |
| Macro | industrial production growth, change in CPI inflation | 1 month (published mid next month) |
| Rates | 3-month yield and its change, term spread | 2 months (the workbook labels yields one month early) |
| Monthly fundamentals | inventories (monthly change, vs a year ago, vs the same month over the last 3 years), production change, rig count change, hedgers' net position and its change | 1 month (published after month-end) |
| Weekly, made monthly | inventory changes published by month-end, latest CFTC hedgers' position, rig count change over the last 4 weeks | weeks dated at least 7 days before month-end |
| Daily, made monthly | realised volatility of daily CL1 returns within the month | 0 |

**Stationarity rule.** On pre-2015 data, any predictor whose ADF test cannot reject a unit root at 10% is replaced by its monthly change, or dropped if its change is already included. This turned Brent premium, term spread, inventories vs seasonal and the weekly hedgers' position into changes, and dropped the 3-month yield level. Final list: 28 predictors.

**Left out:** daily Brent, crack spread and Baltic Dry Index (do not line up with their monthly versions, 534 undated rows), "Total Open Interest" (it is long plus short), Shell (127 missing months), oil company shares and gasoline prices (mostly move with oil itself).

## Diagnostics

- ADF tests on the target and every predictor.
- The order in which predictors enter the LASSO path on pre-2015 data.
- A companion OLS with the first four predictors to enter the path, fitted on pre-2015 data: Newey-West standard errors, Ljung-Box, Breusch-Pagan, White, Chow test at December 2008, CUSUM, VIF.
- Autocorrelation and volatility clustering in the main model's validation errors.

## Files

| File | What it does |
|---|---|
| `lasso_model.py` | The model, steps 1 to 9. Step 9 (test) only runs with `--run-test`. |
| `features.py`, `compare_return_vs_curve.py`, `explore_frequency_and_models.py` | Earlier exploration: frequency choice, and the LASSO return model compared with a curve (spread) model. Validation window only. |

Outputs go to `data/results/Alan&Ronan/lasso_model/`. Forecast files use `month` (the month being forecast), `actual`, and one column per model.

## Run

From the repository root:

```bash
python "models/Alan&Ronan/lasso_model.py"              # steps 1 to 8, about 15 seconds
python "models/Alan&Ronan/lasso_model.py" --run-test   # adds the test, run once only
```

Tested on Python 3.11 with the versions in requirements.txt. Reads the shared cleaned tables in `data/clean/`.
