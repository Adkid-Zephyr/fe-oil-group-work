# Coursework code

`oil-forecasting.ipynb` is the whole analysis. Install the packages with `pip install -r requirements.txt`, then run it from this folder with Restart & Run All.

## What the notebook does

1. **Data and roll.** Builds one row per Friday from the daily CL1 and CL2 prices, the weekly fundamentals and the monthly series, each entered only once it was public. Removes the monthly contract switch from the target, so the target is the change a rolled position earns. Checks 14 values against hand calculations and stops if any fails.
2. **Stationarity.** ADF, Phillips–Perron and KPSS on training data, and the Dickey–Fuller tests on the generic spread and on the held spread.
3. **Predictors.** The storage-theory predictors with their expected signs, what was left out and why, and the 18 Lasso candidates.
4. **Four models.** No-change, mean-reversion, storage model and Lasso. Each must beat the one before it.
5. **Models on training.** Each model estimated on the training sample: the storage model built general-to-specific, and the predictors the Lasso keeps.
6. **Diagnostics.** Autocorrelation, heteroskedasticity, normality, functional form and parameter stability, each with a remedy agreed in advance.
7. **Validation and freeze.** Expanding-window forecasts on November 2009 to February 2017. Picks the winner and writes `outputs/freeze.json`.
8. **Test.** March 2017 to June 2024, using only the frozen settings.
9. **Trading rule.** What a simple rule would have earned after costs, with block-bootstrap intervals.

Anything added after the test had been seen is labelled post-test in Section 8.

## Split

By the week being forecast: training to 30 October 2009 (765 weeks), validation to 24 February 2017 (382 weeks), test from 3 March 2017 to 28 June 2024 (383 weeks).

## Outputs

Tables are written to `outputs/` as CSV files named by section (`t2_` to `t9_`). Figures go to `outputs/figs/`.
