# Felix model handoff

**Current group entry point:** [oil-forecasting.ipynb](../../../oil-forecasting.ipynb), Section **5.1** (Felix OLS) and **7.1** (validation, 2005–2014). The model has been integrated on main. The standalone notebook below remains a compact reference; use the group notebook for coordinated evaluation.

[Back to repository overview](../../../README.md)

Open [felix-model.ipynb](../../../felix-model.ipynb) at the repository root in VS Code or Jupyter. Select a Python kernel with `models/Benchmark/requirements.txt` and `ipykernel` installed, then Run All. It reads Mike's current shared `data/clean/oil_monthly_clean.csv`, shows the exact original features and fits the training sample only. It does not run validation or test forecasts or overwrite shared outputs.

## Exact original specification

At forecast origin month t, predict `100*(CL1(t+1)/CL1(t)-1)` using:

- **Momentum:** `100*(CL1(t)/CL1(t-1)-1)`. Window: one month only, not a 12-month average. This is Mike's `cl1_pct`.
- **Carry:** `100*(CL1(t)-CL2(t))/CL1(t)`. Positive means backwardation. It is **minus** Mike's `carry = 100*(CL2/CL1-1)`; the denominator remains CL1. Do not substitute `100*(CL1/CL2-1)`.
- **Dollar:** `100*dxy_ret(t-1)`. DXY is supplied in decimals. At origin t we use the previous month's value, an extra conservative lag. In target-month notation this is t-2.
- OLS with an intercept, no standardisation, clipping or variable selection.

The notebook aligns rows by forecast origin and uses Mike's `target_month` and `sample` labels. Its training fit uses only `sample == 'train'` (targets through December 2004), leaving validation and test evaluation to the group's agreed workflow. This fit is a handoff example, not a replacement for either previously run experiment.

## Original code and existing experiments

- `models/Benchmark/analyze.py`: original expanding-window monthly OLS, initially trained through 2014, tested from 2015. Reads the raw workbook. Provided as original source, not the new group's cleaned-data entry point.
- `models/Benchmark/fixed-split-2014/run.py`: later fixed-coefficient weekly/monthly experiment, trained before 2014 and tested from 2014. Results are in `data/results/Felix-fixed-split-2014`.
- The fixed-split experiment requires the previous cleaned input layout. Mike removed that layout in main commit `51d116d`. Reproduce that exact historical experiment in a separate checkout of commit `a32df7627c38c583602fbb0f37658cd7d6be7532`, where inputs and hashes match. Do not restore old input copies over the current shared dataset.

The historical experiments have already examined overlapping 2015-2024 outcomes. They must not be described as an untouched test or conflated with the group's current validation/testing protocol. No new test evaluation is performed by the handoff notebook.

## Dependencies

```bash
python -m pip install -r models/Benchmark/requirements.txt ipykernel
```

The notebook also works with `nbclient` for automated execution. Keep Mike's `oil-forecasting.ipynb` as the group notebook; this is a separate integration reference.
