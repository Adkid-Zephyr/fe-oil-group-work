"""Clean the three monthly sheets of Oil Data.xlsx into one table of levels.

Run from anywhere:  python guidelines/clean_monthly.py

This script ONLY cleans. It does not transform, lag or test anything: returns,
spreads, stationarity tests and models are left to the modelling teams.
The raw workbook is opened read-only and its hash is checked before and after.
"""
import hashlib
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG: edit here
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = REPO_ROOT / "data" / "raw" / "Oil Data.xlsx"
OUTPUT_DIR = REPO_ROOT / "data" / "clean" / "monthly_levels"
OUTPUT_CSV = OUTPUT_DIR / "oil_monthly_clean.csv"
OUTPUT_LOG = OUTPUT_DIR / "data_cleaning_log.md"

RAW_DATE_COLUMN = "Date"

# Sheets to load, with raw column name -> clean name. Clean names match
# guidelines/Data quality/data_dictionary.csv so they line up with the shared
# tables. Raw names are compared after stripping spaces ("Brent ", "BP ").
SHEETS = {
    "Industry_M": {
        "CL1": "cl1",
        "CL2": "cl2",
        "Brent": "brent",
        "CRKS321C Index": "crack_spread_321",
        "Baltic Dry Index": "baltic_dry_index",
        "Daily Production": "crude_production_source_units",
        "Inventories": "inventories_source_units",
        "Rig Count": "rig_count",
        "Commercial Long": "commercial_long",
        "Commercial Short": "commercial_short",
        # Every cell in this column is the formula Long + Short, so it is not
        # an independent open-interest measure. See the log.
        "Total Open Interest": "commercial_long_plus_short_source",
    },
    "Macro_M": {
        "CPI YOY %": "cpi_yoy_pct",
        "3M Yield": "treasury_3m_yield_pct",
        "10Y Yield": "treasury_10y_yield_pct",
        "IndustrialProduction Index": "industrial_production_index",
        "SPX": "sp500_index",
        "DXY returns": "dxy_return_decimal",
        "VIX": "vix",
    },
    "StockPrices_M": {
        "Gasoline All Grades": "gasoline_all_grades",
        "Dow Jones US Oil&Gas Index": "dow_jones_us_oil_gas_index",
        "ExxonMobil": "exxon_mobil",
        "ConocoPhilips": "conoco_phillips",
        "Chevron": "chevron",
        "BP": "bp",
        "Shell": "shell",
        "TotalEnergies": "total_energies",
    },
}

DROP_COLUMNS = ["shell"]

# Checked for negative or zero values.
PRICE_COLUMNS = [
    "cl1", "cl2", "brent", "gasoline_all_grades", "dow_jones_us_oil_gas_index",
    "sp500_index", "exxon_mobil", "conoco_phillips", "chevron", "bp",
    "total_energies",
]

# The large-move check uses % change, except for these rates, spreads and
# returns: they can sit at or near zero, so it uses the plain change instead.
PLAIN_CHANGE_COLUMNS = [
    "crack_spread_321", "cpi_yoy_pct", "treasury_3m_yield_pct",
    "treasury_10y_yield_pct", "dxy_return_decimal",
]
LARGE_MOVE_SD = 5


# ---------------------------------------------------------------------------
# Loading and per-sheet cleaning
# ---------------------------------------------------------------------------
def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe_raw_sheet(name, raw):
    """Print a sheet exactly as loaded, before any cleaning."""
    dates = pd.to_datetime(raw[RAW_DATE_COLUMN], errors="coerce")
    print(f"\n--- {name} (raw) ---")
    print(f"Shape: {raw.shape}")
    print(f"Date range: {dates.min().date()} to {dates.max().date()}")
    print(f"Row order: {'newest first' if dates.is_monotonic_decreasing else 'not newest first'}")
    print(f"Columns: {[str(c) for c in raw.columns]}")
    print("Missing values per column:")
    print(raw.isna().sum().to_string())


def check_dates(dates, label):
    """Assert dates are unique, ascending and gap-free. Gaps are reported, never filled."""
    assert dates.is_unique, f"{label}: duplicate dates {dates[dates.duplicated()].tolist()}"
    assert dates.is_monotonic_increasing, f"{label}: dates are not ascending"
    expected = pd.date_range(dates.min(), dates.max(), freq="ME")
    gaps = expected.difference(dates)
    if len(gaps) > 0:
        print(f"{label}: MISSING MONTHS: {[str(d.date()) for d in gaps]}")
    assert len(gaps) == 0, f"{label}: {len(gaps)} missing months (reported above, not filled)"


