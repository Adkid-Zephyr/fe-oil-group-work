# Felix's model

Monthly OLS forecasts the next percentage change in the CL1 continuous front-month series using lagged CL1 momentum, lagged CL1-CL2 curve shape and DXY returns lagged an extra month.

## Inputs: personal frozen cleaning snapshot v1.0.0

Mike is handling the group cleaning. This copy is for Felix's draft only, not the group's agreed dataset. Reconcile against Mike's output before final comparison.

The model reads only these files under `data/cleaning_snapshot/Cleaned data/`:

- `industry_monthly.csv`: `date`, `month`, `cl1`, `cl2`.
- `macro_monthly.csv`: `date`, `month`, `dxy_return_decimal` (reconciled with `dxy_return_pct`).
- `monthly_targets.csv`: authoritative target, previous-month origin, evaluation membership and shared no-change benchmark.

The loader checks dataset version, original-source identity, file hashes against `Data quality/manifest.json`, continuous monthly alignment, finite inputs, target arithmetic and evaluation dates. It does **not** fall back to raw Excel. Read [the cleaning report](data/cleaning_snapshot/CLEANING_REPORT.md) for unresolved metadata.

The 534 undated daily records, non-CL daily/monthly differences, mislabeled monthly OI sum and weekly source interpolation do not enter this model. Contract rolling/adjustment, release-time metadata and vintage revisions remain unresolved. DXY decimal scale is the documented working interpretation, not independently verified vendor metadata.

## Results after migration

All 114 predictions, targets and both benchmark forecasts exactly reproduce the recorded pre-migration numerical values in this tested environment. OLS RMSE remains 12.9171 pp and MAE 8.4978 pp. Cleaning did not create a performance improvement. The three inputs, regression, lags, 2014 training cut-off and 2015–2024 evaluation dates are unchanged.

No change is the group's shared benchmark (RMSE 13.4383 pp). The original historical-mean comparator (13.4076 pp), its OOS R-squared and bootstrap remain explicitly labelled supplementary research comparisons. The bootstrap interval includes zero; a stable advantage is not established.

## Reproduce from the repository root

```bash
python -m pip install -r "Felix's model/requirements.txt"
python "Felix's model/analyze.py"
python "Felix's model/test_model.py"
python "Felix's model/build.py"
```

This snapshot is frozen; do not regenerate or replace the group dataset from this folder. A changed source/version/hash requires explicit review rather than bypassing the loader's checks. Run in the full repository layout, not with `analyze.py` alone.

## Files

- `analyze.py`: cleaned-data loader, expanding-window forecasts, diagnostics and verification.
- `test_model.py`: migration, corruption and chronology regression tests.
- `build.py`: embeds analysis, code and English report into `dist/index.html`.
- `results/`: forecasts, model-only monthly inputs and analysis JSON with input hashes.
- `validation/pre_cleaning_reference.json`: predictions recorded before this migration, tied to the original repository commit.
- `source/PROTOCOL.md`: original model protocol plus a dated migration addendum; original design history remains visible.

Open `dist/index.html` in a browser for the English-only interactive report. It links to shared cleaned data and explains why the predictions did not change. This draft update is not published to the live site.

This is an AI-assisted research draft for group verification, not a submitted assessment. The target is a continuous-series price-change proxy, not validated executable futures P&L.
