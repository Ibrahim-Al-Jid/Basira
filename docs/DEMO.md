# Demo runbook

Goal: a live demo that cannot be derailed by the model provider. Status of each item is stated; nothing here is claimed beyond what was run.

## What a scan costs in model requests

Today a scan makes at most one model request (`MAX_MODEL_CALLS = 1` in `backend/model_connections.py`), and only when a model is configured. Everything else is deterministic and needs no network. The figure of 26 requests belongs to the detection experiment (one request per target file), not to a scan. The multi-agent model stages planned in [PLAN.md](PLAN.md) (P09, P15) raise the per-scan count; this page must be updated with the measured number when they land, and the budget check below enforces it.

OpenRouter free tier: 50 requests per day without credit (measured on 27 November 2026), shared by every run on that key, including experiments. Do not run experiments on the demo day.

## Before the day

1. Rehearse the full path on the demo machine with the same network. Status: not done.
2. Run the local stack as in the README (verified on Linux; Docker not verified here).
3. Pre-run the demo scan once and keep its report. Status: manual today.
4. Check the day's remaining quota on the key before starting (see budget check). Status: manual, `GET https://openrouter.ai/api/v1/key`.

## Steps and fallback

| Step | Expected | If it fails |
|---|---|---|
| Start stack, open the app | page loads in seconds | restart; local lab needs PostgreSQL and Redis running |
| Start the scan on the demo project | agent lanes fill in as stages finish | the deterministic path still completes with no model: say so, it is by design |
| Open the report, switch Arabic and English | both languages render | open the pre-run report |
| Export PDF and JSON | downloads | use the files saved in step 3 |

## Step-by-step flow for the professor

Principle: the audience sees one thing at a time, and the presenter controls the pace. Stage events (P09) drive it; replay mode (below) makes it identical on a stored scan.

1. Show the empty project and the intake choices (ZIP, GitHub, HAR, config).
2. Start the scan. Agent lanes appear one by one: Maestro, Scout, Hunter, Auditor, Scribe. Say what each does as its lane fills.
3. Findings appear one at a time, highest severity first, each with its evidence and the check that found it. A "next finding" control lets the presenter advance instead of waiting.
4. Report: summary, then coverage ("what was not checked"), then export to PDF and JSON, then Arabic.
5. Close with the numbers from [research/detection-experiment.md](research/detection-experiment.md), exactly as recorded, including the limits.

Status: steps 1 to 2 exist (agent lanes show stages as they finish). Step 3 exists: the Findings tab has a "Step-by-step view" button; it hides all findings, then "Next finding" (or Space, and the arrow keys, which follow the page direction in Arabic) reveals one finding group at a time, with Restart, Show all and a shown counter. Checked in a real browser in English with the one-finding sample scan (0 of 1 shown, then Next); a multi-finding run and the Arabic view were not checked. Replay of a stored scan is built (see "Built in P20").

## Built in P20

- **Per-scan model request budget check.** Before the model stage starts, the worker counts the model requests Basira started in the project today (UTC) and compares them with the daily limit (`backend/model_budget.py`). The limit is `BASIRA_MODEL_DAILY_LIMIT` when set; otherwise 50 for a model whose name ends in `:free` (the free-tier figure measured on 27 November 2026), and no limit for any other model. When the remaining count is below what one scan needs (`MAX_MODEL_CALLS`), the model stage is not started, the scan finishes on the deterministic path, and the scan activity shows a "Model not used" event with the reason in Arabic. Limit: it counts requests made through this app in this project only. Use of the same key elsewhere is not visible, so the manual quota check in "Before the day" still applies. Tested with unit tests and a counting test on the scan table; not run against a live provider.
- **Replay of a stored scan.** On the scan progress page of a finished scan, "Start replay" plays the stored events back in order on the agent lanes and the event list, with pause, resume, restart, skip to end and 1x, 2x or 4x speed (gaps follow the stored timestamps, clamped between 0.35 s and 1.8 s). Opening the page with `?replay=1` starts it by itself. It reads only the events the page already loaded: no model or network request. Checked in a real browser (Chromium via Playwright) on a stored 8-event scan, in Arabic and English, with no page errors and no horizontal overflow. Timing rules have unit tests (`frontend/src/replay.test.mjs`, run in CI). Not checked: a long scan with many events, and the report page (replay lives on the progress page only).

- **Dashboard.** The Overview page shows the latest scan's numbers, the trend over the last 12 scans and the change since the previous scan, each number linked to its scan with the scan's time. The "Presentation mode" button enlarges the numbers for a projector and Esc leaves it. Checked in a real browser in Arabic and English on four scans of one input; not checked on a projector or a long history.

## Not built yet

- Rehearsal on the demo machine, and pre-running the demo scan, remain manual steps.
