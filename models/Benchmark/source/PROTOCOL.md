# Oil futures research protocol

Prepared 2026-10-27 before running forecasting results. Educational group-review draft.

Question: do three interpretable signals improve next-month changes in the supplied CL1 continuous front-month series relative to simple forecasts?
Target: 100*(CL1_t/CL1_(t-1)-1), monthly, Industry_M. This is a change in a continuous futures price series, not a verified investable total return.
Predictors for target month t: previous month CL1 percentage change; previous month carry 100*(CL1-CL2)/CL1; DXY return from t-2 in percentage points. The extra DXY lag is conservative because the workbook has no release-time metadata. Month keys, rather than exact dates, align industry and macro sheets. No other variables, transformations or tuned model families.
Model: OLS with intercept. Benchmarks: zero change and expanding historical mean, with historical mean designated the primary comparison.
Training: all complete monthly observations through December 2014. Evaluation: January 2015 through June 2024. Expanding-window re-estimation each month, using targets strictly before the forecast target. No random split, no holdout-based tuning. All supplied monthly data used, including 2020. No winsorization or imputation.
Diagnostics on initial training sample: ADF on price/returns/predictors, Ljung-Box residual autocorrelation, Breusch-Pagan heteroskedasticity, CUSUM residual stability, HAC(3) coefficient uncertainty. Report limitations of small-sample and multiple tests.
Metrics: RMSE, MAE, direction accuracy (zero forecasts abstain), OOS R-squared relative to expanding mean. Show full holdout plus pre-2020, 2020, and 2021+ descriptive subsets, without selecting a winning model from subsets.
Uncertainty: block-bootstrap paired squared-error differences (OLS minus mean), block length 6 months, 2000 draws, fixed seed. Descriptive interval, not independent confirmation or a tuning criterion.
Illustrative decision rule: long if forecast > threshold; short if below negative threshold; otherwise flat. Default threshold 1 percentage point, not optimized. Costs applied per unit of absolute position change. Outputs are gross/net price-change proxy arithmetic sums, NOT executable futures P&L, wealth, annualised return or validated trading profitability. No margin/roll/contract execution available.
Verification: date continuity, source units and bounds, pairwise forecast information times, numpy independent OLS prediction, prefix-invariance after removing future records, numerical checks and browser checks.
