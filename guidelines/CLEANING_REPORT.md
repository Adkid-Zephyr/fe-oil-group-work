# Shared oil dataset: cleaning and quality report

Version 1.0.0. Prepared 27 October 2026. Scope: every populated cell in the supplied six-sheet workbook, including its definition sheet and formula cells. This is a reproducible structural cleaning and source-quality audit, not independent certification of every market observation.

## What the group should use

Start with the [shared cleaned-data guide](../data/clean/README.md).

- For common monthly experiments, use `data/clean/monthly_observations.csv`. It aligns the three monthly sheets by **calendar month**, retaining each sheet's original reference date and Excel row.
- For targets and fair model comparisons, use `data/clean/monthly_targets.csv`. The shared evaluation remains **January 2015–June 2024**, with **114** valid monthly targets and the existing **no-change** benchmark.
- For other frequencies, use the corresponding native-frequency CSV. Do not assume the monthly evaluation protocol applies to daily/weekly forecasts.
- Read the field dictionary and unresolved findings below **before selecting predictors**. An organised CSV is not automatically a point-in-time-safe modelling matrix.

**We have not filled missing observations, guessed dates, clipped extremes or removed the pandemic.** All original numerical values survive either in native-frequency CSVs or the quarantine file. The original workbook is unchanged. One additional weekly column masks an interpolation already present in the source; the original column remains available for auditing.

## Source and provenance

Original: `data/raw/Oil Data.xlsx`, already archived in this repository from the course's [Canvas dataset page](https://canvas.imperial.ac.uk/courses/9001/files/2784233).

SHA-256: `4355813a4761a6f242ae6ff1eff03dce6f89127320161b6fb2481e9aa908bae5`.

This audit uses that exact repository copy; it is not a fresh verification of the live Canvas download. The script refuses an unfamiliar source hash. All native rows carry `source_excel_row`, a one-based row number including the Excel header, so a group member can find the exact original observation.

| Source sheet | Rows in native cleaned table | Coverage | Structural treatment |
|---|---:|---|---|
| Industry_D | 8,692 | 1990-01-02 to 2024-07-30 | 534 additional rows without dates quarantined, not discarded |
| Industry_W | 1,803 | 1990-01-05 to 2024-07-19 | All rows retained; one existing interpolation marked |
| Industry_M | 355 | 1994-12-30 to 2024-06-28 | Four entirely blank unnamed columns removed |
| Macro_M | 355 | 1994-12-31 to 2024-06-30 | 234 entirely blank trailing rows removed |
| StockPrices_M | 355 | 1994-12-30 to 2024-06-28 | All rows retained, including missing Shell history |
| Data Definitions | 32 nonempty rows, including labels/headings | Not a time series | Exported verbatim to `guidelines/Data quality/source_definitions.csv` |

The definition sheet's overall date description does **not** cover the longer daily and weekly tables. We use observed dates rather than imposing the monthly date range on every sheet.

## Deterministic cleaning applied

1. Read source values and formulas separately. Reject Excel error cells, unsupported numeric contents, nonfinite values, unexpected headers/unnamed values and unrecognised formulas rather than silently coercing them.
2. Remove only entirely blank rows/columns. The exact removed row numbers are recorded in `summary.json`.
3. Separate any nonempty row without a date into `quarantined_rows.csv`; retain its original row number and all values as JSON. Do not invent a date or shift a column.
4. Sort valid dates ascending and standardise date strings to `YYYY-MM-DD`. Reject duplicate dates and duplicate months, rather than choosing one arbitrarily. This workbook has none.
5. Normalise column names to stable English snake_case. Preserve source names and Excel column letters in `data_dictionary.csv`. Original numeric values and missingness are retained.
6. For monthly sheets, derive a `month` key (`YYYY-MM`) and verify an uninterrupted sequence of 355 months. Join by this key, not exact dates; business-month-end and calendar-month-end dates differ.
7. Preserve DXY in `dxy_return_decimal` and add `dxy_return_pct = 100 * dxy_return_decimal`. Decimal interpretation is the working convention used in the existing model, consistent with the values' scale; the workbook's number format is **General**, not an explicit percentage format. Confirm vendor metadata if available. CPI and yields are already supplied in percentage-point scale and are not multiplied again.
8. Derive shared monthly targets using consecutive calendar months. No return is formed across a missing month or a nonpositive/missing endpoint. First-month targets remain missing. No log return is applied to the daily negative price.
9. Generate descriptive review files for missingness, calendar gaps, large first differences, negative values, long repeated-value runs and cross-frequency differences. These are **review flags, not instructions to delete observations**.

