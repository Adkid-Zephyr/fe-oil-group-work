# Felix: historical fixed-2014 results

**Protocol:** fit once using targets before 2014; test from 2014 to the available end of 2024. These are not the current group notebook's 2005–2014 validation results.

| File | Contents |
| --- | --- |
| [metrics.csv](metrics.csv) | Weekly/monthly OLS and no-change RMSE, MAE and directional accuracy. |
| [monthly_forecasts.csv](monthly_forecasts.csv) | 126 predictions, January 2014–June 2024. |
| [weekly_forecasts.csv](weekly_forecasts.csv) | 551 predictions, 3 January 2014–19 July 2024. |
| `monthly_prepared.csv`, `weekly_prepared.csv` | Inputs for this historical experiment, not replacement shared clean data. |
| [analysis.json](analysis.json) | Input hashes, training/test dates and fixed coefficients. |
| [validation.json](validation.json) | Recorded checks on the experiment. |

[Method and historical reproduction instructions](../../../models/Benchmark/fixed-split-2014/README.md) · [Current group entry point](../../../oil-forecasting.ipynb).