def clean_sheet(name, raw, renames):
    """Standardise one sheet's dates and column names. Returns (table, rows re-dated)."""
    table = raw.dropna(how="all").dropna(axis=1, how="all").copy()
    table.columns = [str(c).strip() for c in table.columns]

    expected_columns = {RAW_DATE_COLUMN, *renames}
    assert set(table.columns) == expected_columns, (
        f"{name}: columns differ from the config: "
        f"{sorted(set(table.columns) ^ expected_columns)}"
    )

    dates = pd.to_datetime(table[RAW_DATE_COLUMN], errors="coerce").dt.normalize()
    assert dates.notna().all(), f"{name}: {dates.isna().sum()} blank or unparseable dates"
    month_ends = dates + pd.offsets.MonthEnd(0)
    rows_redated = int((month_ends != dates).sum())

    table = table.rename(columns=renames).drop(columns=RAW_DATE_COLUMN)
    table.insert(0, "date", month_ends)
    table = table.sort_values("date").reset_index(drop=True)
    check_dates(table["date"], name)
    return table, rows_redated


def make_numeric(table):
    """Convert value columns to numbers. Returns any entries that were not numeric."""
    problems = []
    for column in table.columns.drop("date"):
        numeric = pd.to_numeric(table[column], errors="coerce")
        bad = table[column].notna() & numeric.isna()
        for i in table.index[bad]:
            problems.append({
                "date": table.at[i, "date"].date(),
                "column": column,
                "entry": repr(table.at[i, column]),
            })
        table[column] = numeric
    return problems


def merge_sheets(tables):
    """Outer merge, so a month missing from one sheet shows up instead of vanishing."""
    merged = None
    for table in tables:
        merged = table if merged is None else merged.merge(
            table, on="date", how="outer", validate="one_to_one"
        )
    return merged.sort_values("date").reset_index(drop=True)


def trim_to_common_sample(table):
    """Keep the span where every column is present. Nothing is imputed."""
    complete = table.drop(columns="date").notna().all(axis=1)
    assert complete.any(), "No month has every column present"
    trimmed = table.loc[complete.idxmax():complete[::-1].idxmax()].reset_index(drop=True)

    holes = trimmed.drop(columns="date").isna().sum()
    holes = holes[holes > 0]
    if len(holes) > 0:
        print(f"MISSING VALUES INSIDE THE COMMON SAMPLE:\n{holes.to_string()}")
    assert len(holes) == 0, "Missing values inside the common sample (reported above, not filled)"
    return trimmed


# ---------------------------------------------------------------------------
# Review checks: these report values and never change them
# ---------------------------------------------------------------------------
def find_nonpositive(table, columns):
    """Rows where a listed column is zero or negative."""
    rows = []
    for column in columns:
        for i in table.index[table[column] <= 0]:
            rows.append({"date": table.at[i, "date"].date(), "column": column,
                         "value": table.at[i, column]})
    return pd.DataFrame(rows, columns=["date", "column", "value"])


def find_duplicate_rows(table):
    """Different dates carrying identical values in every column."""
    values = table.drop(columns="date")
    return table.loc[values.duplicated(keep=False), "date"].dt.date.tolist()


def find_large_moves(table):
    """Month-on-month moves more than LARGE_MOVE_SD full-sample SDs from that column's mean.

    The moves are computed for this check only and are not saved.
    """
    rows = []
    for column in table.columns.drop("date"):
        series = table[column]
        if column in PLAIN_CHANGE_COLUMNS:
            move, unit = series.diff(), "change"
        else:
            move, unit = series.pct_change(fill_method=None) * 100, "% change"
        sd_from_mean = (move - move.mean()) / move.std()
        for i in sd_from_mean.index[sd_from_mean.abs() > LARGE_MOVE_SD]:
            rows.append({
                "date": table.at[i, "date"].date(),
                "column": column,
                "previous": series.at[i - 1],
                "value": series.at[i],
                "move": round(move.at[i], 4),
                "unit": unit,
                "sds_from_mean": round(sd_from_mean.at[i], 1),
            })
    columns = ["date", "column", "previous", "value", "move", "unit", "sds_from_mean"]
    return pd.DataFrame(rows, columns=columns).sort_values(["date", "column"], ignore_index=True)


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------
def markdown_table(table):
    if table.empty:
        return "None."
    header = "| " + " | ".join(str(c) for c in table.columns) + " |"
    divider = "|" + "---|" * table.shape[1]
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join([header, divider, *rows])


