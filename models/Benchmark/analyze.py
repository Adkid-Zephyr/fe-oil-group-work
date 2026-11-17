"""Transparent monthly oil forecasting exercise. Run from any directory."""
from pathlib import Path
import json, hashlib, warnings
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan, breaks_cusumolsresid

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SOURCE = REPOSITORY / 'data' / 'raw' / 'Oil Data.xlsx'
RESULTS = REPOSITORY / 'data' / 'results' / 'Benchmark'
CLEAN = REPOSITORY / 'data' / 'clean'
FEATURES = ['momentum', 'carry', 'dollar']

def read_monthly(sheet):
    df = pd.read_excel(SOURCE, sheet_name=sheet)
    df = df.loc[:, ~df.columns.astype(str).str.startswith('Unnamed')]
    df.columns = df.columns.str.strip()
    df['Date'] = pd.to_datetime(df['Date'])
    assert df.Date.notna().all()
    df['month'] = df.Date.dt.to_period('M')
    assert not df.month.duplicated().any(), 'Duplicate monthly records'
    return df.set_index('month').sort_index()

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
    ind,mac=read_monthly('Industry_M'),read_monthly('Macro_M')
    assert (ind[['CL1','CL2']]>0).all().all(), 'Monthly prices must be positive'
    d=make_frame(ind,mac)
    assert len(d)==len(ind), 'Missing monthly observations'
    assert str(d.index.max())=='2024-06', 'Revisit fixed sample if source changes'
    o=walk_forward(d)
    assert len(o)==114 and not o.isna().any().any()
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
    inventory=[]
    for sh in pd.ExcelFile(SOURCE).sheet_names:
        f=pd.read_excel(SOURCE,sheet_name=sh)
        item=dict(sheet=sh,rows=len(f),columns=[str(c).strip() for c in f.columns if not str(c).startswith('Unnamed')])
        if sh!='Data Definitions':
            dates=pd.to_datetime(f.Date);item.update(start=str(dates.min().date()),end=str(dates.max().date()))
        inventory.append(item)
    payload=dict(meta=dict(source='Oil Data.xlsx, Canvas BUSI70606',sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                          created='2026-10-27',raw_start=str(ind.index.min()),raw_end=str(ind.index.max()),raw_n=len(ind),
                          complete_n=int(d[['actual']+FEATURES].notna().all(axis=1).sum()),
                          source_url='https://canvas.imperial.ac.uk/courses/9001/files/2784233',inventory=inventory),
                 metrics=summary,diagnostics=diagnostics(d),forecasts=o.to_dict('records'),
                 prices=[dict(month=str(m),cl1=float(r.CL1),cl2=float(r.CL2)) for m,r in ind.iterrows()],
                 bootstrap=dict(mean_loss_diff=float(loss.mean()),lo=float(np.quantile(boot,.025)),hi=float(np.quantile(boot,.975)),block=block,draws=B),
                 residual_band_coverage=float(((o.actual>=o.lo)&(o.actual<=o.hi)).mean()*100),
                 audit=dict(independent_prediction_max_abs_error=max(errs),prefix_invariance=True,forecast_count=len(o),source_unchanged=True))
    RESULTS.mkdir(parents=True, exist_ok=True)
    CLEAN.mkdir(parents=True, exist_ok=True)
    (RESULTS/'analysis.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    o.to_csv(RESULTS/'forecasts.csv',index=False)
    d.to_csv(CLEAN/'monthly_prepared.csv',index_label='target_month')
    print(json.dumps({k:payload[k] for k in ['meta','metrics','diagnostics','bootstrap','residual_band_coverage','audit']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
