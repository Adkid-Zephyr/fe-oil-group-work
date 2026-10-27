"""Felix's shared no-change benchmark. Run from any directory."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

def make_forecasts(data):
    data = data.rename(columns=lambda c: str(c).strip()).copy()
    data['month'] = pd.to_datetime(data['Date']).dt.to_period('M')
    data = data.sort_values('month').set_index('month')
    assert not data.index.duplicated().any(), 'Duplicate months'
    assert data.index.equals(pd.period_range(data.index.min(), data.index.max(), freq='M')), 'Missing months'
    price = pd.to_numeric(data['CL1'], errors='raise')
    assert price.notna().all() and (price > 0).all(), 'Invalid monthly prices'
    previous = price.shift(1)
    out = pd.DataFrame({'origin': (data.index-1).astype(str),
                        'actual_price': price,
                        'benchmark_price': previous,
                        'actual_return_pct': 100*(price/previous-1),
                        'benchmark_return_pct': 0.0}, index=data.index)
    return out.loc['2015-01':'2024-06'].rename_axis('month').reset_index()

def main():
    data = pd.read_excel(ROOT/'Canvas'/'Oil Data.xlsx', sheet_name='Industry_M')
    out = make_forecasts(data)
    assert len(out) == 114 and not out.isna().any().any()
    error = out.actual_return_pct-out.benchmark_return_pct
    metrics = {'model':'No change', 'owner':'Felix', 'n':len(out),
               'rmse_pp':float(np.sqrt(np.mean(error**2))),
               'mae_pp':float(np.mean(abs(error)))}
    folder = ROOT/'Benchmark results'; folder.mkdir(exist_ok=True)
    out.to_csv(folder/'forecasts.csv',index=False)
    pd.DataFrame([metrics]).to_csv(folder/'metrics.csv',index=False)
    (folder/'README.md').write_text(
        '# No-change benchmark results\n\nCompleted by Felix. January 2015 to June 2024, 114 monthly forecasts.\n\n'
        f"RMSE: {metrics['rmse_pp']:.4f} pp. MAE: {metrics['mae_pp']:.4f} pp.\n\n"
        'Use `benchmark_return_pct` for monthly percentage-change models or `benchmark_price` for price-level models. Join on `month` and use identical test dates and units. The metrics above are for percentage changes only.\n')
    print(json.dumps(metrics,indent=2))

if __name__ == '__main__':
    main()
