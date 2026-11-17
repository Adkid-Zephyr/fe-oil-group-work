# Group 11 weekly spread diagnostics review

17 November 2026. Source snapshot [main at c2524f0](https://github.com/Adkid-Zephyr/fe-oil-group-work/commit/c2524f0e51f06adf2a4b34c52240faba07dbd9df).

Felix's assigned review covers stationarity and residual diagnostics and their consistency with the report. The original assignment referred to Alan's weekly model. Final selection was still unconfirmed when this review was prepared. The checked-in report follows Alan's specification. Mike's newer notebook has its own target, models, sample split and output tables. Both reviews below use the team's existing code and results.

## Alan: the current checked-in report

[Report](https://github.com/Adkid-Zephyr/fe-oil-group-work/blob/c2524f0/coursework/REPORT.md) · [Analysis code](https://github.com/Adkid-Zephyr/fe-oil-group-work/blob/c2524f0/coursework/analysis.py) · [Results](https://github.com/Adkid-Zephyr/fe-oil-group-work/tree/c2524f0/data/results/coursework)

The target is the weekly change in the dollar CL2–CL1 spread. The three-variable OLS diagnostics use 1,250 target weeks from 20 January 1995 through 28 December 2018. The holdout starts 4 January 2019.

| Report claim | Matching evidence | Review |
| --- | --- | --- |
| CL1 and CL2 level tests | Trend ADF p = 0.2595 and 0.3338. Both KPSS statistics exceed the 5% critical value of 0.146. | Matches. ADF fails to reject a unit root and KPSS rejects trend stationarity. |
| Weekly spread change is stationary | ADF p = 2.38e-24. KPSS statistic 0.00870 vs 5% critical value 0.463. | Say the tests support stationarity of the change. |
| Spread level is persistent | ADF −5.384 vs 5% critical value −2.864. KPSS 1.040 vs 0.463. | Both nulls are rejected. Describe the evidence as mixed and distinguish the level from the change. |
| Residual autocorrelation and HAC | Durbin–Watson 2.410. Ljung–Box p = 3.64e-13, 1.32e-25 and 1.10e-31 at lags 1, 4 and 12. Breusch–Godfrey (4) p = 6.93e-31. Code uses seven Newey–West lags. | Numbers and rejection match. HAC adjusts inference. |
| Heteroskedasticity | Breusch–Pagan p = 3.90e-25. | Rejection matches. The result establishes evidence of nonconstant residual variance. It does not establish the scope of a point forecast. Revise the report's causal “so” accordingly. |
| Parameter stability | Classical midpoint Chow at 12 January 2007: p = 0.002329. Residual CUSUM: p = 0.000224. | Numbers match. These are tests of overall model stability. Use the recursive coefficient figure for statements about the spread slope specifically, and label Chow as classical given the rejected constant-variance assumption. |

## Mike: the updated weekly notebook

[Notebook](https://github.com/Adkid-Zephyr/fe-oil-group-work/blob/c2524f0/coursework/oil-forecasting.ipynb) · [Output tables and freeze settings](https://github.com/Adkid-Zephyr/fe-oil-group-work/tree/c2524f0/coursework/outputs)

The target is the roll-adjusted change in percentage carry. The training cutoff is 30 October 2009, validation ends 24 February 2017 and test starts 3 March 2017. The saved freeze distinguishes B1 (no-change forecast winner under the selection rule) from M1 (signal model used for the diagnostics below). Reports should name the relevant model and sample with each test.

- **Stationarity, Section 2.** ADF and KPSS support stationarity of the roll-adjusted target (ADF −24.920, KPSS 0.303), stock surprise at four weeks (−6.534, 0.062), and four-week production change (−7.855, 0.033). Raw and clean carry levels produce conflicting ADF/KPSS verdicts. Both log price levels show evidence consistent with unit roots. Cite `t2_unit_roots.csv` when updating the report.
- **Residual autocorrelation, Sections 6 and 7.5.** M1 training (765 weeks) gives BG(4) p = 0.1753 and Ljung–Box(12) p = 0.2486. The train-plus-validation fit (1,147 weeks) gives p = 0.05294 and 0.09723, respectively. Neither result rejects at 5%, although BG(4) after refitting is close to that threshold. Alan's rejection and Durbin–Watson figure belong to his specification.
- **Heteroskedasticity and stability.** Breusch–Pagan rejects in both windows (p = 9.16e-6 and 1.27e-6). The classical training-only Chow test at the September 2008 break rejects (p = 0.00239), while its HAC Wald counterpart does not (p = 0.840). The notebook's stated interpretation gives priority to the robust tests. The existing report's January 2007 Chow and CUSUM results belong to Alan's fit.

## Verification performed

In a temporary copy of the pinned source, ran Alan's original `build()`, `stationarity()` and `diagnostics()`. Both diagnostic tables matched the committed CSVs. Executed Mike's existing notebook code cells for the data build and diagnostic dependencies (zero-based positions 2, 5, 7, 17, 19, 27, 31, 33, 38, 40, 46 and 69). For cell 69, selected the train-plus-validation rows and signal regressors from the committed freeze settings, verifying the regenerated M1 and B2 terms against that file. The three tables `t2_unit_roots.csv`, `t6_diagnostics_M1_train.csv` and `t7_diagnostics_train_validation.csv` matched the committed CSVs. Comparisons required matching labels, rows and columns, with numeric tolerances of rtol 1e-7 and atol 1e-9. This was a targeted diagnostics rerun. The holdout and model selection procedures were outside the rerun scope.

For the current report, apply the Alan wording edits above. If the group selects Mike's specification, replace the diagnostic paragraph and sample description together using the matching figures above.
