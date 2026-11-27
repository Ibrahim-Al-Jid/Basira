# Thesis and defense package

Graduation project: **Basira (بصيرة)**, a multi-agent security-review workspace for project files. This folder is the written thesis (P24 in [PLAN.md](../PLAN.md)) and the defense material. It is written in English. The owner decides if and when it is translated to Arabic.

Rule for every chapter: a number appears only if it was measured and recorded in this repository, and its limit is stated next to it. Where something was not run, the text says "not run".

## Reading order

| # | File | Content |
|---|---|---|
| 1 | [problem_and_scope.md](problem_and_scope.md) | Problem, research questions, scope, what is out of scope |
| 2 | [related_work.md](related_work.md) | The 72-tool survey, what Basira does differently and what it does not |
| 3 | [architecture_and_data.md](architecture_and_data.md) | Agents, tools, memory, data design, security design |
| 4 | [evaluation.md](evaluation.md) | Method, every recorded number, every limit, how to reproduce |
| 5 | [ethics.md](ethics.md) | Authorization rules for scanning, data handling, model use |
| 6 | [usability_check.md](usability_check.md) | Protocol for the five-user check and the results sheet (not run yet) |
| 7 | [slides.md](slides.md) | Slide-by-slide outline with speaker notes, timed |
| 8 | [defense_questions.md](defense_questions.md) | Likely professor questions with evidence-backed answers |

The live demo is in [DEMO.md](../DEMO.md). Run steps are in the [README](../../README.md).

## Status of this package (27 November 2026)

- Chapters 1 to 5 and 7 to 8: written from the repository as it is on `main`.
- Chapter 6: protocol written, **no user has been tested**. Do not present results until the sheet is filled with real sessions.
- Chapter 4: the four-configuration comparison is incomplete. C1 and C2 have results; C3 and C4 have code but no run (free-tier request cap). The chapter must be updated when they run. The plan also asks for a 24-case holdout (12 clean, 12 positive) and a second labeler; neither exists yet.

## Reproduce the numbers

From the repo root, after the setup in the README:

```bash
npm test                                           # backend tests (284 passed, 1 skipped on 27 Nov 2026)
.venv/bin/python -m backend.synthetic_evaluation   # 18-case synthetic corpus, per-domain precision and recall
.venv/bin/python -m backend.detection_experiment --config static   # DVWA, static checks, downloads pinned files
```

`--config single`, `team` and `team-tools` need `OPENROUTER_API_KEY` and a day with free quota (26, about 130 and about 200 requests). The recorded C2 run is in `docs/research/detection-runs/`.
