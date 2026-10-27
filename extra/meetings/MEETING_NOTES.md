# Group work planning meeting

Prepared 27 October 2026 from the user-supplied 24-minute recording. The recording date is not independently confirmed. These are draft minutes based on local automatic speech recognition, not a verbatim or speaker-verified record. Timestamps identify passages for checking against the original audio. Personal conversation and unrelated banter are omitted.

## Main discussion and emerging agreement

| Recording time | Discussion | Outcome or uncertainty |
| --- | --- | --- |
| 00:29-01:29; 03:24-04:39 | Topology versus familiar econometric methods | Prefer an approach the whole group can explain. Advanced methods were discussed but not selected. Clear justification matters more than complexity. |
| 05:10-06:25 | Report, presentation and independent model ideas | Prioritise the report and understanding the model. Develop alternatives before selecting the final approach. A website was discussed but was not a required group deliverable. |
| 07:13-09:28 | Divide the group into smaller modelling teams | Discussion moved toward three workstreams, including a simple benchmark. The current folder names and owners come from Felix's explicit repository request, not uncertain speaker identification. |
| 09:28-10:31; 23:49-23:54 | Benchmark selection | A simple reference model is needed. ARIMA was mentioned; Fama-French was questioned. The exact benchmark remained open at the end. |
| 10:33-11:12 | Out-of-sample testing | Clarified that a later portion of the supplied data can be held out. No exact shared split or frequency was agreed in the recording. |
| 11:18-12:13 | Forecasting and trading rules | Distinguished prediction from a full trading strategy. Trader-oriented interpretation remains relevant. |
| 12:13-13:08 | Assessment requirements | Participants noted the 2,000-word brief, a possible 3,000-word Canvas limit and the old Autumn 2025 heading. Some spoken grading and presentation claims were tentative; use the source documents and live Canvas pages. |
| 17:29-19:38; 21:29-22:51 | Shared cleaning versus team-specific preparation | A common cleaned dataset was proposed, but participants also noted cleaning depends on modelling choices. Final cleaning ownership and exact rules remain ambiguous. Keep the original workbook shared and record each team's transformations. |
| 20:05-20:41; 21:08-22:42 | Internal deadlines | Thursday was discussed for data preparation and next Thursday for modelling. The calendar dates were not established reliably. Confirm dates from the group message mentioned in the recording. |
| 21:35-21:54; 23:11-23:39 | Work allocation | Two paired modelling workstreams and a solo benchmark/model workstream were discussed. Felix's current request confirms the folder ownership below. |

## Current workstreams

| Owner(s) | Work |
| --- | --- |
| Felix | Build the benchmark comparison and contribute a simple model. Existing OLS research is stored in `models/Benchmark`. |
| Alan and Ronan | Develop and document their candidate model in `Alan&Ronan’s model`. |
| Mike and Div | Develop and document their candidate model in `Mike&Div‘s model`. |
| Whole group | Compare models on compatible targets and dates, choose the final approach, explain diagnostics and limitations, and prepare the report and presentation. |

## AI assistance

At 01:35-03:11, 15:03-15:31 and 18:46-19:06, participants discussed AI-generated drafts, understanding the results and the risk of accepting an initial output without scrutiny. The recording includes a reminder not to use AI output directly as the final submission. Consult the archived course guidance for the actual rules; comments in this discussion do not establish permission from the teaching team.

## Items to resolve

- Confirm internal calendar deadlines and the final data-cleaning owner from the group's written follow-up.
- Agree a common target, frequency, forecast horizon, split and predictor availability rules before ranking all three teams' models.
- Review the proposed historical-mean, zero-change and AR(1) comparison in `../BENCHMARKS.md`. These specific settings were selected after this meeting for Felix's monthly task.
- Resolve the 2,000 versus 3,000 word discrepancy and the presentation slot with the teaching team.
- Select the final model(s), presenters and single submission owner after reviewing the results.

## Recording provenance

The original audio remains in the user's local files and has not been uploaded to this repository. `recording_provenance.json` records its checksum and duration. `DISCUSSION_EXCERPTS.md` provides timestamped ASR excerpts from task-relevant sections. Speaker identities and ambiguous names have not been inferred from voices.
