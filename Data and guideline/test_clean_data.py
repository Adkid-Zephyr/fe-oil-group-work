"""Regression and conservation tests for the shared dataset."""
import unittest
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import openpyxl
from clean_data import ROOT, RAW, EXPECTED_SHA, SCHEMAS, digest, normalize_records, make_targets

class CleaningTests(unittest.TestCase):
 def test_original_workbook_unchanged(self):
  self.assertEqual(digest(RAW),EXPECTED_SHA)

 def test_every_dated_numeric_value_and_missing_cell_preserved(self):
  wb=openpyxl.load_workbook(RAW,read_only=True,data_only=True)
  for sheet,(filename,names) in SCHEMAS.items():
   raw=list(wb[sheet].values)
   out=pd.read_csv(ROOT/'Cleaned data'/filename,float_precision='round_trip')
   self.assertTrue(out.date.is_monotonic_increasing)
   self.assertFalse(out.date.duplicated().any())
   for row in out.itertuples(index=False):
    source=raw[row.source_excel_row-1]
    self.assertEqual(row.date,source[0].strftime('%Y-%m-%d'))
    for j,col in enumerate(names,start=1):
     actual=getattr(row,col);expected=source[j]
     if expected is None:self.assertTrue(pd.isna(actual),(sheet,col,row.date))
     else:self.assertEqual(actual,expected,(sheet,col,row.date))

 def test_quarantine_preserves_all_undated_records(self):
  wb=openpyxl.load_workbook(RAW,read_only=True,data_only=True)
  raw=list(wb['Industry_D'].values)
  q=pd.read_csv(ROOT/'Data quality/quarantined_rows.csv')
  self.assertEqual(len(q),534)
  for row in q.itertuples():
   observed=json.loads(row.raw_values_json);src=raw[row.source_excel_row-1]
   self.assertEqual(list(observed.values()),list(src))
   self.assertIsNone(src[0])

 def test_source_interpolation_is_masked_only_in_derived_column(self):
  w=pd.read_csv(ROOT/'Cleaned data/industry_weekly.csv')
  flag=w.commercial_long_is_source_interpolated
  self.assertEqual(int(flag.sum()),1)
  self.assertEqual(w.loc[flag,'date'].iloc[0],'2001-09-07')
  self.assertEqual(w.loc[flag,'commercial_long'].iloc[0],332195)
  self.assertTrue(w.loc[flag,'commercial_long_unimputed'].isna().all())
  np.testing.assert_allclose(w.loc[~flag,'commercial_long'],w.loc[~flag,'commercial_long_unimputed'],equal_nan=True)

 def test_negative_price_not_deleted(self):
  d=pd.read_csv(ROOT/'Cleaned data/industry_daily.csv')
  self.assertEqual(d.loc[d.date=='2020-04-20','cl1'].iloc[0],-37.63)

 def test_all_formula_caches_reconciled_and_label_not_misrepresented(self):
  f=pd.read_csv(ROOT/'Data quality/formula_audit.csv')
  self.assertEqual(len(f),356)
  np.testing.assert_array_equal(f.cached_value,f.recomputed_value)
  m=pd.read_csv(ROOT/'Cleaned data/industry_monthly.csv')
  np.testing.assert_array_equal(m.commercial_long_plus_short_source,m.commercial_long+m.commercial_short)
  self.assertNotIn('total_open_interest',m.columns)

 def test_shared_benchmark_same_dates_and_values(self):
  t=pd.read_csv(ROOT/'Cleaned data/monthly_targets.csv')
  b=pd.read_csv(ROOT/'Benchmark results/forecasts.csv')
  e=t[t.is_shared_evaluation]
  self.assertEqual(e.month.tolist(),b.month.tolist())
  self.assertEqual(len(e),114)
  self.assertTrue(e.target_valid.all())
  for c in ['actual_price','benchmark_price','actual_return_pct','benchmark_return_pct']:
   np.testing.assert_allclose(e[c],b[c],rtol=1e-12,atol=1e-12)

 def test_no_bridging_a_missing_month_or_nonpositive_price(self):
  m=pd.DataFrame({'month':['2000-01','2000-03','2000-04','2000-05','2000-06'],'cl1':[10,20,-5,15,0]})
  t=make_targets(m)
  self.assertEqual(len(t),6)
  self.assertTrue(t.actual_return_pct.isna().all())
  self.assertFalse(t.target_valid.any())

 def test_dates_and_numeric_corruption_fail_loudly(self):
  header=('Date','CL1');r=(datetime(2000,1,1),12)
  with self.assertRaisesRegex(AssertionError,'duplicate dates'):normalize_records([header,r,r],'Test_D',['cl1'])
  with self.assertRaisesRegex(AssertionError,'nonnumeric'):normalize_records([header,(datetime(2000,1,1),'bad')],'Test_D',['cl1'])
  with self.assertRaisesRegex(AssertionError,'unexpected date'):normalize_records([header,('01/02/03',12)],'Test_D',['cl1'])
  with self.assertRaisesRegex(AssertionError,'unnamed columns'):normalize_records([('Date','CL1',None),(datetime(2000,1,1),12,99)],'Test_D',['cl1'])

 def test_monthly_panel_alignment_and_target_future_invariance(self):
  j=pd.read_csv(ROOT/'Cleaned data/monthly_observations.csv')
  self.assertEqual(len(j),355)
  for c in ['industry__date','macro__date','stocks__date']:
   self.assertEqual(j[c].str[:7].tolist(),j.month.tolist())
  m=pd.read_csv(ROOT/'Cleaned data/industry_monthly.csv')
  t=make_targets(m);prefix=make_targets(m[m.month<='2018-12'])
  pd.testing.assert_frame_equal(prefix,t.iloc[:len(prefix)].reset_index(drop=True))

 def test_derived_dollar_units_and_existing_model_inputs(self):
  macro=pd.read_csv(ROOT/'Cleaned data/macro_monthly.csv')
  np.testing.assert_allclose(macro.dxy_return_pct,macro.dxy_return_decimal*100,rtol=1e-13,atol=1e-13)
  panel=pd.read_csv(ROOT/'Cleaned data/monthly_observations.csv').set_index('month')
  old=pd.read_csv(ROOT.parent/"Felix's model/results/monthly_prepared.csv").set_index('target_month')
  self.assertEqual(list(panel.index),list(old.index))
  ret=panel['industry__cl1'].pct_change(fill_method=None)*100
  computed={'actual':ret,'momentum':ret.shift(1),'carry':(100*(panel['industry__cl1']-panel['industry__cl2'])/panel['industry__cl1']).shift(1),'dollar':panel['macro__dxy_return_pct'].shift(2)}
  for col,values in computed.items():
   np.testing.assert_allclose(values,old[col],rtol=1e-12,atol=1e-12,equal_nan=True)

 def test_manifest_hashes_match(self):
  meta=json.loads((ROOT/'Data quality/manifest.json').read_text())
  for path,h in meta['files_sha256'].items():self.assertEqual(digest(ROOT/path),h,path)

if __name__=='__main__':unittest.main(verbosity=2)