## Material findings and decisions

### 1. Undated daily records and uncertain cross-series alignment

The bottom **534 rows** of `Industry_D` contain Brent values but no date, CL1 or CL2. They cannot be attached to a calendar safely. They are retained in quarantine and excluded only from dated time-series tables.

For the 355 monthly industry dates, 341 have a corresponding dated daily row; the other 14 lack that exact daily date. On those 341 shared dates:

| Variable | Exact matches, tolerance 1e-8 | Different values |
|---|---:|---:|
| CL1 | 341 | 0 |
| CL2 | 341 | 0 |
| Brent | 0 | 341 |
| Crack spread | 1 | 340 |
| Baltic Dry Index | 4 | 337 |

These discrepancies could reflect calendar alignment, aggregation, instrument or reference-time conventions. The comparison alone cannot establish which source series is correct. The trailing undated values make daily alignment especially concerning, but **we have not asserted or applied a guessed row shift**.

**Decision:** retain both source series and flag daily Brent/crack/BDI for alignment review, and their monthly counterparts for cross-frequency definition review. Do not use these as interchangeable series or resample one to overwrite the other. Check with the teaching team/data provider before relying on the alignment of daily non-CL predictors. See `cross_frequency_comparison.csv` for every date and value, including the 14 absent-date cases.

### 2. Monthly “Total Open Interest” is a formula sum

All **355** cells in `Industry_M!L2:L356` contain `=J[row]+K[row]`: commercial longs plus commercial shorts. Their cached numerical values agree exactly with that arithmetic. This is not an independently supplied total-open-interest series, and the source label should not be accepted without qualification.

**Decision:** rename the output to `commercial_long_plus_short_source`, retain every value and record the formula. Do not substitute it for the weekly `total_open_interest_source`, treat them as the same variable, or silently divide the sum by two. The weekly series' instrument/reporting definition also remains unverified.

### 3. A weekly value already uses a future observation

`Industry_W!E1195`, dated **2001-09-07**, contains `=(E1194+E1196)/2`, cached as **332195**. Because the source sheet is descending, its endpoints include **2001-09-14** and **2001-08-31**. The later observation creates a point-in-time problem if this interpolated value is treated as observed information on September 7.

**Decision:** retain `commercial_long` exactly as supplied; add `commercial_long_is_source_interpolated` and `commercial_long_unimputed`. The latter is identical except that this one source-interpolated cell is missing. Use the unimputed column for a forecast design that must avoid that interpolation. Any further filling or sample restriction needs a documented, training-only policy. This does not resolve the publication timing of the other weekly observations.

### 4. Leading missing histories are genuine gaps in this workbook

| Series | Missing observations | First supplied observation |
|---|---:|---|
| Daily crack spread | 369 | 1991-06-18 |
| Daily Baltic Dry Index | 29 | 1990-02-12 |
| Weekly rig count | 1 | 1990-01-12 |
| Weekly crude stock change | 4 | 1990-02-02 |
| Weekly commercial long, short and total OI | 85 each | 1991-08-23 |
| Monthly Shell price | 127 | 2005-07-29 |

These missing cells are leading gaps; the raw dated numeric columns have no internal or trailing missing cells. The derived weekly unimputed column adds the one explicitly masked internal observation. No missing value becomes zero. The monthly observation panel retains **all 355 months** instead of applying a complete-case filter across every possible predictor. Using Shell would shorten the usable sample; choose that intentionally and compare models on matching dates.

### 5. Negative values are not automatically data errors

