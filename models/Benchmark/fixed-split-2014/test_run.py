"""Regression checks for split, timing and independent forecasts."""
import unittest
import numpy as np
import pandas as pd
import run

class ForecastTests(unittest.TestCase):
    def test_monthly_split_and_independent_fit(self):
        frame=run.monthly_frame(pd.read_csv(run.MONTHLY))
        out,_,meta=run.evaluate(frame)
        self.assertEqual(meta['test_n'],126)
        self.assertEqual(meta['train_end'],'2013-12-31')
        train=frame.loc[:'2013-12-31'].dropna(subset=['actual']+run.FEATURES)
        import statsmodels.api as sm
        fit=sm.OLS(train.actual,sm.add_constant(train[run.FEATURES])).fit()
        np.testing.assert_allclose(out.ols,fit.predict(sm.add_constant(out[run.FEATURES])),atol=1e-10)
        self.assertEqual(meta['excluded_test_rows'],0)

    def test_test_outcomes_do_not_fit_model(self):
        frame=run.monthly_frame(pd.read_csv(run.MONTHLY))
        out,_,meta=run.evaluate(frame)
        changed=frame.copy();changed.loc['2014-01-01':,'actual']+=1000
        other,_,other_meta=run.evaluate(changed)
        self.assertEqual(meta['coefficients'],other_meta['coefficients'])
        np.testing.assert_array_equal(out.ols,other.ols)

    def test_future_raw_data_cannot_change_past_forecasts(self):
        source=pd.read_csv(run.MONTHLY)
        full,_,_=run.evaluate(run.monthly_frame(source))
        prefix,_,_=run.evaluate(run.monthly_frame(source[pd.to_datetime(source.date)<'2020-01-01']))
        pd.testing.assert_frame_equal(prefix,full.loc[prefix.index])

    def test_weekly_time_alignment(self):
        frame=run.weekly_frame(pd.read_csv(run.DAILY),pd.read_csv(run.MONTHLY))
        usable=frame.dropna(subset=run.FEATURES)
        self.assertTrue((usable.available_date<=usable.origin).all())
        self.assertTrue((usable.input_price_date<=usable.origin).all())
        self.assertTrue((usable.observed_date<=usable.index).all())

if __name__=='__main__':unittest.main()
