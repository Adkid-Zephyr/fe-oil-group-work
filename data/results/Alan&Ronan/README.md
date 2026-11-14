# Alan and Ronan results: monthly CL1-CL2 spread

Produced by `models/Alan&Ronan/run_validation.py` and `run_test.py`.

- Target: next month's change in `CL1 - CL2`, $/bbl. `month` is the target month, `origin` the month the forecast is made.
- Protocol: expanding window, one-step forecasts, re-estimated every month.
- `forecasts_<window>.csv`: `actual_change` and one `pred_*` column per model. `pred_band` is the final model. `outside_band` = 1 when the spread at the origin is outside the band, which is when the model expects a move.
- `metrics_<window>.csv`: RMSE, MAE, out-of-sample R² against each benchmark, direction hit rate, Clark-West and Diebold-Mariano tests.
- Not comparable with the CL1 return results elsewhere in this folder: different target and units.
