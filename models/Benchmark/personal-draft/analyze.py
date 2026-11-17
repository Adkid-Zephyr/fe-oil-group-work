"""Transparent monthly oil forecasting exercise. Run from any directory."""
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan, breaks_cusumolsresid

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / 'data' / 'cleaning_snapshot'
EXPECTED_SOURCE_SHA = '4355813a4761a6f242ae6ff1eff03dce6f89127320161b6fb2481e9aa908bae5'
FEATURES = ['momentum', 'carry', 'dollar']

def load_cleaned_inputs(shared=SNAPSHOT):
    """Read Felix personal frozen CSVs; never silently fall back to raw Excel."""
    shared = Path(shared)
    summary = json.loads((shared/'Data quality/summary.json').read_text())
    manifest = json.loads((shared/'Data quality/manifest.json').read_text())
    assert summary['dataset_version'] == '1.0.0', 'Review changed cleaning version'
    assert summary['source_sha256'] == manifest['source_sha256'] == EXPECTED_SOURCE_SHA
    frames, hashes = {}, {}
    for name in ['industry_monthly.csv', 'macro_monthly.csv', 'monthly_targets.csv']:
        relative = 'Cleaned data/' + name
        path = shared/relative
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert sha == manifest['files_sha256'][relative], f'Cleaned file changed: {relative}'
        hashes[relative] = sha
        df = pd.read_csv(path, float_precision='round_trip')
        index = pd.PeriodIndex(df['month'], freq='M')
        assert index.is_unique and index.is_monotonic_increasing, f'Invalid months: {name}'
        assert index.equals(pd.period_range(index.min(),index.max(),freq='M')), f'Month gaps: {name}'
        assert str(index.min()) == '1994-12' and str(index.max()) == '2024-06'
        frames[name] = df.set_index(index).drop(columns='month')
    industry, macro, targets = (frames[k] for k in ['industry_monthly.csv','macro_monthly.csv','monthly_targets.csv'])
    assert industry.index.equals(macro.index) and industry.index.equals(targets.index)
    assert np.allclose(macro.dxy_return_pct,100*macro.dxy_return_decimal,rtol=1e-12,atol=1e-12)
    assert np.isfinite(industry[['cl1','cl2']].to_numpy()).all()
    assert np.isfinite(macro.dxy_return_decimal.to_numpy()).all()
    ind = industry[['date','cl1','cl2']].rename(columns={'date':'Date','cl1':'CL1','cl2':'CL2'})
    mac = macro[['dxy_return_decimal']].rename(columns={'dxy_return_decimal':'DXY returns'})
    ind['Date'] = pd.to_datetime(ind['Date'])
    assert ind.Date.dt.to_period('M').tolist() == list(ind.index)
    assert pd.to_datetime(macro.date).dt.to_period('M').tolist() == list(macro.index)
    return ind, mac, targets, dict(dataset_version=summary['dataset_version'],
        source_sha256=summary['source_sha256'], input_hashes=hashes,
        manifest_sha256=hashlib.sha256((shared/'Data quality/manifest.json').read_bytes()).hexdigest())

def make_frame(ind, mac):
    # Reindex before shifting so a missing month can never become a one-month change.
    grid = pd.period_range(ind.index.min(), ind.index.max(), freq='M')
    d = ind.reindex(grid)
    d['usd'] = mac['DXY returns'].reindex(grid) * 100
    d['actual'] = d.CL1.pct_change(fill_method=None) * 100
    d['momentum'] = d.actual.shift(1)
    d['carry'] = (100 * (d.CL1 - d.CL2) / d.CL1).shift(1)
    d['dollar'] = d.usd.shift(2)
    return d

