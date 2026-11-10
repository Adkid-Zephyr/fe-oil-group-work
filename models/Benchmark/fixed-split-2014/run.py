"""Fixed pre-2014 OLS; one-period-ahead CL1 change forecasts."""
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'data/results/Felix-fixed-split-2014'
MONTHLY = ROOT / 'data/clean/monthly_levels/oil_monthly_clean.csv'
DAILY = ROOT / 'data/clean/industry_daily.csv'
FEATURES = ['momentum', 'carry', 'dollar']

def monthly_frame(source):
    s = source.copy()
    s.index = pd.to_datetime(s.date).dt.to_period('M')
    assert s.index.is_unique and s.index.is_monotonic_increasing
    assert s.index.equals(pd.period_range(s.index.min(), s.index.max(), freq='M'))
    p = s.index.to_timestamp('M')
    f = pd.DataFrame(index=p)
    f['price'] = s.cl1.to_numpy()
    f['actual'] = f.price.pct_change(fill_method=None)*100
    f['momentum'] = f.actual.shift(1)
    f['carry'] = (100*(s.cl1-s.cl2)/s.cl1).shift(1).to_numpy()
    f['dollar'] = (100*s.dxy_return_decimal).shift(2).to_numpy()
    f['origin'] = p-pd.offsets.MonthEnd(1)
    f['dollar_source_date'] = p-pd.offsets.MonthEnd(2)
    return f

def weekly_frame(daily, monthly):
    s = daily.copy(); s['date'] = pd.to_datetime(s.date)
    assert s.date.is_unique
    s = s.sort_values('date').set_index('date')
    # Select an actual common row, never separately forward-fill CL1 and CL2.
    s['week_end'] = s.index.to_period('W-FRI').end_time.normalize()
    s['observed_date'] = s.index
    w = s.groupby('week_end').tail(1).set_index('week_end')
    w = w.loc[w.index <= s.index.max()]
    grid = pd.date_range(w.index.min(), w.index.max(), freq='W-FRI')
    w = w.reindex(grid)
    f = pd.DataFrame(index=grid)
    f['price'] = w.cl1
    f['actual'] = w.cl1.pct_change(fill_method=None)*100
    f['momentum'] = f.actual.shift(1)
    f['carry'] = (100*(w.cl1-w.cl2)/w.cl1).shift(1)
    f['origin'] = grid-pd.Timedelta(days=7)
    f['observed_date'] = w.observed_date
    f['input_price_date'] = w.observed_date.shift(1)
    # Monthly dollar values become usable only after the following month-end.
    m = monthly.copy(); m['dollar_source_date'] = pd.to_datetime(m.date)
    m['available_date'] = m.dollar_source_date+pd.offsets.MonthEnd(1)
    m['dollar'] = 100*m.dxy_return_decimal
    a = pd.merge_asof(f.reset_index(names='target_date'),m[['available_date','dollar_source_date','dollar']].sort_values('available_date'),left_on='origin',right_on='available_date',direction='backward')
    return a.set_index('target_date')

def evaluate(frame):
    valid = frame.replace([np.inf,-np.inf],np.nan).dropna(subset=['actual']+FEATURES)
    train = valid.loc[valid.index < '2014-01-01']
    test = valid.loc[(valid.index >= '2014-01-01') & (valid.index < '2025-01-01')].copy()
    assert len(train)>10 and len(test)>0
    x = np.column_stack([np.ones(len(train)),train[FEATURES]])
    beta = np.linalg.lstsq(x,train.actual,rcond=None)[0]
    test['ols'] = np.column_stack([np.ones(len(test)),test[FEATURES]])@beta
    test['no_change'] = 0.0
    test['training_end'] = str(train.index[-1].date())
    assert (test.origin < test.index).all()
    assert (test.dollar_source_date <= test.origin).all()
    scores = []
    denom = np.sum(test.actual**2)
    for model in ['ols','no_change']:
        err = test.actual-test[model]
        scores.append({'model':model,'n':len(test),'rmse_pp':float(np.sqrt(np.mean(err**2))),'mae_pp':float(np.mean(abs(err))),'oos_r2_vs_zero':float(1-np.sum(err**2)/denom),'direction_accuracy_pct':None if model=='no_change' else float(100*np.mean(np.sign(test[model])==np.sign(test.actual)))})
    info = {'train_start':str(train.index[0].date()),'train_end':str(train.index[-1].date()),'train_n':len(train),'test_start':str(test.index[0].date()),'test_end':str(test.index[-1].date()),'test_n':len(test),'coefficients':dict(zip(['intercept']+FEATURES,map(float,beta))),'excluded_test_rows':int(((frame.index>='2014-01-01')&(frame.index<'2025-01-01')).sum()-len(test))}
    return test, scores, info

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--weekly',action='store_true');args=ap.parse_args()
    monthly=pd.read_csv(MONTHLY)
    sources=[MONTHLY]; frames={'monthly':monthly_frame(monthly)}
    if args.weekly:
        sources.append(DAILY);frames['weekly']=weekly_frame(pd.read_csv(DAILY),monthly)
    OUT.mkdir(parents=True,exist_ok=True)
    all_scores=[];meta={}
    for frequency,frame in frames.items():
        forecasts,scores,info=evaluate(frame)
        forecasts.to_csv(OUT/f'{frequency}_forecasts.csv',index_label='target_date')
        frame.to_csv(OUT/f'{frequency}_prepared.csv',index_label='target_date')
        all_scores.extend([{'frequency':frequency,**s} for s in scores]);meta[frequency]=info
    pd.DataFrame(all_scores).to_csv(OUT/'metrics.csv',index=False)
    meta['sources']=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources]
    meta['method']='Fixed OLS fit using targets before 2014; no test-period refitting or tuning. One-step forecasts use lagged observed inputs.'
    (OUT/'analysis.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps({'metrics':all_scores,'samples':meta},indent=2))
if __name__=='__main__': main()
