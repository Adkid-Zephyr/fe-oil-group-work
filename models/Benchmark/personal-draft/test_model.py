"""Regression checks for the switch from raw Excel to shared cleaned inputs."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from analyze import ROOT, SNAPSHOT, load_cleaned_inputs, make_frame, walk_forward

class CleanedModelTests(unittest.TestCase):
    def test_model_reads_cleaned_files_without_raw_excel(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            shutil.copytree(SNAPSHOT/'Cleaned data',folder/'Cleaned data')
            shutil.copytree(SNAPSHOT/'Data quality',folder/'Data quality')
            self.assertFalse((folder/'Canvas').exists())
            ind,mac,target,provenance=load_cleaned_inputs(folder)
            self.assertEqual(len(ind),355)
            self.assertEqual(len(provenance['input_hashes']),3)
            frame=make_frame(ind,mac)
            np.testing.assert_allclose(frame.actual,target.actual_return_pct,equal_nan=True,atol=1e-12,rtol=1e-12)

    def test_altered_cleaned_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            shutil.copytree(SNAPSHOT/'Cleaned data',folder/'Cleaned data')
            shutil.copytree(SNAPSHOT/'Data quality',folder/'Data quality')
            path=folder/'Cleaned data/industry_monthly.csv'
            path.write_text(path.read_text()+'\n')
            with self.assertRaisesRegex(AssertionError,'Cleaned file changed'):
                load_cleaned_inputs(folder)

    def test_changed_cleaning_version_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            shutil.copytree(SNAPSHOT/'Data quality',folder/'Data quality')
            path=folder/'Data quality/summary.json'
            v=json.loads(path.read_text());v['dataset_version']='2.0.0';path.write_text(json.dumps(v))
            with self.assertRaisesRegex(AssertionError,'Review changed cleaning version'):
                load_cleaned_inputs(folder)

    def test_forecasts_reproduce_pre_migration_values(self):
        ind,mac,target,_=load_cleaned_inputs()
        frame=make_frame(ind,mac)
        frame['actual']=target.actual_return_pct
        frame['momentum']=frame.actual.shift(1)
        forecasts=walk_forward(frame)
        old=pd.DataFrame(json.loads((ROOT/'validation/pre_cleaning_reference.json').read_text())['forecasts'])
        self.assertEqual(forecasts.month.tolist(),old.month.tolist())
        self.assertEqual(len(forecasts),114)
        np.testing.assert_allclose(forecasts[['actual','ols','mean','zero']],old[['actual','ols','mean','zero']],rtol=0,atol=1e-12)
        saved=pd.read_csv(ROOT/'results/forecasts.csv')
        np.testing.assert_allclose(forecasts.ols,saved.ols,rtol=0,atol=1e-12)

    def test_future_truncation_and_shared_evaluation(self):
        ind,mac,target,_=load_cleaned_inputs()
        all_forecasts=walk_forward(make_frame(ind,mac))
        earlier=walk_forward(make_frame(ind.loc[:'2018-12'],mac.loc[:'2018-12']))
        np.testing.assert_allclose(earlier.ols,all_forecasts.ols.iloc[:len(earlier)],rtol=0,atol=1e-12)
        expected=target.loc[target.is_shared_evaluation]
        self.assertEqual(all_forecasts.month.tolist(),expected.index.astype(str).tolist())
        self.assertTrue(expected.target_valid.all())
        np.testing.assert_array_equal(all_forecasts.zero,expected.benchmark_return_pct)

if __name__=='__main__':unittest.main(verbosity=2)
