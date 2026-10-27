# Financial Econometrics: Oil Futures Forecasting

Collaboration repository for the Financial Econometrics group coursework at Imperial College Business School (BUSI70606, 2026-2027).

Our task is to develop interpretable oil futures forecasts and explain their usefulness, diagnostics and limitations to a trading desk. All repository documentation, code comments and reports use English.

## Repository structure

| Folder | Purpose |
| --- | --- |
| `Data and guideline` | Original Canvas data and assignment documents, shared evaluation protocol, repository guidance and meeting records. |
| `Felix's model` | Felix's monthly predictive OLS model, reproducible analysis, results and interactive research report. |
| `Alan&Ronan’s model` | Alan and Ronan's model contributions. |
| `Mike&Div‘s model` | Mike and Div's model contributions. |

## Start here

1. Read [the shared guidance](Data%20and%20guideline/README.md) and the original coursework PDF in `Data and guideline/Canvas`.
2. Read [the benchmark protocol](Data%20and%20guideline/BENCHMARKS.md) before comparing models.
3. Review [the meeting record](Data%20and%20guideline/Meetings/MEETING_NOTES.md).
4. Open `Felix's model/dist/index.html` locally for the interactive research report. GitHub displays HTML source; download or clone the repository to view the report.

## Shared cleaned data

The group can use [the shared CSV dataset](Data%20and%20guideline/Cleaned%20data/README.md). Read [the English cleaning report](Data%20and%20guideline/CLEANING_REPORT.md) for source issues, field restrictions and the common monthly targets. Original data and teammates' model folders remain unchanged.

```bash
python -m pip install -r "Data and guideline/cleaning-requirements.txt"
python "Data and guideline/clean_data.py"
python "Data and guideline/test_clean_data.py"
```

## Reproduce Felix's results

From the repository root, using Python 3.12 (the tested runtime):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r "Felix's model/requirements.txt"
python "Felix's model/analyze.py"
python "Felix's model/build.py"
python "Data and guideline/benchmark.py"
```

Felix has completed the shared **no-change benchmark**. The last command regenerates ready-to-use forecasts under `Data and guideline/Benchmark results`. See the short benchmark guide linked above. Earlier multi-model comparisons remain optional; the original research report retains its historical-mean comparison.

## Collaboration

Create a branch for your changes, work in your team's folder, then open a pull request into `main`. Keep shared raw data unchanged. Include run instructions, target definition, forecast horizon, information timing and forecast CSVs with each model. Do not compare errors across different targets, units, frequencies or test dates. Agree a common evaluation protocol before selecting the final model.

The repository contains working research drafts, not a submitted group report. Review numerical claims and the course's AI guidance before submission. Course materials remain for private group use; no public redistribution licence is granted here.

The live Canvas assignment page showed **27 November 2026 at 16:00** on 27 October 2026. Confirm the displayed timezone and any later changes in Canvas. The PDF still says Autumn 2025 and Wednesday Week 7; the live assignment page is the current scheduling reference.

Group members still need to be added as GitHub collaborators using their GitHub usernames.