def write_log(info):
    final = info["final"]
    renames = pd.DataFrame(
        [(sheet, raw, clean) for sheet, mapping in SHEETS.items() for raw, clean in mapping.items()],
        columns=["sheet", "raw_name", "clean_name"],
    )
    redated = "; ".join(f"{sheet}: {n} of {len(final)}" for sheet, n in info["rows_redated"].items())
    non_price = info["non_price_nonpositive"]
    non_price_text = (
        ", ".join(f"{column} ({count})" for column, count in non_price.items()) if len(non_price) else "none"
    )

    log = f"""# Data cleaning log: monthly oil dataset

Generated by `guidelines/clean_monthly.py`. Rerun the script instead of editing this file.

## Source and scope

- Source: `data/raw/Oil Data.xlsx`, opened read-only. SHA-256 `{info['sha256']}`, unchanged by the run.
- Frequency: monthly.
- Sheets used: {', '.join(SHEETS)}.
- Sheets not used: Industry_D and Industry_W. The repository audit (`guidelines/CLEANING_REPORT.md`) reports that daily Brent has 534 undated rows and matches monthly Brent on none of the 341 shared dates. Daily CL1 includes -37.63 on 2020-04-20, a real settlement rather than a data error, which rules out log returns across that date.
- Cleaning only. No returns, spreads, lags, scaling, tests, outlier treatment or imputation.

## Sort order and date alignment

- The raw sheets run newest to oldest. All are sorted oldest to newest.
- Every date is set to its calendar month-end. Macro_M already uses calendar month-ends. Industry_M and StockPrices_M use the last business day, so some rows change date ({redated}). Their values are unchanged, so a value dated 2024-06-30 may have been observed on 2024-06-28.
- Sheets are merged one-to-one on the month-end date.
- Dates are asserted to be unique, ascending and free of gaps, in each sheet and after merging. Missing months found: none.

## Column names and types

- All names are snake_case and match `guidelines/Data quality/data_dictionary.csv`.
- `Total Open Interest` is renamed `commercial_long_plus_short_source` because it equals Commercial Long + Commercial Short in {info['oi_sum_matches']} of {info['oi_rows']} rows. The workbook builds it with that formula, so it is not an independent open-interest measure.
- `dxy_return_decimal` is supplied by the workbook as a return. No DXY level is available, so it is the one column that is not in levels.
- Non-numeric entries found: {len(info['non_numeric'])}.

{markdown_table(renames)}

## Dropped columns

- `shell`: {info['shell_missing']} missing months, with the first value on {info['shell_first_date']}. Keeping it would shorten the sample by more than ten years.
- Nothing else is dropped. Both `cl1` and `cl2` are kept.

## Final sample

- Window: {final['date'].min().date()} to {final['date'].max().date()}, {len(final)} monthly observations, {final.shape[1] - 1} value columns.
- Months removed by trimming: {info['months_trimmed']}. Values imputed: 0.

## Flagged values (reported, not changed or removed)

### Negative or zero prices

Checked: {', '.join(PRICE_COLUMNS)}.

{markdown_table(info['nonpositive'])}

Not treated as errors, because these can legitimately be zero or negative, but note that logs are undefined at those values. Months at or below zero: {non_price_text}.

### Duplicate rows

Different dates with identical values in every column: {len(info['duplicates'])}.

### Month-on-month moves larger than {LARGE_MOVE_SD} standard deviations

Each move is compared with that column's full-sample mean and standard deviation. Moves are % changes, except plain changes for {', '.join(PLAIN_CHANGE_COLUMNS)}. A flag means a value is worth checking, not that it is wrong.

{markdown_table(info['large_moves'])}

## Known issues (values left as supplied)

These come from one-off checks and are not recomputed by this script. Neither has been confirmed by the data provider.

- **Treasury yields appear to be dated one month early, across the whole sample.** A yield labelled month t matches the published US Treasury month-end rate for t+1. Monthly changes correlate 0.995 (10Y) and 0.987 (3M) with Treasury's changes at t+1, against 0.082 and 0.313 in the same month (Treasury daily par yield curve, 1994-2024). The flagged 3M moves labelled 2007-12 and 2020-02 therefore happened in January 2008 and March 2020. A yield labelled t-1 is really the rate at the end of month t, so forecasts of month t need a lag of at least two months on these two columns.
- **Monthly positioning and rig counts differ from the weekly sheet.** For June 2024, monthly `commercial_long` is 1,600,085 against 604,586 in the last weekly report, and `rig_count` is 581 against 479. Monthly longs and shorts also stay within about 10% of each other throughout, unlike the weekly series. The monthly definitions are undocumented, so the "commercial" label is unverified.
"""
    OUTPUT_LOG.write_text(log, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    hash_before = file_sha256(RAW_FILE)
    raw_sheets = pd.read_excel(RAW_FILE, sheet_name=list(SHEETS))

    print("=== BEFORE CLEANING ===")
    for name, raw in raw_sheets.items():
        describe_raw_sheet(name, raw)

    print("\n=== CLEANING ===")
    tables, rows_redated, non_numeric = [], {}, []
    for name, raw in raw_sheets.items():
        table, rows_redated[name] = clean_sheet(name, raw, SHEETS[name])
        non_numeric += [{"sheet": name, **problem} for problem in make_numeric(table)]
        tables.append(table)
    print(f"Rows moved to calendar month-end: {rows_redated}")
    print(f"Non-numeric entries found: {len(non_numeric)}")
    for problem in non_numeric:
        print(f"  {problem}")

    merged = merge_sheets(tables)
    check_dates(merged["date"], "Merged table")
    print(f"Merged shape: {merged.shape}")

    shell = merged.set_index("date")["shell"]
    shell_missing = int(shell.isna().sum())
    shell_first_date = shell.first_valid_index().date()
    print(f"Dropping {DROP_COLUMNS}: shell has {shell_missing} missing months, first value {shell_first_date}")
    without_dropped = merged.drop(columns=DROP_COLUMNS)

    final = trim_to_common_sample(without_dropped)
    check_dates(final["date"], "Final table")
    months_trimmed = len(without_dropped) - len(final)
    print(f"Common sample: {final['date'].min().date()} to {final['date'].max().date()}, "
          f"{len(final)} observations ({months_trimmed} months trimmed, nothing imputed)")

    print("\n=== REVIEW: NOTHING BELOW HAS BEEN CHANGED ===")
    nonpositive = find_nonpositive(final, PRICE_COLUMNS)
    print(f"\nNegative or zero prices: {len(nonpositive)}")
    if not nonpositive.empty:
        print(nonpositive.to_string(index=False))

    other_columns = final.columns.drop(["date", *PRICE_COLUMNS])
    non_price_nonpositive = (final[other_columns] <= 0).sum()
    non_price_nonpositive = non_price_nonpositive[non_price_nonpositive > 0]
    print("\nMonths at or below zero in non-price columns (for information):")
    print(non_price_nonpositive.to_string() if len(non_price_nonpositive) else "None")

    duplicates = find_duplicate_rows(final)
    print(f"\nDuplicate rows across different dates: {len(duplicates)} {duplicates or ''}")

    large_moves = find_large_moves(final)
    print(f"\nMonth-on-month moves larger than {LARGE_MOVE_SD} SD: {len(large_moves)}")
    if not large_moves.empty:
        print(large_moves.to_string(index=False))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    final.to_csv(OUTPUT_CSV, index=False, date_format="%Y-%m-%d", lineterminator="\n")

    long_plus_short = final["commercial_long"] + final["commercial_short"]
    write_log({
        "sha256": hash_before,
        "final": final,
        "rows_redated": rows_redated,
        "non_numeric": non_numeric,
        "shell_missing": shell_missing,
        "shell_first_date": shell_first_date,
        "months_trimmed": months_trimmed,
        "oi_sum_matches": int((long_plus_short == final["commercial_long_plus_short_source"]).sum()),
        "oi_rows": len(final),
        "nonpositive": nonpositive,
        "non_price_nonpositive": non_price_nonpositive,
        "duplicates": duplicates,
        "large_moves": large_moves,
    })

    assert file_sha256(RAW_FILE) == hash_before, "The raw workbook changed during the run"

    print("\n=== FINAL ===")
    print(f"Shape: {final.shape}")
    print(f"Date range: {final['date'].min().date()} to {final['date'].max().date()}")
    print(f"Columns: {list(final.columns)}")
    print(f"Saved: {OUTPUT_CSV.relative_to(REPO_ROOT)}")
    print(f"Saved: {OUTPUT_LOG.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
