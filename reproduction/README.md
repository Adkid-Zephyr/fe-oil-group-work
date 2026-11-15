# Felix: task 9 reproducibility review

**Reviewed on 15 November 2026. Result: the uploaded notebook runs top to bottom and its core results reproduce, with three recorded minor differences. This is a review of the current tasks 1–3 notebook, not sign-off on a complete final group notebook.**

## Version and scope

- Fresh remote clone of main commit `5e9742479073d6a114eebb362da02c6130bd5f34`.
- Actual notebook: root `oil-forecasting.ipynb`, 33 cells, 17 executable code cells.
- A new virtual environment was installed for the clone. CPython 3.12.14, macOS arm64; exact dependency versions are pinned in root `requirements.txt`.
- Every cell ran in order in a fresh kernel. The runner uses an isolated copy of tracked files, not prior notebook memory or another project's data.
- Reference files were captured before execution. The saved test forecasts were reproduced, not retuned. Raw workbook and shared monthly input remained byte-identical.
- Runtime test forecasts, metrics and ARMA search results were captured separately because the notebook does not overwrite saved test tables when they already exist.

## Reproduced core results

| Window | Months | Band RMSE | Band MAE | OOS R² vs no change | Clark–West p | DM p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Validation, 2005–2014 | 120 | 0.561066 | 0.384045 | 6.8111% | 0.008687 | 0.220205 |
| Test, 2015–June 2024 | 114 | 0.622320 | 0.368305 | 15.6784% | 0.003002 | 0.068940 |

Errors are in USD/barrel. These reproduce the existing model; no new specification search was performed.

Independently recomputed all 234 band predictions using normal equations, checked dates, actual spread changes, past-only band thresholds and outside-band flags, and recomputed RMSE, MAE and OOS R² for every model. Maximum independent band-prediction difference was below `1e-15`. The recorded stationarity tables, transformation decisions and outlier table also reproduced within tolerance. Five generated PNGs decoded at the expected dimensions; the cumulative-SSE and stationarity figures received visual checks.

## Differences found (not hidden)

| File | Difference | Impact |
| --- | --- | --- |
| `arma_order_validation.csv` | Unselected ARMA(3,3): AIC/BIC differ by 0.00039447; residual Ljung–Box p differs by 0.00018090. | Numerical optimizer/environment drift; the selected ARMA(2,0) is unchanged. The exact cause is not independently isolated. |
| `forecasts_validation.csv` | One ARMA forecast exceeds the strict comparison tolerance; maximum difference 0.00000184976 USD/barrel. | No change to the displayed three-decimal metrics. Band forecasts are unaffected. |
| `metrics_test.csv` | Saved label `Plain mean reversion (AR)` versus notebook label `Plain mean reversion`. | Label-only mismatch. Numeric test metrics differ by at most 2.66e-10. |

The first strict run reported these as failures; `initial_run.json` preserves that evidence. The final checker keeps the exact differences and classifies these narrow reviewed cases as warnings. It does not rewrite the reference results to force a match.

Comparison defaults are `atol=1e-6`, `rtol=1e-7`, with identical shapes, columns, date strings and missingness. Only validation ARMA forecasts below 1e-5, unselected ARMA search differences below 1e-3 with an unchanged best BIC order, and the explicit label alias above can be warnings. All other mismatches fail. `--strict` exits nonzero for these warnings too.

## Fixes supplied on Felix's branch

- Corrected the README command: `models/Alan&Ronan/spread_model.ipynb` does not exist; the shared notebook is `oil-forecasting.ipynb`.
- Added pinned installation requirements and a single reproducibility command.
- Added isolated execution and output comparisons, including live test objects, so unchanged saved files cannot masquerade as freshly computed results.
- Corrected malformed cumulative-SSE axis units in the notebook and matching Python chart helper. Model calculations, coefficients, data and committed CSV reference values are unchanged.

## Remaining group work and limits

1. **The repository currently integrates tasks 1–3 only.** Full predictor selection, final-model diagnostics, robustness and trading-rule sections (tasks 4–8) are not all present in this notebook. Repeat this review after the group supplies the final merged notebook. The historical exploration scripts are not a substitute for integrated submission sections.
2. **Stationarity decisions use full-sample results.** In the decision cell, `lvl_full['verdict']` affects whether a level is kept, despite a setup comment saying decisions use pre-2015 data only. The full-sample tables can be a descriptive check, but the authors need to resolve that decision-rule inconsistency before claiming purely pre-test selection. This review did not change transformations or retune the model.
3. **Statistical interpretation is not certified by execution.** In particular, the README applies ordinary Dickey–Fuller critical values to a threshold/band slope. That justification needs the model authors' methodological review. The numerical calculations reproduce; this audit does not validate that inferential claim.
4. `oil_daily_dictionary.csv` is retained but not regenerated by the notebook. The daily data itself is regenerated and checked. The shared monthly CSV/dictionary are inputs and are checked for preservation, not rebuilt by this notebook.
5. The pinned environment was tested on macOS arm64 only. PNG byte identity is not a reproducibility criterion: fonts/rendering and metadata can differ. Numerical data are compared directly.

## Run and inspect

See the root README for fresh-clone commands. Run:

```bash
python reproduction/run_notebook.py
python reproduction/run_notebook.py --strict
```

The second command intentionally returns nonzero if even the recorded minor differences remain. Both write evidence under `.repro/`; use `--output .repro/another-run` to retain separate runs. No source files or shared outputs are overwritten. The runner adds an execution-only capture cell after the original notebook, removes it from the delivered executed notebook, and uses it solely to inspect runtime test results.

- `latest_report.json`: checked run, environment, input hashes and every comparison.
- `initial_run.json`: first strict comparison before classifying the minor differences.
- `.repro/oil-forecasting.executed.ipynb`: local executed copy for review (generated, not committed).
- `.repro/execution.log`, `.repro/regenerated/`, `.repro/figures/`: local detailed execution evidence.

Historical Felix OLS notebooks remain separate. This review does not reopen or modify their research claims and does not claim the whole project has never previously examined overlapping test years.
