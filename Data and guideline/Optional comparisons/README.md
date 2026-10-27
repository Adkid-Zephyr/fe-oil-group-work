# Benchmark results

One-step monthly CL1 percentage changes, January 2015 to June 2024. Errors are in percentage points. All models use the same complete-case training rows as Felix OLS.

| Model | RMSE | MAE | OOS R2 vs mean | Direction accuracy |
| --- | ---: | ---: | ---: | ---: |
| Zero change / price random walk | 13.4383 | 8.7394 | -0.0046 | N/A (zero forecast) |
| Expanding historical mean | 13.4076 | 8.6724 | 0.0000 | 56.14% |
| AR(1) with intercept | 13.3703 | 8.5145 | 0.0056 | 53.51% |
| Felix OLS (three predictors) | 12.9171 | 8.4978 | 0.0718 | 57.89% |

AR(1) was added after the original OLS results were available. These are retrospective comparisons, not a fresh untouched test. The model choice and interpretation still require group review.
