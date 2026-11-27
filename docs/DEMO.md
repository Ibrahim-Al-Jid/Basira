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

## Not built yet (planned, tracked as P20 in the plan)

- Per-scan request budget check that refuses to start a model stage when the remaining daily quota is too low and says why.
- Replay mode: play back a stored scan's events in the live UI when the provider is down.
- A dashboard view made for presenting.
