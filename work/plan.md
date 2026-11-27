# Marsad plan

The one living plan. Ten phases, regrouped on 27 November 2026 from the original nineteen. The original plan with every acceptance record is kept in [the archive](../docs/archive/plan-19-phases.md); the old phase numbers are in the last column so old references still resolve.

Status values: **done** (acceptance evidence exists and was re-run or re-checked on 27 November 2026), **partial**, **open**. Anything not run says so.

| # | Phase | What it covers | Status | Old phases |
|---|---|---|---|---|
| 1 | Foundations | Agent roles and contracts, rule registry, evidence-verified output, file selection | done | 1, 2 |
| 2 | Reports and export | Report pages, AR/EN HTML, JSON, SARIF, PDF engine, comparison, comments, advanced reports | done | 3, 6 |
| 3 | Platform core | Identity (local accounts, OIDC), PostgreSQL with row-level security, background jobs on Redis and Celery, source consolidation | done | 4, 7 |
| 4 | Detection catalog | 100 checks, input adapters, six memory types, provider policy, vulnerability taxonomy | done | 5, 6 |
| 5 | Evidence and provenance | Asset and evidence contracts, source analysis, source import, web and API evidence | done | 9, 10, 11 |
| 6 | Product journey | Projects workspace, personal ownership, migration off organizations | done | 8, 13 |
| 7 | Intake | ZIP, GitHub (App) and approved website URL intake with passive evidence | done | 14 |
| 8 | Tools and agents | Pinned tool registry, offline sandboxed execution, verified agent workflow, checkpoints and memory | done | 15, 16 |
| 9 | Live experience and reporting | Live per-agent progress view, report model and page, PDF in both languages, new visual design | **open** | 17 |
| 10 | Evaluation, hardening and release | Independent evaluation, benchmark runs, stress and recovery, legacy removal, release decision | **partial** | 12, 18, 19 |

## What was verified on 27 November 2026

- Backend: 245 existing tests passed (Python 3.13), plus the new taxonomy tests. Frontend built with Vite.
- Real stack: PostgreSQL 17, Redis 7.2 and a Celery worker ran with the app. The Phase 13 browser acceptance (`tests/browser_phase13.py`) passed in English and Arabic against that stack, including ZIP scan, report, PDF export and cross-account isolation.
- Found and fixed: `current_alias` was read before assignment in the Dockerfile check (`backend/checks/config.py`).
- Not re-run here: Docker image build, the Docker-only acceptance (`tests/container_phase45.py`), the other Playwright suites, real model provider calls, S3 intake.

## Phase 9: live experience and reporting (open)

Gap measured on the running app: the scan page shows one "Queued" timeline entry. It does not show which agent works on what.

1. Live agent view: the five roles (coordinator, planning, analysis, verification, reporting) as lanes with state (waiting, running, done, skipped, failed), current task, tool in use, items done and remaining, elapsed time, and the evidence each produced. Driven by the existing scan event stream, plus per-role task events where the runtime does not emit them yet.
2. Report model: one immutable `ReportModel` per scan, rendered to the web page, Arabic and English text, and PDF, with a cross-format consistency test.
3. PDF: keep `backend/report_pdf.py` (fpdf2 and uharfbuzz), add tests for shaping, mixed direction, long paths and many pages.
4. Visual design: a new design system (tokens, type, layout, motion) applied to landing, sign-in, workspace shell, intake, live view, report and dashboard. Screenshots before and after in `docs/archive/`.
5. Intake: accept every input in more than one way (drag and drop, file picker, paste, URL) with no extra confirmation steps beyond the one permission statement the policy requires.
6. Naming: rename only after the owner picks a name, applied once across repo, package, UI and README.

## Phase 10: evaluation, hardening and release (partial)

- Done: reference sample evaluation and release acceptance for the original scope ([archive/PHASE12.md](../docs/archive/PHASE12.md), [RELEASE.md](../docs/RELEASE.md)).
- Open: labeled corpus and four-configuration comparison (native rules, tools only, single agent, multi-agent), described in [research/benchmarks.md](../docs/research/benchmarks.md). No accuracy number is published until it runs.
- Open: stress and fairness tests, restore drills on a copied database, removal of the remaining `org_id` compatibility paths after a verified migration, release manifest, and the go or no-go record.

## Documentation map

See [docs/README.md](../docs/README.md).
