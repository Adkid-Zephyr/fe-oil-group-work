# Felix's diagnostics review

This branch tracks the team's weekly coursework at [c2524f0](https://github.com/Adkid-Zephyr/fe-oil-group-work/commit/c2524f0e51f06adf2a4b34c52240faba07dbd9df). The review uses Mike's [notebook](../coursework/oil-forecasting.ipynb) and [committed outputs](../coursework/outputs/). If the group adopts this notebook, the diagnostics section of [the current report](../coursework/REPORT.md) needs the replacements below. It still describes Alan's dollar-spread regression with a January 2019 holdout. Mike's main target is the roll-adjusted weekly change in percentage carry, with a March 2017 holdout.

| Check | Evidence from Mike's notebook | Report wording |
| --- | --- | --- |
| Stationarity, Section 2 | ADF and KPSS support stationarity of the target, four-week stock surprise and four-week production change. Both tests reject their respective nulls for raw and adjusted carry levels. | The weekly roll-adjusted change has evidence of stationarity. Evidence on the carry level is mixed. |
| Residual autocorrelation, Sections 6 and 7.5 | For M1, BG(4) gives p = 0.1753 in training and 0.05294 after refitting on training plus validation. Ljung–Box(12) gives p = 0.2486 and 0.09723, respectively. | Neither test rejects at 5%. BG(4) in the refit is close to that cutoff. |
| Heteroskedasticity and stability, Sections 6 and 7.5 | Breusch–Pagan rejects in both samples (p = 9.16e-6 and 1.27e-6). Training-only September 2008 classical Chow rejects (p = 0.00239), while the HAC Wald counterpart gives p = 0.840. | Report evidence of nonconstant residual variance and use HAC inference. State which stability test and sample the conclusion refers to. |

M1 is the signal model in [the freeze record](../coursework/outputs/freeze.json). B1, the no-change forecast, is the selected forecasting benchmark winner under the notebook's validation rule. The diagnostics above describe M1.

Re-executed the team's data build and diagnostic cells in an isolated copy. The regenerated [unit-root table](../coursework/outputs/t2_unit_roots.csv), [training diagnostics](../coursework/outputs/t6_diagnostics_M1_train.csv) and [train-plus-validation diagnostics](../coursework/outputs/t7_diagnostics_train_validation.csv) match the committed results within numerical tolerance (rtol 1e-7, atol 1e-9). The review covers these diagnostics and report consistency. Forecast and trading evaluation were outside its scope.
