# Shared cleaned data v1.0.0

**Read [the cleaning report](../../guidelines/CLEANING_REPORT.md) before choosing predictors.** The files are standardised and auditable; several source definitions/timestamps remain unresolved. Raw numeric values are retained, not automatically corrected.

## Files

| File | Rows | Purpose |
|---|---:|---|
| `industry_daily.csv` | 8,692 | Dated daily source observations; non-CL alignment needs review |
| `industry_weekly.csv` | 1,803 | Weekly observations, plus a source-interpolation flag and an unimputed commercial-long column |
| `industry_monthly.csv` | 355 | Monthly industry observations; misleading OI field renamed |
| `macro_monthly.csv` | 355 | Monthly macro observations; original decimal DXY and a derived percentage-point version |
| `stock_prices_monthly.csv` | 355 | Monthly stocks; missing Shell history retained |
| `monthly_observations.csv` | 355 | All three monthly tables joined by month, with sheet-prefixed fields |
| `monthly_targets.csv` | 355 | Consecutive-month CL1 targets and the common no-change benchmark; first target missing |

Dates are ISO `YYYY-MM-DD`; month keys are `YYYY-MM`. Empty CSV fields mean missing, never zero. Every native row retains a one-based `source_excel_row`. No return or filling is performed on the native tables. Data are oldest first. Keep all 355 rows when constructing monthly lags before applying your model-specific valid-row filter.

## Quick start in Python

```python
from pathlib import Path
import pandas as pd

folder = Path("data/clean")
observations = pd.read_csv(folder / "monthly_observations.csv")
targets = pd.read_csv(folder / "monthly_targets.csv")

# For model evaluation, not for fitting to target-month information:
evaluation = targets.loc[targets["is_shared_evaluation"] & targets["target_valid"]].copy()
assert len(evaluation) == 114

# Example: join a team's one-step-ahead predictions, labelled by target month.
# Predictions must already have been produced using only permissible past data.
predictions = pd.read_csv("your_predictions.csv")  # month, forecast_return_pct
comparison = evaluation.merge(predictions, on="month", validate="one_to_one")
assert comparison["month"].tolist() == evaluation["month"].tolist()
assert comparison["forecast_return_pct"].notna().all()
model_error = comparison["actual_return_pct"] - comparison["forecast_return_pct"]
benchmark_error = comparison["actual_return_pct"] - comparison["benchmark_return_pct"]
print("Model MAE:", model_error.abs().mean())
print("Benchmark MAE:", benchmark_error.abs().mean())
```

The observation table is **not lagged**. Target-month fields are not permissible predictors merely because they are on the same row. Preserve the monthly grid, apply explicitly justified availability lags, then drop rows missing only your chosen inputs. A global `dropna()` on the whole table unnecessarily removes Shell's 127 missing early months and changes the model-comparison sample.

## Do not overlook

- `industry_weekly.csv`: prefer `commercial_long_unimputed` to avoid the 2001-09-07 source interpolation, which used a future endpoint. The raw `commercial_long` value is retained and marked.
- `industry_monthly.csv`: `commercial_long_plus_short_source` is the literal sum in Excel, originally labelled Total Open Interest. It is not a separately verified OI measurement.
- Daily Brent/crack/BDI need alignment review; monthly counterparts are not interchangeable with daily resampling. No guessed column shifts have been applied.
- Missing data, negative prices and large moves are retained. Do not use logarithms on nonpositive daily prices.
- Release timestamps, vintage history, roll rules, stock adjustments and some unit scales are unknown. See the [field dictionary](../../guidelines/Data%20quality/data_dictionary.csv).

Rebuild with `python guidelines/clean_data.py`; run `python -m unittest discover -s guidelines -p "test_clean_data.py"` from the repository root. Original data remain in `../raw/Oil Data.xlsx`.
