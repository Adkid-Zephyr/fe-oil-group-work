# Shared benchmark - completed by Felix

We use a **no-change benchmark**: next month's oil price is predicted to equal this month's. Equivalently, the predicted monthly percentage change is zero. It is simple and tests whether our models improve on this basic forecast.

## Use it

- Ready-to-use forecasts: [Benchmark results/forecasts.csv](Benchmark%20results/forecasts.csv).
- `month` is the target month; `origin` is the previous month.
- Compare monthly return forecasts with `benchmark_return_pct` (percentage points), or price forecasts with `benchmark_price` (USD/barrel).
- Use the same target, dates and units for every model. Report RMSE and MAE; lower is better. Price-level errors must be computed separately.
- Current evaluation: January 2015-June 2024, 114 months, using CL1 from `Industry_M`. No fitting or tuning is required. Other frequencies or test periods require matching benchmark forecasts.

To regenerate from the original workbook, install `numpy`, `pandas` and `openpyxl` (also included in Felix's requirements), then run from the repository root:

```bash
python "Data and guideline/benchmark.py"
```

Historical-mean and AR(1) comparisons are retained in `Optional comparisons`, reproducible with `compare_models.py`. They are optional background, not the selected shared benchmark. Felix's earlier research report still uses its original historical-mean comparison.