def walk_forward(frame):
    rows=[]
    for month in frame.index[frame.index >= pd.Period('2015-01')]:
        train=frame.loc[frame.index < month].dropna(subset=['actual']+FEATURES)
        row=frame.loc[month]
        if row[['actual']+FEATURES].isna().any():
            continue
        x=sm.add_constant(train[FEATURES], has_constant='add')
        fit=sm.OLS(train.actual,x).fit()
        xv=np.r_[1.,row[FEATURES].to_numpy(dtype=float)]
        pred=float(xv @ fit.params.to_numpy())
        low,high=np.quantile(fit.resid,[.1,.9])
        vals=dict(month=str(month),origin=str(month-1),dollar_month=str(month-2),
                  train_end=str(train.index[-1]),n_train=len(train),actual=float(row.actual),
                  ols=pred,mean=float(train.actual.mean()),zero=0.,
                  lo=float(pred+low),hi=float(pred+high),price=float(row.CL1))
        for k,v in zip(['intercept']+FEATURES,fit.params): vals['b_'+k]=float(v)
        for k in FEATURES: vals[k]=float(row[k]);vals['c_'+k]=float(row[k]*fit.params[k])
        rows.append(vals)
    return pd.DataFrame(rows)

def metrics(o):
    ans={}
    for name in ['ols','mean','zero']:
        err=o.actual-o[name]
        ans[name]={'rmse':float(np.sqrt(np.mean(err**2))), 'mae':float(np.mean(abs(err))),
                   'direction':None if name=='zero' else float(np.mean(np.sign(o[name])==np.sign(o.actual))*100),
                   'n':len(o)}
    ans['oos_r2']=float(1-np.sum((o.actual-o.ols)**2)/np.sum((o.actual-o['mean'])**2))
    return ans

def diagnostics(frame):
    tr=frame.loc[frame.index <= pd.Period('2014-12')].dropna(subset=['actual']+FEATURES)
    fit=sm.OLS(tr.actual,sm.add_constant(tr[FEATURES])).fit()
    hac=fit.get_robustcov_results(cov_type='HAC',maxlags=3)
    out=[]
    for name,col in [('CL1 level','CL1'),('Monthly change','actual'),('Momentum','momentum'),('Carry','carry'),('Dollar','dollar')]:
        v=adfuller(tr[col],regression='c',autolag='AIC')
        out.append(dict(test='ADF',series=name,stat=float(v[0]),p=float(v[1]),lags=int(v[2]),null='Unit root'))
    lb=acorr_ljungbox(fit.resid,lags=[12],return_df=True)
    bp=het_breuschpagan(fit.resid,fit.model.exog)
    cu=breaks_cusumolsresid(fit.resid,ddof=4)
    out.extend([dict(test='Ljung–Box (12)',series='Residuals',stat=float(lb.lb_stat.iloc[0]),p=float(lb.lb_pvalue.iloc[0]),null='No residual autocorrelation through lag 12'),
                dict(test='Breusch–Pagan (Koenker)',series='Residuals',stat=float(bp[0]),p=float(bp[1]),null='Constant residual variance'),
                dict(test='CUSUM',series='Residuals',stat=float(cu[0]),p=float(cu[1]),null='Stable coefficients')])
    coefs=[dict(name=k,estimate=float(b),se=float(s),p=float(p),lo=float(ci[0]),hi=float(ci[1]))
           for k,b,s,p,ci in zip(['intercept']+FEATURES,hac.params,hac.bse,hac.pvalues,hac.conf_int())]
    return dict(tests=out,coefficients=coefs,n=len(tr),start=str(tr.index[0]),end=str(tr.index[-1]),r2=float(fit.rsquared))

