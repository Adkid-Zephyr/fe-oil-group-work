# Felix OLS: original research workspace

**For current group work, start with [oil-forecasting.ipynb](../../oil-forecasting.ipynb), Sections 5.1 and 7.1.** For the standalone model and exact variable definitions, use the [handoff guide](handoff/README.md).

This folder's `Benchmark` name is historical. The OLS model here is not the shared no-change benchmark; that is documented in [guidelines/BENCHMARKS.md](../../guidelines/BENCHMARKS.md).

| Item | Location | Role |
| --- | --- | --- |
| Current standalone handoff | [felix-model.ipynb](../../felix-model.ipynb) | Mike's current cleaned data; training-only reference. |
| Original model | [analyze.py](analyze.py) | Monthly expanding-window OLS using raw Excel; evaluation starts in 2015. |
| Original results | [data/results/Benchmark](../../data/results/Benchmark/) | Earlier forecasts and analysis JSON. |
| Original report | [dist/index.html](dist/index.html) | Download/open locally; GitHub displays HTML source. |
| Original protocol | [source/PROTOCOL.md](source/PROTOCOL.md) | Earlier model and evaluation specification. |
| Fixed-2014 experiment | [fixed-split-2014/README.md](fixed-split-2014/README.md) | Historical weekly/monthly experiment with a different split. |

`build.py` builds the original report. Running the original `analyze.py` writes older experiment outputs and prepared data; it is not the current group's cleaned-data workflow. Historical results are retained, not relabelled as current validation results.

[Full repository overview and Felix's deliverable map](../../README.md).
