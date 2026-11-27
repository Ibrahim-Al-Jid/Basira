# 6. Usability check (five users)

**Status: not run. No result in this file is real until a session is recorded in the sheet below.** The plan (P24) asks for five real users and their results.

## Question

Can a person who did not build Basira start a scan, read the report, and say what to fix first, without help?

## Participants

Five people who write or review code (students or junior developers), none involved in building Basira. Record only: participant ID (U1 to U5), role, years of experience, preferred language (Arabic or English). No names, no recordings without consent.

## Setup

Same machine and build for everyone (git commit recorded). Demo project: the built-in sample or the demo ZIP, same for all. Provider: none (deterministic path) so the result does not depend on a model. The tester reads the script aloud and does not help; hints are logged.

## Tasks

| # | Task | Success |
|---|---|---|
| T1 | Start a scan on the demo project | scan submitted without a hint |
| T2 | Say when the scan is finished and what each agent did | names at least 3 of the 5 roles |
| T3 | Open the report and find the most severe finding | picks the highest-severity one |
| T4 | Say what to change to fix it | matches the stated fix |
| T5 | Switch the report to the other language and export PDF | file downloaded |
| T6 | Say what the scan did not check | mentions coverage or limits |

Measure per task: success (yes, with hint, no), time in seconds, number of wrong clicks, and a free comment. After the tasks, the SUS questionnaire (10 items, 1 to 5) and two open questions: "What confused you?" and "What would you trust or not trust here?".

## Consent

Read before starting: participation is voluntary, you can stop any time, notes are anonymous, you are testing the tool, not being tested.

## Results sheet (empty)

| User | Lang | T1 | T2 | T3 | T4 | T5 | T6 | Time total | SUS | Main problem |
|---|---|---|---|---|---|---|---|---|---|---|
| U1 | | | | | | | | | | |
| U2 | | | | | | | | | | |
| U3 | | | | | | | | | | |
| U4 | | | | | | | | | | |
| U5 | | | | | | | | | | |

How to report: task success counts out of 5, median time, mean SUS with the note that n = 5 gives no statistical claim, and the list of problems found with the fix made. Present it as a small formative check.
