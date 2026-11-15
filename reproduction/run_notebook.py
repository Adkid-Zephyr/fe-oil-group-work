"""Execute the shared notebook in an isolated tracked-file copy and compare outputs."""
from pathlib import Path
import argparse, hashlib, io, json, os, platform, subprocess, sys, tempfile, time, traceback
from importlib import metadata
import nbformat
from nbclient import NotebookClient
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def sha(b): return hashlib.sha256(b).hexdigest()

def compare_csv(expected, actual):
    a=pd.read_csv(io.BytesIO(expected));b=pd.read_csv(io.BytesIO(actual))
    if a.shape!=b.shape or list(a.columns)!=list(b.columns):
        return {'status':'FAIL','reason':'shape or columns differ','expected_shape':a.shape,'actual_shape':b.shape}
    differences=[];max_error=0.
    for col in a:
        if pd.api.types.is_numeric_dtype(a[col]) and pd.api.types.is_numeric_dtype(b[col]):
            x=a[col].to_numpy(dtype=float);y=b[col].to_numpy(dtype=float)
            ok=np.isclose(x,y,atol=1e-6,rtol=1e-7,equal_nan=True)
            finite=np.isfinite(x)&np.isfinite(y)
            if finite.any():max_error=max(max_error,float(np.max(abs(x[finite]-y[finite]))))
        else:
            ok=(a[col].fillna('<MISSING>').astype(str)==b[col].fillna('<MISSING>').astype(str)).to_numpy()
        if not ok.all():differences.append({'column':col,'rows':np.flatnonzero(~ok).tolist()[:10], 'expected':[str(v) for v in a.loc[~ok,col].head(10)], 'actual':[str(v) for v in b.loc[~ok,col].head(10)]})
    return {'status':'PASS' if not differences else 'FAIL','rows':len(a),'max_abs_numeric_difference':max_error,'differences':differences}

def assess_difference(path, expected, actual, result):
    """Retain strict differences and explicitly classify only reviewed minor cases."""
    if result['status'] != 'FAIL': return result
    a=pd.read_csv(io.BytesIO(expected)); b=pd.read_csv(io.BytesIO(actual))
    if a.shape!=b.shape or list(a.columns)!=list(b.columns):return result
    cols={x['column'] for x in result.get('differences',[])}
    if cols=={'model'}:
        normalise=lambda x:x.replace('Plain mean reversion (AR)','Plain mean reversion')
        if a.model.map(normalise).equals(b.model.map(normalise)):
            result.update(status='WARN',classification='label_only',strict_match=False)
    elif path.endswith('forecasts_validation.csv') and cols=={'pred_arma'} and result['max_abs_numeric_difference']<1e-5:
        result.update(status='WARN',classification='small_arma_forecast_drift',strict_match=False)
    elif path.endswith('arma_order_validation.csv') and cols <= {'aic','bic','ljung_box_p_12'} and result['max_abs_numeric_difference']<1e-3:
        ia=a.bic.idxmin();ib=b.bic.idxmin()
        affected={r for x in result['differences'] for r in x['rows']}
        if a.loc[ia,['p','q']].equals(b.loc[ib,['p','q']]) and ia not in affected and ib not in affected:
            result.update(status='WARN',classification='nonselected_arma_fit_drift',strict_match=False)
    return result