def main():
    ind,mac,targets,provenance=load_cleaned_inputs()
    assert (ind[['CL1','CL2']]>0).all().all(), 'Monthly prices must be positive'
    d=make_frame(ind,mac)
    np.testing.assert_allclose(d.actual,targets.actual_return_pct,rtol=1e-12,atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(d.CL1,targets.actual_price,rtol=1e-12,atol=1e-12)
    assert (targets.origin.to_numpy() == (targets.index-1).astype(str).to_numpy()).all()
    # Shared y is authoritative; the independent price derivation above checks it.
    d['actual'] = targets.actual_return_pct
    d['momentum'] = d.actual.shift(1)
    assert len(d)==len(ind), 'Missing monthly observations'
    assert str(d.index.max())=='2024-06', 'Revisit fixed sample if source changes'
    o=walk_forward(d)
    assert len(o)==114 and not o.isna().any().any()
    shared_eval=targets.loc[targets.is_shared_evaluation]
    assert list(shared_eval.index.astype(str)) == o.month.tolist()
    assert shared_eval.target_valid.all()
    np.testing.assert_allclose(o.zero,shared_eval.benchmark_return_pct,atol=0,rtol=0)
    reference=pd.DataFrame(json.loads((ROOT/'validation/pre_cleaning_reference.json').read_text())['forecasts'])
    assert reference.month.tolist()==o.month.tolist()
    change={k:float(np.max(np.abs(o[k]-reference[k]))) for k in ['actual','ols','mean','zero']}
    assert all(pd.Period(r.train_end) < pd.Period(r.month) for r in o.itertuples())
    # Independent regression prediction and source-point checks.
    errs=[]
    for month in ['2015-01','2020-04','2024-06']:
        m=pd.Period(month);tr=d[d.index<m].dropna(subset=['actual']+FEATURES)
        xx=np.column_stack([np.ones(len(tr)),tr[FEATURES].values])
        beta=np.linalg.lstsq(xx,tr.actual.values,rcond=None)[0]
        expected=float(np.r_[1,d.loc[m,FEATURES].values] @ beta)
        observed=float(o.loc[o.month==month,'ols'].iloc[0])
        errs.append(abs(expected-observed))
    assert max(errs)<1e-10
    prefix=make_frame(ind.loc[:'2018-12'],mac.loc[:'2018-12'])
    p=walk_forward(prefix)
    assert np.allclose(p.ols,o.ols.iloc[:len(p)],rtol=0,atol=1e-10)
    # Paired circular moving-block bootstrap of losses, not a model refit.
    loss=((o.actual-o.ols)**2-(o.actual-o['mean'])**2).to_numpy()
    rng=np.random.default_rng(20261027);B=2000;block=6;n=len(loss)
    boot=[]
    for _ in range(B):
        starts=rng.integers(0,n,int(np.ceil(n/block)))
        ids=np.concatenate([(s+np.arange(block))%n for s in starts])[:n]
        boot.append(float(loss[ids].mean()))
    periods={'all':o,'pre2020':o[o.month<'2020-01'],'2020':o[o.month.str.startswith('2020')],'post2020':o[o.month>='2021-01']}
    summary={k:metrics(v) for k,v in periods.items()}
    payload=dict(meta=dict(source='Felix personal cleaning snapshot v1.0.0 (not the group-agreed dataset)',sha256=provenance['source_sha256'],cleaned_data=provenance,
                          created='2026-10-27',raw_start=str(ind.index.min()),raw_end=str(ind.index.max()),raw_n=len(ind),
                          complete_n=int(d[['actual']+FEATURES].notna().all(axis=1).sum()),
                          source_url='https://github.com/Adkid-Zephyr/fe-oil-group-work/tree/main/models/Benchmark/personal-draft/data/cleaning_snapshot/Cleaned%20data',
                          cleaning_report_url='https://github.com/Adkid-Zephyr/fe-oil-group-work/blob/main/models/Benchmark/personal-draft/data/cleaning_snapshot/CLEANING_REPORT.md',input_revision='personal-cleaning-snapshot-v1.0.0'),
                 metrics=summary,diagnostics=diagnostics(d),forecasts=o.to_dict('records'),
                 prices=[dict(month=str(m),cl1=float(r.CL1),cl2=float(r.CL2)) for m,r in ind.iterrows()],
                 bootstrap=dict(mean_loss_diff=float(loss.mean()),lo=float(np.quantile(boot,.025)),hi=float(np.quantile(boot,.975)),block=block,draws=B),
                 residual_band_coverage=float(((o.actual>=o.lo)&(o.actual<=o.hi)).mean()*100),
                 audit=dict(independent_prediction_max_abs_error=max(errs),prefix_invariance=True,forecast_count=len(o),
                            cleaned_input_hashes_verified=True,shared_targets_verified=True,pre_cleaning_max_abs_change=change,
                            unchanged_within_1e_12=all(v<1e-12 for v in change.values())))
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/analysis.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False))
    o.to_csv(ROOT/'results/forecasts.csv',index=False)
    d.to_csv(ROOT/'results/monthly_prepared.csv',index_label='target_month')
    print(json.dumps({k:payload[k] for k in ['meta','metrics','diagnostics','bootstrap','residual_band_coverage','audit']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
