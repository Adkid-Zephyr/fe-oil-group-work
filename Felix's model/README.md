# Felix's model

Monthly OLS predicts the next monthly percentage change in the supplied CL1 continuous front-month series using lagged CL1 momentum, lagged CL1-CL2 carry and DXY returns lagged an extra month.

- `analyze.py`: data preparation, expanding-window forecasts, diagnostics and verification.
- `build.py`: builds the self-contained report from `source` and `results`.
- `dist/index.html`: interactive English research report; open locally.
- `results`: forecast CSV, prepared monthly data and analysis JSON.
- `source/PROTOCOL.md`: original model protocol.

The input workbook is shared at `../Data and guideline/Canvas/Oil Data.xlsx`. Run instructions are in the repository README. The copy of `analyze.py` differs from the source session only in this input path. The HTML is rebuilt so its embedded code matches the repository copy. The repository version uses English only; the original bilingual language switch and Chinese strings were removed.

This is a research draft. The target is a continuous-series price-change proxy, not validated investable futures P&L. The shared AR(1) comparison is separate from the original report.
