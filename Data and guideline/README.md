# Shared data and guidance

## Canvas sources

The following existing local downloads were archived on 27 October 2026. The course module listing and assignment page were checked live. A fresh PDF download was blocked by Chrome, so these copies are not represented as newly downloaded or byte-verified against the server. SHA-256 hashes are in `source_manifest.json`.

- [Coursework brief](https://canvas.imperial.ac.uk/courses/9001/files/2784232?module_item_id=2361031): `Canvas/26 Fintech CW Financial Econometrics.pdf`.
- [Oil dataset](https://canvas.imperial.ac.uk/courses/9001/modules/items/2361032): `Canvas/Oil Data.xlsx`.
- [Syllabus](https://canvas.imperial.ac.uk/courses/9001/modules/items/2361027): `Canvas/26_Syllabus_Financial_Econometrics.pdf`.
- [Student AI guidance](https://canvas.imperial.ac.uk/courses/5594/files/2665512?module_item_id=2274656): `Canvas/Student Guidance on Use of AI 2026.27.pdf`.
- [Live group assignment](https://canvas.imperial.ac.uk/courses/9001/assignments/195314): displayed deadline 27 November 2026, 16:00; one submission attempt; choose one group member to submit. Verify the Canvas timezone before relying on the time.

The recording and the source research session also identify a 3,000-word maximum on the assessment-information page, conflicting with the brief. Confirm the limit with the teaching team; the working writing target is 2,000 words.

The brief asks for a 2,000-word written report with program files and a five-minute presentation plus Q&A. Explain the target, frequency, predictors, stationarity, residual autocorrelation, heteroskedasticity, parameter stability and out-of-sample accuracy. Include at least one simple naive benchmark. Explain results to an oil trader.

The PDF carries an Autumn 2025 heading despite appearing in the 2026-2027 course. Do not infer a current calendar deadline from its Week 7 wording.

## Working conventions

Keep original data immutable. Store model-specific transformations and results in the relevant model folder. Use English filenames and prose; preserve the team folder spellings requested by the group. Record methodological changes before rerunning comparisons, including any choices informed by previously observed test results.

`Meetings` contains source-linked draft minutes. Model settings proposed in `BENCHMARKS.md` are analytical recommendations, not automatically decisions made in the recorded meeting.

## Shared benchmark - completed by Felix

Use the **no-change benchmark**. The [short guide](BENCHMARKS.md) explains it; [forecast CSV](Benchmark%20results/forecasts.csv) is ready for teammates to use. Historical-mean and AR(1) results are retained only as optional comparisons.
