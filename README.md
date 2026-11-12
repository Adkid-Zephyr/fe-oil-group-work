# Financial Econometrics: Oil Futures Forecasting

Imperial College Business School · BUSI70606 · Group coursework, 2026–2027.

## Start here

1. Open **[oil-forecasting.ipynb](oil-forecasting.ipynb)** for the current shared analysis. Felix's OLS is in **5.1** and its 2005–2014 validation in **7.1**.
2. Use **[data/clean/oil_monthly_clean.csv](data/clean/oil_monthly_clean.csv)**, produced by Section 2 of the group notebook. [Column definitions and release lags](data/clean/oil_monthly_dictionary.csv).
3. Read the [coursework brief](guidelines/Canvas/26%20Fintech%20CW%20Financial%20Econometrics.pdf) and [benchmark definition](guidelines/BENCHMARKS.md).

The current group split is by **target month**: training through December 2004, validation January 2005–December 2014, test January 2015–June 2024. Do not mix these results with the earlier fixed-2014 experiment below.

## Felix's work: what to use and where

| Item | Location | Purpose / status |
| --- | --- | --- |
| Integrated OLS and validation | [Group notebook](oil-forecasting.ipynb), Sections **5.1 / 7.1** | Current collaboration entry point; includes the three-signal model and validation analysis. |
| Standalone model handoff | [felix-model.ipynb](felix-model.ipynb) | Executed reference using Mike's current cleaned CSV. Run All fits training only; no validation/test evaluation. |
| Exact signal definitions and setup | [Felix handoff guide](models/Benchmark/handoff/README.md) | Momentum window, carry sign, dollar lag, dependencies and integration notes. |
| No-change benchmark | [Definition](guidelines/BENCHMARKS.md) · [code](guidelines/benchmark.py) · [forecasts and metrics](data/results/no-change-benchmark/) | Completed shared zero-return reference. Saved forecasts cover 2015–June 2024; match dates when comparing. |
| Weekly / monthly fixed-2014 experiment | [Code and method](models/Benchmark/fixed-split-2014/README.md) · [results](data/results/Felix-fixed-split-2014/) | Historical experiment: trained before 2014, tested from 2014. Requires the recorded historical input version. |
| Original monthly research | [Original model guide](models/Benchmark/README.md) · [results](data/results/Benchmark/) | Earlier expanding-window experiment; retained for provenance. |
| Interactive results website | [Oil, explained](https://fe-oil-explained.laufs0310.chatgpt.site/) | Published 10 November fixed-2014 weekly/monthly results. It does not yet reflect the group's newer validation analysis. |
| Earlier data audit and meeting notes | [Cleaning report](guidelines/CLEANING_REPORT.md) · [quality evidence](guidelines/Data%20quality/) · [meeting notes](extra/meetings/MEETING_NOTES.md) | Reference material; the current cleaned-data workflow is Section 2 of the group notebook. |

**Signal definitions at origin t:** momentum is the one-month CL1 percentage change; carry is `100*(CL1(t)-CL2(t))/CL1(t)` (minus the shared CSV's carry); dollar is `100*dxy_ret(t-1)`. The target is next month's CL1 percentage change. Full details are in the handoff guide.

**Outstanding Felix work:** Section 3 (stationarity) is still a placeholder in the current notebook. The assigned ADF/KPSS/ACF table, independent release-lag spot checks and final fresh-clone reproducibility review are not marked complete by the model handoff. Existing notebook checks and older audits are not substitutes for those deliverables.

## Run Felix's standalone handoff

From the repository root:

```bash
python -m pip install -r models/Benchmark/requirements.txt ipykernel
```

Open `felix-model.ipynb` in VS Code/Jupyter, select that Python environment and use **Run All**. It reads the shared cleaned file and does not overwrite group data. These dependencies cover Felix's handoff, not a verified environment for the entire evolving group notebook.

## Repository map

```text
 oil-forecasting.ipynb             Current group notebook
 felix-model.ipynb                 Felix's standalone handoff
 data/raw/                        Original workbook
 data/clean/                      Current shared cleaned CSV and dictionary
 data/results/                    Saved results, separated by experiment/model
 models/Benchmark/handoff/        Felix's definitions and integration guide
 models/Benchmark/fixed-split-2014/ Historical weekly/monthly experiment
 models/Benchmark/                Original Felix OLS source and report
 models/Alan&Ronan/                Team model workspace
 models/Mike&Div/                  Team model workspace
 guidelines/                      Coursework, benchmark and earlier audit tools
 extra/                           Meeting notes and optional comparisons
```

The folder name `models/Benchmark` is historical: it contains Felix's **OLS model**. The actual shared **no-change benchmark** is `guidelines/benchmark.py` with outputs in `data/results/no-change-benchmark/`.

## Collaboration

Pull the latest main before starting. Use a branch for changes and review the diff before merging. Coordinate edits to the shared notebook; avoid unrelated cell/output churn. Keep raw data unchanged and use the current shared cleaned CSV for group work. The older `guidelines/clean_data.py` and `clean_monthly.py` workflows are historical audit tools, not the current data-generation entry point.

Keep target definitions, date windows, units and information timing consistent. Label earlier experiments explicitly. Felix's historical experiments already examined overlapping 2015–2024 outcomes, so do not describe those years as untouched by all prior group research.

The repository contains research drafts, not a submitted assessment. Review the [AI guidance](guidelines/Canvas/Student%20Guidance%20on%20Use%20of%20AI%202026.27.pdf) before submission. Course materials retain their original rights; public repository visibility does not grant redistribution rights.

Canvas showed **27 November 2026 at 16:00** when checked on 27 October. Recheck Canvas for current deadlines and presentation details; the brief retains an older year/week reference.
