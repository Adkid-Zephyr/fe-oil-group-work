# Felix: fixed training split at 2014

**Historical experiment:** the original cleaned inputs were removed in main `51d116d`. Reproduce this experiment at commit `a32df7627c38c583602fbb0f37658cd7d6be7532` in a separate checkout. For Mike's current shared data, use the root `felix-model.ipynb` and [handoff guide](../handoff/README.md).

Monthly and weekly runs completed on 10 November 2026. Monthly uses Mike's cleaned monthly data. Weekly uses the cleaned daily and weekly tables present on Ronan's branch and his Friday price-alignment convention. Input identities and the exact source commit are recorded in `weekly_provenance.json`.

## Design

- Input: Mike's `data/clean/monthly_levels/oil_monthly_clean.csv`, as committed to main at `bc8f13a`. No raw workbook loading or changes to shared data.
- Target: one-period CL1 percentage change, `100 * (CL1(t)/CL1(t-1)-1)`.
- Predictors: previous-period target change, previous-period `100*(CL1-CL2)/CL1`, and the DXY monthly return from two months before the target month, converted to percentage points.
- Fit OLS with an intercept once using targets before 1 January 2014. Coefficients stay fixed throughout testing. Each test prediction uses the latest permissible observed inputs; this is sequential one-step forecasting, not a ten-year forecast made at the end of 2013.
- Train: February 1995-December 2013, 227 complete observations. Test: January 2014-June 2024, 126 observations. The source does not include the rest of 2024. No test rows are excluded.
- Benchmark: zero change. No tuning, imputation, winsorisation or removal of the 2020 period.

## Monthly results

| Model | RMSE (pp) | MAE (pp) | Direction accuracy |
| --- | ---: | ---: | ---: |
| Three-variable OLS | 12.5286 | 8.2950 | 57.14% |
| No change | 13.0766 | 8.5231 | Not applicable |

RMSE is 4.19% lower than no change; OOS R-squared against no change is 8.21%. These are descriptive historical results. The old report already used overlapping test years, so this revised split is not a newly untouched confirmation sample. Continuous CL1 changes are not executable futures returns.

## Reproduce

From the repository root, install `models/Benchmark/requirements.txt`, then run:

```bash
python models/Benchmark/fixed-split-2014/run.py --weekly
python models/Benchmark/fixed-split-2014/test_run.py
```

Outputs: `data/results/Felix-fixed-split-2014/`. The manifest records input hashes, training and test dates, fixed coefficients and exclusions. Tests check the cutoff, independent statsmodels estimates, invariance to changed test outcomes, future-data truncation and the proposed weekly date alignment.

## Weekly construction and results

Ronan's `weekly_returns()` uses the Fridays in `industry_weekly.csv`, matching the last daily CL1/CL2 close on or before each Friday. Our implementation selects the same actual price row and checks it is no more than six days old. Both input files are byte-identical to his branch at `df0369a4e3e1c5c7c36a1e504f413ee0c05f3285`. The weekly input table itself contains fundamentals, so CL1/CL2 still come from the cleaned daily table, as in Ronan's code.

We use his continuous CL1 change target, consistent with our monthly model. We do not substitute his approximate roll-adjusted held-contract target or his larger predictor set. Weekly momentum and curve use the preceding week. DXY remains a monthly signal from Mike's file and becomes usable only after the end of the following month. No weekly dollar observations are invented. No crisis weeks are removed.

Train: 10 February 1995-27 December 2013 (986 complete weeks). Test: 3 January 2014-19 July 2024 (551 weeks), with no excluded test rows. The 1995 training start is set by availability of the lagged monthly dollar signal. Model coefficients are fitted once and stay fixed.

| Model | RMSE (pp) | MAE (pp) | Direction accuracy |
| --- | ---: | ---: | ---: |
| Three-variable OLS | 5.6037 | 3.9377 | 52.09% |
| No change | 5.5631 | 3.9188 | Not applicable |

Weekly OLS has about 0.73% higher RMSE than no change (OOS R-squared -1.47%). This specification adds no forecast improvement on the weekly test sample. Monthly OLS improves relative to its own benchmark, while weekly OLS does not. Raw weekly and monthly RMSE levels cannot directly rank frequency quality because the horizons differ. Their available end dates also differ.

Both runs are historical one-step forecast evaluations. Updated lagged inputs are allowed during testing, but test outcomes never enter coefficient estimation. The weekly data construction and predictions pass independent checks against Ronan's price convention and statsmodels OLS, as well as future-truncation checks.
