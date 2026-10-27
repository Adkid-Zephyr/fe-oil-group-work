# Financial Econometrics: Oil Futures Forecasting

Collaboration repository for the Financial Econometrics group coursework at Imperial College Business School (BUSI70606, 2026-2027).

Our task is to develop interpretable oil futures forecasts and explain their usefulness, diagnostics and limitations to a trading desk. All repository documentation, code comments and reports use English.

## Repository structure

```text
fe-oil-group-work/
|-- data/
|   |-- raw/                     # Original, unchanged source data
|   |-- clean/                   # Prepared data generated during analysis
|   |-- results/                 # Forecasts and metrics, grouped by model
|       |-- Benchmark/
|       |-- Mike&Div/
|       |-- Alan&Ronan/
|       |-- no-change-benchmark/ # Separate zero-change baseline forecasts
|-- models/
|   |-- Benchmark/               # Monthly OLS model, analysis code and report
|   |-- Mike&Div/
|   |-- Alan&Ronan/
|-- guidelines/                  # Coursework guidance, protocols and scripts
|   |-- Canvas/                  # Coursework brief, syllabus and AI guidance
|-- extra/
|   |-- meetings/                # Meeting notes and source records
|   |-- optional-comparisons/    # Historical-mean and AR(1) comparisons
|-- .gitignore
|-- README.md
```

- `data/raw/` holds the original `Oil Data.xlsx`; keep it unchanged.
- `data/clean/` holds reproducible prepared datasets, such as `monthly_prepared.csv`.
- `data/results/` groups forecasts and metrics by model: `Benchmark/`, `Mike&Div/`, and `Alan&Ronan/`. `no-change-benchmark/` holds the separate zero-change baseline forecasts.
- `models/` contains model code, model-specific documentation and report assets. The `Benchmark` folder is the monthly OLS model workspace.
- `guidelines/` contains shared coursework materials and the common benchmark protocol.
- `extra/` contains meeting records and optional, non-primary model comparisons.

## Start here

1. Read [shared guidance](guidelines/README.md) and the original coursework PDF in `guidelines/Canvas/`.
2. Read the [benchmark protocol](guidelines/BENCHMARKS.md) before comparing models.
3. Open `models/Benchmark/dist/index.html` locally for the interactive research report. GitHub displays HTML source; clone or download the repository to view it.

## Reproduce the Benchmark model

From the repository root, using Python 3.12 (the tested runtime):

```bash
python -m venv .venv
python -m pip install -r models/Benchmark/requirements.txt
python models/Benchmark/analyze.py
python models/Benchmark/build.py
python guidelines/benchmark.py
```

The analysis reads the original workbook from `data/raw/`, writes prepared data to `data/clean/`, and writes model outputs to `data/results/Benchmark/`. The final command regenerates the separate **no-change benchmark** forecasts in `data/results/no-change-benchmark/`. See the [benchmark guide](guidelines/BENCHMARKS.md) for how to compare models. Historical-mean and AR(1) results are optional comparisons in `extra/optional-comparisons/`.

## Collaboration

Create a branch for your changes, work in your team's folder, then open a pull request into `main`. Keep shared raw data unchanged. Include run instructions, target definition, forecast horizon, information timing and forecast CSVs with each model. Do not compare errors across different targets, units, frequencies or test dates. Agree a common evaluation protocol before selecting the final model.

The repository contains working research drafts, not a submitted group report. Review numerical claims and the course's AI guidance before submission. Course materials remain for private group use; no public redistribution licence is granted here.

The live Canvas assignment page showed **27 November 2026 at 16:00** on 27 October 2026. Confirm the displayed timezone and any later changes in Canvas. The PDF still says Autumn 2025 and Wednesday Week 7; the live assignment page is the current scheduling reference.

Group members still need to be added as GitHub collaborators using their GitHub usernames.
