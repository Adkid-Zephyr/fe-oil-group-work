# Felix: fixed training split at 2014

Monthly run completed on 10 November 2026. Weekly model evaluation is pending confirmation of the cleaned daily source used to construct weekly prices; Mike's uploaded cleaning script produces monthly data only.

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
python models/Benchmark/fixed-split-2014/run.py
python models/Benchmark/fixed-split-2014/test_run.py
```

Outputs: `data/results/Felix-fixed-split-2014/`. The manifest records input hashes, training and test dates, fixed coefficients and exclusions. Tests check the cutoff, independent statsmodels estimates, invariance to changed test outcomes, future-data truncation and the proposed weekly date alignment.

## Proposed weekly construction (pending input confirmation)

Use the existing cleaned daily CL1/CL2 table, selecting the last actual observation in each Friday-ending week. Drop the final incomplete week; preserve missing weeks in the calendar grid. Do not interpolate monthly oil prices to invent weekly observations. Weekly momentum and curve use the preceding week. Monthly DXY is carried forward only after the end of the following month, using Mike's monthly file. This is a weekly model with a monthly dollar signal, not a weekly DXY return series. The daily table is the earlier shared audit output, not Mike's monthly cleaning output.

After source confirmation, `run.py --weekly` runs both frequencies. Compare each model with its own same-frequency benchmark; weekly and monthly raw RMSE values measure different horizons and cannot directly rank frequency quality.
