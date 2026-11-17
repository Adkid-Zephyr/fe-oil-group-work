# Coursework

The brief asks for a forecast an oil trader can use. This note forecasts the weekly change in the calendar spread, written as in the brief:

`CL2 − CL1`, in dollars per barrel. Positive means contango.

The only data file read is `data/raw/Oil Data.xlsx`.

```bash
python coursework/analysis.py
```

The holdout is January 2019–June 2024. The ARIMA order is chosen on earlier weeks, and the ridge penalty is fixed before the holdout is scored. Output goes to `data/results/coursework/`.

`REPORT.md` is the written note. `PRESENTATION.md` is the five-minute briefing.
