"""Run the FROZEN spread model once on the test window (target months
Jan 2015 to Jun 2024, 114 months).

The test window is meant to be opened once. This script refuses to run if
test results already exist. To reproduce the saved numbers on a fresh clone,
pass --reproduce: it reruns and checks the forecasts match the saved file.
"""
import sys
import numpy as np
import pandas as pd
from spread_model import load_monthly, evaluate, print_metrics, RESULTS

saved = RESULTS / "forecasts_test.csv"
reproduce = "--reproduce" in sys.argv
if saved.exists() and not reproduce:
    sys.exit("Test results already exist. The test window is run once. "
             "Use --reproduce to check the saved numbers.")

df = load_monthly("2024-06")
fc, metrics, arma = evaluate(df, "2015-01", "2024-06", "test", save=not reproduce)
if reproduce:
    old = pd.read_csv(saved)
    cols = ["actual_change", "pred_ar", "pred_arma", "pred_band"]
    ok = np.allclose(old[cols].values, fc[cols].values, atol=1e-6)
    print("Reproduction check:", "PASS, forecasts match the saved file" if ok else "FAIL")
print_metrics(metrics)
