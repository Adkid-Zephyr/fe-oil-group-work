# Forecasting the WTI calendar spread

Group coursework for Financial Econometrics (BUSI70606), Imperial College Business School.

We forecast next week's change in the spread between the second and front WTI futures contracts (CL2 and CL1), as a junior analyst would for an oil trading desk. The whole analysis is one notebook, which reads only `data/raw/Oil Data.xlsx`.

## Run it

```bash
pip install -r coursework/requirements.txt
cd coursework
jupyter nbconvert --to notebook --execute --inplace oil-forecasting.ipynb
```

Or open `coursework/oil-forecasting.ipynb` and choose Restart & Run All. It takes under a minute, and has been tested on Python 3.11, 3.12 and 3.13.

## What is where

| Path | What it is |
| --- | --- |
| `coursework/oil-forecasting.ipynb` | The analysis, top to bottom: data and roll, stationarity, predictors, models, diagnostics, validation and freeze, test, trading rule |
| `coursework/weekly_dataset.csv` | The weekly data set the notebook builds (one row per Friday) |
| `coursework/outputs/` | Every table the notebook writes, the validation and test forecasts, and `freeze.json` |
| `coursework/outputs/figs/` | The notebook's figures |
| `data/raw/Oil Data.xlsx` | The data provided with the brief |
| `guidelines/Canvas/` | The brief, the syllabus and the School's guidance on AI |

## The freeze

The model choice, estimation window and trading threshold were fixed on validation data and written to `coursework/outputs/freeze.json` before the test was scored. The notebook keeps that file and its time stamp, and stops if a re-run would change a frozen setting. Do not delete it.