Daily CL1 is **−37.63 on 2020-04-20**. The [CFTC's contemporaneous-event report summary](https://www.cftc.gov/PressRoom/PressReleases/8315-20) confirms that the May 2020 WTI contract settled at −$37.63 that day. This supports retaining that observation; it does not certify the construction of the entire CL1 continuous series.

Negative crack spreads, stock changes, inflation readings or short-term yields also require contextual interpretation, not automatic deletion. All negative source observations are listed and retained. Daily log returns are undefined around nonpositive prices; do not repair this by taking absolute values or replacing the negative price with a small positive number. Contract-level dollar changes or another explicitly justified target may be more suitable for daily analysis of this period.

### 6. Calendar and statistical review

All weekly dates are Fridays separated by seven days. Monthly tables contain no missing or duplicate months. Daily observations fall on weekdays; **329 weekdays** between endpoints have no row. These are not labelled as errors: many may be holidays, and an authoritative exchange calendar was not supplied. We do not insert or forward-fill them.

`review_flags.csv` contains **1,621 field-level review entries**, potentially multiple per observation. A large-first-difference flag uses absolute modified z-score greater than 8, based on the median and MAD of each full-sample native-frequency first-difference series. `constant_runs.csv` lists **39** runs at thresholds of at least five daily, four weekly or three monthly observations. Repeated quotes or sustained macro readings can be legitimate.

**These full-sample descriptive flags must not be used as ex-ante predictor inputs or automatic outlier filters.** If a team chooses winsorisation, scaling, imputation or feature selection, estimate the rule within each training window and report it. No value was removed because of these flags.

## Information timing and unresolved metadata

The workbook contains observation/reference dates, not verified release timestamps. Monthly data for a reference month are not necessarily all available on its last day. CPI, industrial production, inventories and position reports may also be revised. No historical vintages are supplied.

- The aligned panel is an **observation table**, not a release-aware forecasting feature matrix.
- Do not join a target-month macro observation directly to that month's return as a predictor.
- A one- or two-month lag is a modelling assumption, not a verified substitute for release calendars.
- Record each predictor's assumed information lag. Use backward as-of joins only against verified availability times if those become available; never backfill from the future.
- Continuous CL1/CL2 rolling and adjustment, stock split/dividend adjustment, some currencies and production/inventory unit scales remain undocumented. Columns ending `_source_units` deliberately avoid silently declaring a thousand/million multiplier.

No public web series has been substituted into the classroom dataset. External checking here is limited to the negative WTI observation above. Instructor/vendor clarification is required to resolve the remaining issues.

## Common target and benchmark

`monthly_targets.csv` has 355 rows. The first row has no previous month in this workbook and is invalid for the percentage-change target; **354** rows have valid targets. The common evaluation subset contains **114** valid targets, January 2015–June 2024.

- `actual_price`: supplied CL1 for target month t.
- `benchmark_price`: supplied CL1 for month t−1 (the no-change price forecast).
- `actual_return_pct`: 100 × (CL1_t / CL1_(t−1) − 1), in percentage points.
- `benchmark_return_pct`: zero when the target is valid; otherwise missing.
- `origin`: previous calendar month, not a verified execution timestamp.
- `is_shared_evaluation`: membership in the repository's existing common evaluation window.

All 114 target and benchmark rows match the existing `data/results/no-change-benchmark/forecasts.csv` within 1e-12 tolerances. Existing model folders and published research reports are not rewritten by this cleaning task. Fair comparisons still require the same horizon, target, units and test dates, including a matched benchmark if any model loses observations.

## Reproduce and verify

From the repository root, use Python 3.12:

```bash
python -m pip install -r guidelines/cleaning-requirements.txt
python guidelines/clean_data.py
python -m unittest discover -s guidelines -p "test_clean_data.py"
```

The pipeline can write to a scratch location with `--output-root /path/to/scratch`. It creates the two output subdirectories there; it does not alter the raw source. Pinned package versions record the tested environment.

Tests check source immutability; conservation of every dated numeric value and missing cell; preservation of all 534 quarantine records; all 356 formula caches; the negative price; the isolated interpolation mask; benchmark equality; monthly alignment and prefix invariance; rejection of malformed dates, duplicate dates and invalid numbers; non-bridging of missing/nonpositive target endpoints; and all manifest hashes.

Machine-readable evidence is in `guidelines/Data quality/summary.json` and `manifest.json`; the dictionary maps every numeric field to the original worksheet/column. These checks establish reproducibility and explicit handling, not that unknown metadata has been recovered.

## Group review before model comparison

1. Start from the same version and source hash.
2. Confirm any suspect predictor you intend to use, especially daily non-CL alignment and the monthly mislabeled OI field.
3. State your target, frequency and information-lag assumptions.
4. Keep missingness and extreme-value decisions inside training windows; do not remove difficult test months for a better score.
5. Join predictions to the shared targets, use the same eligible dates and retain the matched no-change benchmark.
6. Record any teacher clarification or data revision as a new version rather than overwriting the original workbook.

The audit and code are AI-assisted working materials for group verification. They do not constitute a submitted assessment or instructor approval.
