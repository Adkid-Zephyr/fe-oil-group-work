"""Evaluate the spread models on the validation window (target months
Jan 2005 to Dec 2014). Safe to rerun: test-period rows are dropped on load."""
from spread_model import load_monthly, evaluate, print_metrics, ARMA_IC

df = load_monthly("2014-12")
fc, metrics, arma = evaluate(df, "2005-01", "2014-12", "validation")
print("ARMA order search on the training sample (best five by BIC):")
print(arma.sort_values(ARMA_IC).head().round(3).to_string(index=False), "\n")
print_metrics(metrics)