def independent_checks(work):
    """Recompute target arithmetic, core band forecasts and headline metrics."""
    monthly=pd.read_csv(work/'data/clean/oil_monthly_clean.csv')
    S=(monthly.cl1-monthly.cl2).to_numpy(); y=np.r_[np.diff(S),np.nan]
    origins=monthly.date.str[:7].tolist(); summary={}
    for label,first,last,count in [('validation','2005-01','2014-12',120),('test','2015-01','2024-06',114)]:
        folder=work/'_runtime_audit' if label=='test' else work/'data/results/Alan&Ronan'
        fc=pd.read_csv(folder/f'forecasts_{label}.csv');met=pd.read_csv(folder/f'metrics_{label}.csv')
        assert len(fc)==count and fc.month.tolist()==pd.period_range(first,last,freq='M').astype(str).tolist()
        assert fc.month.is_unique and (fc.origin<fc.month).all()
        errors=[]
        for row in fc.itertuples():
            i=origins.index(row.origin);past=S[:i];lo=past.mean()-past.std();hi=past.mean()+past.std()
            flags=(past<lo)|(past>hi)
            X=np.column_stack([np.ones(i),past*(~flags),past*flags,flags.astype(float)])
            outside=S[i]<lo or S[i]>hi
            xi=np.array([1., S[i]*(not outside), S[i]*outside, float(outside)])
            # Independent normal-equation solution (small full-rank OLS design).
            pred=xi@np.linalg.solve(X.T@X,X.T@y[:i])
            errors.append(abs(pred-row.pred_band))
            np.testing.assert_allclose(row.actual_change,y[i],atol=1e-12)
            np.testing.assert_allclose([row.band_lower,row.band_upper],[lo,hi],atol=1e-12)
            assert int(outside)==row.outside_band
        assert max(errors)<1e-9
        for j,col in enumerate(['pred_no_change','pred_ar','pred_arma','pred_band']):
            e=fc.actual_change-fc[col]
            np.testing.assert_allclose([np.sqrt(np.mean(e**2)),np.mean(abs(e))],met.loc[j,['rmse','mae']].to_numpy(dtype=float),atol=1e-10)
            if j:
                r2=1-np.sum(e**2)/np.sum(fc.actual_change**2)
                np.testing.assert_allclose(r2,met.loc[j,'oos_r2_vs_no_change'],atol=1e-10)
        band=met.iloc[3]
        summary[label]={'status':'PASS','n':count,'independent_band_max_abs_error':max(errors),'band_rmse':float(band.rmse),'band_mae':float(band.mae),'band_oos_r2':float(band.oos_r2_vs_no_change),'cw_p':float(band.cw_p_vs_no_change),'dm_p':float(band.dm_p_vs_no_change)}
    return summary


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='.repro');ap.add_argument('--strict',action='store_true');args=ap.parse_args()
    out=(ROOT/args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    baseline={p:(ROOT/p).read_bytes() for p in tracked if p and (ROOT/p).is_file()}
    source='oil-forecasting.ipynb';nb=nbformat.reads(baseline[source].decode(),as_version=4)
    nbformat.validate(nb)
    source_sha=sha(baseline[source]);start=time.time()
    report={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'notebook_sha256':source_sha,'python':platform.python_version(),'platform':platform.platform(),'status':'RUNNING','code_cells':sum(c.cell_type=='code' for c in nb.cells),'comparisons':{}}
    report['packages']=sorted([{'name':d.metadata['Name'],'version':d.version} for d in metadata.distributions()],key=lambda d:d['name'].lower())
    report['tracked_changes']=subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=ROOT,text=True).splitlines()
    report['runner_sha256']=sha(Path(__file__).read_bytes())
    report['requirements_sha256']=sha((ROOT/'requirements.txt').read_bytes())
    report['input_hashes']={p:sha(baseline[p]) for p in baseline if p.startswith('data/raw/') or p in ['data/clean/oil_monthly_clean.csv','data/clean/oil_monthly_dictionary.csv']}
    log=[]
    with tempfile.TemporaryDirectory(prefix='fe-repro-') as td:
        work=Path(td)/'repo';work.mkdir()
        for p,content in baseline.items():
            dest=work/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
        kd=Path(td)/'jupyter/kernels/python3';kd.mkdir(parents=True)
        (kd/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],'display_name':'Python 3','language':'python'}))
        before_times={p:(work/p).stat().st_mtime_ns for p in baseline}
        old=os.environ.get('JUPYTER_PATH');os.environ['JUPYTER_PATH']=str(kd.parents[1])
        os.environ['MPLBACKEND']='module://matplotlib_inline.backend_inline'
        original_cells=len(nb.cells)
        # The notebook deliberately does not overwrite saved test metrics.
        # Export its live objects after execution to audit those numbers too.
        capture=nbformat.v4.new_code_cell("""from pathlib import Path as _AuditPath
_audit_dir = REPO / '_runtime_audit'
_audit_dir.mkdir(exist_ok=True)
fc_test.to_csv(_audit_dir / 'forecasts_test.csv', index=False)
metrics_test.to_csv(_audit_dir / 'metrics_test.csv', index=False)
arma_test.to_csv(_audit_dir / 'arma_order_test.csv', index=False)
""")
        nb.cells.append(capture)
        def progress(cell,cell_index,**kw):
            msg=f'Executing cell {cell_index+1}/{original_cells}' if cell_index<original_cells else 'Capturing live test outputs for comparison';print(msg,flush=True);log.append(msg)
        try:
            NotebookClient(nb,timeout=600,kernel_name='python3',resources={'metadata':{'path':str(work)}},on_cell_execute=progress).execute()
            report['status']='PASS'
        except Exception as e:
            report['status']='FAIL';report['error']=str(e);log.append(traceback.format_exc())
        finally:
            if old is None:os.environ.pop('JUPYTER_PATH',None)
            else:os.environ['JUPYTER_PATH']=old
        for p,content in baseline.items():
            generated=work/p
            if p.startswith('data/raw/') or p in ['data/clean/oil_monthly_clean.csv','data/clean/oil_monthly_dictionary.csv']:
                report['comparisons'][p]={'status':'PASS' if generated.read_bytes()==content else 'FAIL','check':'input unchanged'}
            elif (p.startswith('data/results/Alan&Ronan/') or p.startswith('data/clean/')) and p.endswith('.csv'):
                runtime=work/'_runtime_audit'/Path(p).name
                generated=runtime if runtime.exists() else generated
                dest=out/'regenerated'/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(generated.read_bytes())
                result=compare_csv(content,generated.read_bytes())
                result=assess_difference(p,content,generated.read_bytes(),result)
                result['evidence']='runtime object' if runtime.exists() else ('regenerated file' if generated.stat().st_mtime_ns != before_times[p] else 'not regenerated')
                report['comparisons'][p]=result
            elif p.startswith('data/results/Alan&Ronan/') and p.endswith('.png'):
                from PIL import Image
                with Image.open(generated) as im:
                    report['comparisons'][p]={'status':'PASS','check':'image decodes','size':list(im.size),'dpi':im.info.get('dpi')}
                dest=out/'figures'/Path(p).name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(generated.read_bytes())
        if report['status']=='PASS':
            try:report['independent_checks']=independent_checks(work)
            except Exception as e:report['status']='FAIL';report['independent_error']=str(e)
        if any(v['status']=='FAIL' for v in report['comparisons'].values()):report['status']='FAIL'
        if report['status']=='PASS' and any(v['status']=='WARN' for v in report['comparisons'].values()):report['status']='REPRODUCED_WITH_DIFFERENCES'
        for c in nb.cells[:original_cells]:
            for o in c.get('outputs',[]):
                if o.output_type=='stream':log.append(o.text)
                elif o.output_type in ['execute_result','display_data'] and 'text/plain' in o.data:log.append(o.data['text/plain'])
        nb.cells=nb.cells[:original_cells]
        nbformat.write(nb,out/'oil-forecasting.executed.ipynb')
    report['elapsed_seconds']=round(time.time()-start,2)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'execution.log').write_text('\n'.join(log))
    print(json.dumps({'status':report['status'],'seconds':report['elapsed_seconds'],'failed':[p for p,v in report['comparisons'].items() if v['status']=='FAIL']},indent=2))
    return 0 if report['status']=='PASS' or (report['status']=='REPRODUCED_WITH_DIFFERENCES' and not args.strict) else 1
if __name__=='__main__':sys.exit(main())
