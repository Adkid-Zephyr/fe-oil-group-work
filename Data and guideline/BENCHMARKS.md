# Benchmark and baseline protocol

## Recommended comparison

For Felix's existing monthly CL1 percentage-change task, retain **the expanding historical mean as the primary benchmark**, **zero change as the naive benchmark**, and use **AR(1) with an intercept as a simple econometric baseline**. These roles distinguish the comparisons for this project; the words benchmark and baseline are often used interchangeably.

| Role | Forecast for target month t | Why include it? |
| --- | --- | --- |
| Primary benchmark | Mean of eligible realized monthly changes strictly before t | Tests whether predictors add information beyond a constant expected change. Preserves the original OLS protocol. |
| Naive benchmark | Zero percentage change, equivalent to predicting next CL1 price equals the latest price | A transparent no-change reference satisfying the brief's simple-benchmark requirement. This is a random walk in price levels, not persistence of the last return. |
| Econometric baseline | r_hat(t) = a + b * r(t-1), estimated by OLS | Tests whether the extra carry and dollar predictors improve on a single lag of the target. No lag-order search is needed. |
| Candidate | Felix's OLS with momentum, carry and lagged dollar change | Provides an interpretable multivariate comparison. |

Fama-French is not the natural benchmark for this task: it addresses equity factor exposures and requires a different explanatory setting. A broad equity index also changes the forecast target. General ARIMA is a possible candidate, but searching its orders is unnecessary for the simple baseline.

## Common evaluation design

- Target: `r(t) = 100 * (CL1(t) / CL1(t-1) - 1)`, in percentage points, using `Industry_M`.
- Horizon: one month ahead. Initial training ends December 2014. Test targets run January 2015 through June 2024 (114 months).
- Refit every month using an expanding window and outcomes strictly earlier than the forecast month.
- Use exactly the same eligible training rows as the existing OLS model for all fitted comparisons: complete target, momentum, carry and dollar observations. This isolates model specification; standalone simpler models could use more history, but that would be a separate experiment.
- Momentum and carry use t-1. DXY uses t-2 as a conservative availability convention. This does not establish real-time vintage availability; the workbook lacks release-time metadata.
- Keep 2020. Do not remove difficult observations to improve the score. Align month keys before shifting variables. No random train/test split or holdout-based tuning.
- Report RMSE (primary), MAE, OOS R-squared against the historical mean, and directional accuracy as supplementary information. Zero-change forecasts abstain from direction, so directional accuracy is not applicable.
- Do not use MAPE for percentage changes near zero. Do not interpret higher in-sample R-squared as out-of-sample evidence.
- `OOS R2 = 1 - sum((actual-model)^2) / sum((actual-mean)^2)`. Positive is better than the mean reference on the same test dates.

Run `python "Data and guideline/benchmark.py"` from the repository root after installing Felix's requirements. Outputs and verification are in `Benchmark results`.

The original OLS results were already available when AR(1) was added. The additional comparison is retrospective. Preserve that disclosure; do not describe it as an independent confirmation sample. Team candidates with another target or frequency need a newly agreed shared protocol, not a combined ranking of incompatible RMSEs.

## Trading interpretation

Forecast accuracy and executable profitability answer different questions. The CL1 series is a continuous futures price proxy. A trading comparison would require contract-roll rules, execution prices, margin, funding and transaction costs. A no-position strategy can serve as a trading reference, but it does not replace a statistical forecast benchmark.

## Sources

- Coursework PDF, pp. 2-4, archived in `Canvas`: simple naive comparison, diagnostic tests and out-of-sample evaluation.
- Hyndman and Athanasopoulos, [Forecasting: Principles and Practice, section 5.2](https://otexts.com/fpp3/simple-methods.html): mean and naive forecasts as standard reference methods. Accessed 27 October 2026.
- Felix's `source/PROTOCOL.md`: existing target, split and primary historical-mean comparison.

These are repository recommendations. The recording discussed selecting a simple benchmark but did not specify or approve this exact model set, target or split.
