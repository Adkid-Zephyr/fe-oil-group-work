"""Reproduce same-sample benchmarks without changing the Benchmark model."""
from pathlib import Path
import importlib.util
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
MODEL = REPOSITORY / 'models' / 'Benchmark'
spec = importlib.util.spec_from_file_location('benchmark_model', MODEL / 'analyze.py')
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

def forecasts(frame):
    result = model.walk_forward(frame)
    predictions = []
    for month in result.month:
        target = pd.Period(month, freq='M')
        train = frame.loc[frame.index < target].dropna(subset=['actual'] + model.FEATURES)
        x = train.momentum.to_numpy(dtype=float)
        y = train.actual.to_numpy(dtype=float)
        # Closed-form univariate OLS, including an intercept.
        slope = np.sum((x-x.mean())*(y-y.mean())) / np.sum((x-x.mean())**2)
        intercept = y.mean() - slope*x.mean()
        pred = intercept + slope*float(frame.loc[target, 'momentum'])
        independent = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y, rcond=None)[0]
        np.testing.assert_allclose(pred, np.array([1., frame.loc[target, 'momentum']]) @ independent, atol=1e-10)
        predictions.append(float(pred))
    result['ar1'] = predictions
    return result

def main():
    frame = model.make_frame(model.read_monthly('Industry_M'), model.read_monthly('Macro_M'))
    result = forecasts(frame)
    assert len(result) == 114 and not result.month.duplicated().any()
    assert result.month.iloc[0] == '2015-01' and result.month.iloc[-1] == '2024-06'
    assert all(pd.Period(a) < pd.Period(b) for a,b in zip(result.train_end,result.month))
    # Future removal must not change any earlier forecast.
    earlier = forecasts(frame.loc[:'2019-12'])
    np.testing.assert_allclose(earlier[['ols','mean','zero','ar1']], result.iloc[:len(earlier)][['ols','mean','zero','ar1']], atol=1e-10)
    original = pd.read_csv(REPOSITORY / 'data' / 'results' / 'Benchmark' / 'forecasts.csv')
    assert original.month.tolist() == result.month.tolist()
    np.testing.assert_allclose(original[['actual','ols','mean','zero']], result[['actual','ols','mean','zero']], atol=1e-10)
    denominator = np.sum((result.actual-result['mean'])**2)
    records = []
    for key,label in [('zero','Zero change / price random walk'),('mean','Expanding historical mean'),('ar1','AR(1) with intercept'),('ols',"Benchmark OLS (three predictors)")]:
        err = result.actual-result[key]
        records.append(dict(model=label, n=len(result), rmse_pp=float(np.sqrt(np.mean(err**2))), mae_pp=float(np.mean(abs(err))), oos_r2_vs_mean=float(1-np.sum(err**2)/denominator), direction_accuracy_pct=None if key=='zero' else float(np.mean(np.sign(result[key])==np.sign(result.actual))*100)))
    output = ROOT; output.mkdir(exist_ok=True)
    result.to_csv(output/'forecasts.csv',index=False)
    pd.DataFrame(records).to_csv(output/'metrics.csv',index=False)
    (output/'validation.json').write_text(json.dumps(dict(status='passed',forecast_months=114,checks=['unique aligned months','strictly earlier training outcomes','AR(1) closed-form against independent least squares','future-truncation invariance through 2019-12','original model forecasts reproduced']),indent=2)+'\n')
    lines=['# Optional comparison results','', 'One-step monthly CL1 percentage changes, January 2015 to June 2024. Errors are in percentage points. All models use the same complete-case training rows as Benchmark OLS.','', '| Model | RMSE | MAE | OOS R2 vs mean | Direction accuracy |','| --- | ---: | ---: | ---: | ---: |']
    for r in records:
        direction='N/A (zero forecast)' if r['direction_accuracy_pct'] is None else f"{r['direction_accuracy_pct']:.2f}%"
        lines.append(f"| {r['model']} | {r['rmse_pp']:.4f} | {r['mae_pp']:.4f} | {r['oos_r2_vs_mean']:.4f} | {direction} |")
    lines.extend(['','AR(1) was added after the original OLS results were available. These are retrospective comparisons, not a fresh untouched test. The model choice and interpretation still require group review.'])
    (output/'README.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(records,indent=2))

if __name__ == '__main__': main()
