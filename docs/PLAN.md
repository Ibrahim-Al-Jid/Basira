# Basira plan

The single source of truth for what Basira is, what is built, what is next, and how each piece is accepted. Everything else in the repo supports this file. Edited on 27 November 2026.

Contents: [1 Product](#1-product) · [2 Current position](#2-current-position) · [3 Phases](#3-phases) · [4 Phase details](#4-phase-details) · [5 Architecture](#5-architecture) · [6 Agents, tools, memory](#6-agents-tools-and-memory) · [7 Contracts](#7-contracts) · [8 Acceptance](#8-acceptance) · [9 Risks](#9-risks-and-limits) · [10 Decisions](#10-decisions) · [11 Conventions](#11-conventions)

## 1. Product

**Basira (بصيرة)** is a multi-agent web security review workspace. A developer gives it a project (ZIP, authorized GitHub repository, approved website pages, or captured evidence), watches named agents work on it live, and gets an evidence-linked report in Arabic or English, with repair guidance and a recheck after the fix.

Tagline from the blueprint: Detect. Verify. Remediate. Secure.

| Audience | Job | Evidence it works |
|---|---|---|
| Individual developer (first audience) | Review a change or release with no setup | Starts a review, sees what each agent did, gets a next action or an explicit coverage limit |
| Reviewer | Check why a finding appeared and record a decision | Opens the source location, tool and snapshot, records a decision apart from the technical finding |
| Local operator | Keep the install repeatable and recoverable | Installs from the documented profile, restores a backup, report digests match |
| Small team (hypothesis) | Share reviews | Only after demand and the ownership model are validated |

Principles: no manual steps beyond one permission statement; every input accepted in more than one way; findings only with verified evidence; Arabic and English share the same facts; the report works with no model provider; nothing is called accurate until measured; unsupported coverage is shown as a gap, never as clean.

Analysis modes:

| Mode | Inputs | Limits |
|---|---|---|
| White-box | ZIP, GitHub snapshot pinned to a commit, manifests, lockfiles, Docker, Kubernetes, CI, IaC, OpenAPI | Read-only, offline; every source, rule, policy and tool version recorded |
| Passive web | Approved website pages, saved HTTP evidence, HTML, HAR, saved passive ZAP output | Records capture scope; importers do not replay or resolve external references |
| Active verification | Owner-proven sites only | Proposed, see P14 and decision A |
| Remediation | Human-reviewed recommendations, optional approved patch draft | Isolated draft, deployment and merge stay with the human |

## 2. Current position

Phases P01 to P08 are built; this plan has 24 phases (P01 to P24). P09 has its model lane in place; **work is in P10** (redesign), then P20 and P19. See the order of work below.

Verified on 27 November 2026:
- Python 3.13: 251 backend tests pass, 1 skipped.
- Real stack without containers (PostgreSQL 17, Redis 7.2, API, dispatcher, Celery worker, Chromium): personal-projects browser acceptance passed in Arabic and English, covering ZIP scan, report, PDF export and cross-account isolation.
- Local lab starts with `npm start`; UI, `/demo` and `/api/taxonomy` respond.
- Not run: Docker image build and Compose, `tests/container_smoke.py`, the other browser suites, real model provider calls, S3 intake.

Measured gaps:
- Scan page shows one "Queued" entry, no per-agent view.
- All 100 checks are passive. 41 of 75 taxonomy subdomains have no check ([taxonomy](taxonomy.md)).
- Anonymous lab (`/demo`) and organization compatibility keys still exist.
- No accuracy number exists. No benchmark has been run.

## 3. Phases

Status: **done** (built, tests exist, acceptance re-run or re-checked on 27 November 2026 unless noted), **partial**, **open**, **proposed** (needs an owner decision).

| ID | Phase | Scope | Status |
|---|---|---|---|
| P01 | Foundations | Agent roles and contracts, rule registry, evidence-verified output, file selection | done |
| P02 | Reports and export | Report pages, Arabic and English HTML, JSON, SARIF, PDF, comparison, comments, finding statuses | done |
| P03 | Platform core | Local accounts, OIDC, PostgreSQL with row-level security, Redis and Celery with outbox and leases | done |
| P04 | Detection catalog | 100 checks in six families, vulnerability taxonomy and API, input adapters | done |
| P05 | Evidence and provenance | Evidence contracts, source analysis, evidence links, web and API evidence | done |
| P06 | Intake | ZIP, GitHub App, approved website pages, HAR, ZAP and OpenAPI import, quarantine lifecycle | done |
| P07 | Tools, agents and memory | Pinned tool registry, offline execution, five-stage graph, model gateway and advisor, checkpoints, scan memory | partial |
| P08 | Product journey | Personal projects workspace, ownership migration, project pages | done |
| P09 | Live experience and report model | Per-agent live view, frozen report model, report and PDF parity tests | open (current) |
| P10 | Redesign: UI/UX, fewer steps, automation | Design system, single-screen Scan flow, live view, decision-first report, dashboard, landing; 10 actions to 3 | open (current) |
| P11 | Recheck and history | Fixed, Still present, New, Changed, Inconclusive, Needs review | open |
| P12 | Remediation | Repair plans, approval, optional sandbox patch draft | open |
| P13 | Help and report assistant | Static contextual help, then the cited read-only report assistant (committed) | open |
| P14 | Active verification | Owner-proven, rate-limited, non-destructive probes for the taxonomy gaps | proposed |
| P15 | Learning from past scans | Owner decisions and recheck outcomes feed ranking, confidence and suppression, measured before it is enabled | open |
| P16 | Performance and data design | Latency budgets, incremental scans, caching, indexes, schema review, load tests | open |
| P17 | Evaluation | Benchmarks, labeled corpus, four-configuration comparison with measured detection rates | open |
| P19 | Coverage expansion and project review | Source-code analysis checks (the measured gap: 0 of 13 on DVWA PHP), starting with injection, XSS, access control and file handling in PHP, JavaScript and Python; research which classes are realistically detectable, close the cheap gaps in the 75-subdomain taxonomy, review what exists against evidence and list real improvements | open |
| P20 | Demo reliability | Runbook ([DEMO.md](DEMO.md)), per-scan request budget check, replay of a stored scan in the live UI, presentation dashboard; graduation demo is live in front of a professor | open, runbook written |
| P21 | Provider-agnostic model settings | Settings page: choose a preset provider (OpenRouter, OpenAI, Anthropic, Google Gemini) or add a custom OpenAI-compatible provider by base URL (https, public host only, checked against private and internal addresses, checked again at request time), paste key, list that provider's models, pick one; warning and acknowledgement before any non-free model; free default path stays OpenRouter free models; keys encrypted server-side and masked in the UI | done in code: adapters, gateway routing, storage (`provider`, `base_url`; migration 0016) and settings UI with cost acknowledgement; tested with fakes and a mocked-API browser run, not against live OpenAI, Anthropic or Gemini. Open: show the provider in the scan report, org-level settings UI is still OpenRouter-only |
| P22 | Self-security | Basira scanned by itself; scanned content treated as untrusted input to the agents (prompt-injection tests); key storage, custom-provider URL and export paths reviewed; threat model written | open |
| P23 | Quality gates | Precision and false-positive rate measured with the detection recall; a regression gate in CI that fails when either drops; flaky-test policy; reproducible evaluation script | open |
| P24 | Thesis and defense package | Problem statement, related work (from `research/competitors.md`), architecture, evaluation chapter with limits, ethics and authorization rules for scanning, a small usability check with real users, slides, demo script, prepared answers to likely questions | open |
| P18 | Hardening and release | Isolation and recovery acceptance, Docker verified, legacy removal, release manifest, rename | open |

Order of work, set by the agent as the expert (owner delegated sequencing, 27 Nov 2026): P21 (provider settings, done), P09 model lane (done), P10 redesign slices a to f (current, the owner is waiting for it), then P20 (replay and budget check), P19 (source-code checks, the biggest measured gap), P11, P17 and P23 (measured evaluation with precision, when the free-tier cap allows), P13, P16, P15, P22, P07 gaps, P12, P24, P18. P14 follows decision A and ships before P17 if approved, so evaluation covers it.

## 4. Phase details

### Built (P01 to P08), with the evidence

| Area | What exists | Where |
|---|---|---|
| Detection | 100 checks, six families (HTML, Web headers and cookies, Dependencies, Infrastructure, CI, App config) | `backend/checks/`, `backend/artifact_review.py`, [checks](checks/README.md) |
| Taxonomy | 17 domains, 75 subdomains, 159 problems, mapped to CWE, OWASP Top 10:2025, OWASP API Top 10 2023, WSTG | `backend/taxonomy.py`, [taxonomy](taxonomy.md) |
| Tools | Gitleaks 8.30.1 and OSV-Scanner 2.7.1 pinned, offline; saved ZAP and OpenAPI import | `backend/source_adapters.py`, `Dockerfile` |
| Workflow | Five stages in LangGraph, parallel branches that merge before verification, deterministic fallback | `backend/graph.py`, `backend/offline_worker.py` |
| Model | Optional OpenRouter through a separate gateway, strict schemas, invalid citations rejected | `backend/model_gateway.py`, `backend/model_connections.py` |
| Memory | Six types, recovery checkpoints bound to owner, project, lease and digests | `backend/scan_memory.py`, [architecture](ARCHITECTURE.md) |
| Platform | Accounts, OIDC, RLS, outbox, Celery, GitHub App | `backend/platform_*.py`, `backend/personal_*.py`, [platform](PLATFORM.md) |
| Reports | HTML (ar, en), JSON, SARIF, PDF with embedded Arabic font, comparison, comments | `backend/report_pdf.py`, `backend/advanced_reporting.py` |
| Evaluation | Synthetic corpus (18 cases), reference corpus manifest, analyzer baseline | `backend/synthetic_evaluation.py`, `backend/corpus_evaluation.py`, `backend/analyzer_baseline.py`, [release](RELEASE.md) |
| Research | 72 competing tools, benchmark survey | [competitors](research/competitors.md), [benchmarks](research/benchmarks.md) |

Open items inside P07: failure and recovery acceptance (crash after checkpoint, before publish), worker isolation acceptance with controlled egress, preflight reasons for unsupported files.

### P09 Live experience and report model

1. Live agent view. Shipped so far: the scan page lists the five roles with state, duration and tools used, from persisted `agent_done` events (`frontend/src/AgentLanes.jsx`). The model stage now has its own lane that shows Running while the one model request is in flight (`stage_start` then `agent_done`, written only by the current lease holder). Still open: events while the five analysis roles are running (they appear when the analysis step ends; the analysis runs in an isolated worker and takes milliseconds on small inputs), and per-tool progress. Target design: lanes for the five roles with state (waiting, running, done, skipped, failed), current task, tool in use, items done and remaining, elapsed time and evidence produced. Fed by persisted stage events with a cursor. Percentages only with a real denominator; stale data is shown as stale.
2. Frozen `ReportModel` per scan (section 7), rendered to web, Arabic and English text, PDF and SARIF. A cross-format test compares finding IDs, severity totals, evidence IDs and coverage.
3. PDF tests for shaping, mixed direction, long paths, many pages and selectable Arabic text.
4. Intake accepts drag and drop, file picker, paste and URL.

Done when: scan page shows each role live in a browser test, and the parity test passes in both languages.

### P10 Redesign: new UI/UX, fewer steps, more automation (now the current phase)

The owner asked for a radical redesign: easier flows, less manual work, more automation. It moves ahead of P20 and P19 in the order of work because it changes what every later feature looks like.

**Measured starting point (27 Nov 2026, personal mode, Arabic UI).** Counted from the scripted tour, after the account exists: New Project, type the project name, Create project, New scan, Continue to source, choose the file, Review scan, tick the permission, Submit, Open report. That is 10 user actions across 5 screens before the report opens. Target: 3 actions on one screen (drop the file, tick the permission, Start), with the project chosen automatically and the report opening when the scan ends.

**Principles.** One primary action per screen. Detect, do not ask: input type from the file, project from the last one used (or an automatic "My scans" project in personal mode). Defaults that are safe. Details on demand. Every state designed: empty, loading, partial, error, no permission, stale. Arabic first, RTL native, English complete. Severity is always a word as well as a color. Honest numbers only; a figure without a real denominator is not shown.

**Flows.**
1. Start: one "Scan" screen. A large drop zone (file, paste, GitHub or approved page URL tabs). On drop: input type detected, scope summary shown inline (what will and will not be read), one consent checkbox, one Start button. The consent checkbox, idempotency key and scope check stay; only the extra screens go.
2. Live: the five agents and the model lane as a pipeline with real events, elapsed time and what each produced; the page opens the report on completion (with a Stay option) and shows a plain error with a Retry on failure.
3. Report: first screen is the decision, not the table: counts by severity, the three things to fix first with the reason, coverage and what was not checked. Then findings, step-by-step mode, evidence, export menu (PDF, JSON, SARIF).
4. Dashboard: scans over time, new and fixed since the last scan (by finding fingerprint), freshness stamp on every number, each number traceable to its scan.
5. Automation backlog, in order: auto-open report (done, 4 s countdown with Stay); remember last project and input type; saved scan presets; one-click replay of a stored scan (P20); recheck after a fix (P11); scan on push for a connected repository.

**Design system.** Tokens first (color, type scale, spacing, radius, elevation, motion with reduced-motion respected), built on the existing dark and light themes, with the blueprint palette. Components get one definition each: button, field, card, status chip, severity chip, lane, empty state, toast. Pages are migrated one at a time so main stays shippable.

**Slices, each a small PR to main.** (a) tokens and shared components; (b) single-screen Scan flow; (c) live view and auto-open; (d) decision-first report; (e) dashboard; (f) landing and sign-in. After each slice: screenshots in Arabic and English, dark and light, and a before/after action count.

Done when: the 3-action flow passes the browser test in both languages, every route has screenshots in both languages and both themes, keyboard use works on the Scan, live and report screens, and each dashboard number reconciles with its scan records. Not claimed: any accessibility audit by a tool, unless one is run and recorded.

### P11 Recheck and history

Compare the original report with a recheck of the new revision under an equivalent scope. Outcomes: Fixed (comparable evidence eligible, check executed, result supports the fix), Still present, New, Changed, Inconclusive (missing input, eligibility or tool success), Needs review (conflicting or ambiguous identity). Missing coverage never yields Fixed. Done when the two-ZIP demo and a missing-file fixture give Fixed and Inconclusive.

### P12 Remediation

Recommendation from a validated finding, repair plan, owner approval bound to source digest, plan digest, permitted paths and expiry. Optional draft in an isolated worktree, trusted pre-vetted checks, review, reject or roll back. Deployment, push and merge are never automatic. Ships behind a flag, one labeled fixture first. States: Proposed, Awaiting approval, Approved, Sandbox created, Patch drafted, Testing, Ready for review, Completed; plus Rejected, Failed, Rolled back.

### P13 Help and report assistant

Committed by the owner. Scope, so it stays safe and useful:
1. Static bilingual help works with no provider.
2. The report assistant is read-only and bound to one project report. It classifies the question locally, retrieves redacted structured records (findings, evidence, coverage, recheck outcomes), and answers from them with citation IDs. A model may phrase the answer but receives only the approved projection and cannot add facts; every citation is validated against the report, otherwise the answer is dropped.
3. It abstains when no approved source matches, says so, and points to the nearest finding or help page.
4. Session-only memory by default; nothing persisted unless the owner opts in. It cannot start scans, change decisions, or touch other projects.
5. It is measured: a labeled question set with grounding, correctness and abstention scores, in both languages.

Done when: authorization, unsupported-question, invalid-citation and provider-down tests pass and the question set is scored.

### P14 Active verification (proposed)

For sites the owner proves they control (DNS TXT record or a file token): bounded, rate-limited, non-destructive probes for the largest taxonomy gaps (reflected XSS, SQL injection signals, open redirect, exposed files, CORS and header behavior, TLS, rate limit presence). Allowlist per probe, kill switch, full audit, safe by default. Findings enter the same evidence contract. Not started. Needs decision A.

### P15 Learning from past scans

The system improves from its own history without letting a model rewrite findings. Three loops, each off until measured on held-out data:
1. Ranking and confidence calibration. Owner decisions (accepted risk, false positive, fixed) and recheck outcomes become labels per rule and per finding fingerprint. A per-rule precision estimate (with a minimum sample size and a confidence interval) adjusts confidence and ordering, never the existence of a finding.
2. Project memory. Repeated fingerprints are recognized across scans; a decision the owner made earlier is offered again, marked as carried over, and expires when the evidence changes.
3. Corpus growth. Confirmed true and false positives (redacted, with consent) are added to the regression corpus so every rule change is scored against them.
Rule changes stay human-approved and versioned. Done when a replay on held-out scans shows the calibrated ranking beats the static one (or the result is reported as no gain) and nothing changes without a recorded version.

### P16 Performance and data design

Targets are set from a measured baseline, not guessed. Work: profile the scan path; incremental scans that skip files whose digest and rule versions are unchanged; cache artifact inventories and parsed manifests by digest; stream stage events instead of polling; parallel analysis branches within the worker budget; report and PDF rendering cached by report version; index review for every hot query (`EXPLAIN` evidence kept); schema review against [ERD](ERD.md): keys, constraints, retention, partitioning decisions for events and findings; load test with many projects and large archives, reporting p50 and p95 for queue wait, scan time and report time. Done when baseline and after numbers are recorded in the release notes and no regression test is slower than its budget.

### P17 Evaluation

Fixed test targets, same inputs for every configuration: (1) static checks only, (2) one agent with no tools, (3) multiple agents with no tools, (4) multiple agents with tools. Measure detection rate (share of labeled vulnerabilities found), false positives, duplicates, runtime and cost, and show the progression from 1 to 4. Targets: vulnerable apps and benchmarks listed in [benchmarks](research/benchmarks.md), plus at least 24 independently labeled holdout cases (12 clean, 12 positive) for the passive scope. Configurations (2) to (4) need a model provider; without one only (1) and the deterministic tool runs can be measured, and the report says so. Model: no paid spend is authorized (owner decision 27 November 2026), so agent configurations use one free OpenRouter model. Chosen from the live OpenRouter model list (`https://openrouter.ai/api/v1/models`, 13 free models on 27 November 2026): `nvidia/nemotron-3-ultra-550b-a55b:free`, the largest free model with tool calling, 1M context. The same model, prompts, temperature and token limits are used in configurations 2 to 4 and are recorded with the results. Free tiers are rate limited and the model can change or disappear, so every run stores the model ID, date and request log. Scoring unit: a labeled vulnerability is a (target file, taxonomy subdomain) pair. The 12-case reference corpus was written together with the checks, so a static score on it proves little; it stays as a regression set, and the headline numbers come from independent targets with a published vulnerability list (for example DVWA and OWASP NodeGoat source), labels mapped to taxonomy subdomains by two readers before any run.
Published comparisons with other systems use only their own published numbers, with source and benchmark version, and are marked as not like-for-like unless the same target and scoring are used. A zero or negative result is reported as is. Nothing is published before a run.

### P22 Self-security

Basira reads untrusted files and sends parts of them to language models, so it is itself a target. Work: run Basira on its own repository and fix real findings; tests where scanned content contains instructions aimed at the agents (the agents must treat it as data and never change tools, scope or output format because of it); review the key store (encryption, masking, no logging), the custom-provider URL checks at request time (DNS rebinding), upload limits and export paths; write the threat model in ARCHITECTURE. Done when the tests exist, pass and are part of CI.

### P23 Quality gates

Detection rate alone rewards noisy tools. Each evaluation run also records precision and false-positive rate per configuration; the one-agent run already flagged 5 of 13 fixed files, so this matters. A CI gate compares the stored baseline and fails on a drop; the evaluation script reproduces every published number from pinned inputs; flaky tests are fixed or quarantined with an owner.

### P24 Thesis and defense package

Deliverables: problem statement and scope; related work using the 72-tool survey; architecture and data design chapters; evaluation chapter with every limit stated (one labeler, one model, free-tier runs); ethics and authorization rules (active probing only for owner-proven targets); a usability check with five real users and their results; slides; the demo script from [DEMO.md](DEMO.md); a list of likely professor questions with evidence-backed answers. Done when a person who has not seen the project can follow the chapters and reproduce the numbers.

### P18 Hardening and release

Failure injection (crash at dispatch, after checkpoint, before publish), duplicate dispatch, stale lease, cancel; isolation with controlled egress; restore on a copied database with matching digests; Docker image and Compose verified on a real Docker host; merge ARCHITECTURE, PLATFORM and WORKSPACE into fewer topic files (translate if the owner asks); remove `/demo`, remaining organization keys and legacy report compatibility after a verified migration; release manifest with hashes and known limits; go or no-go record; rename if decided.

## 5. Architecture

```mermaid
flowchart LR
  U[Developer] --> W[React workspace]
  W --> A[FastAPI application]
  A --> P[(PostgreSQL)]
  A --> I[Intake and snapshot validation]
  P --> D[Outbox dispatcher]
  D --> Q[Redis]
  Q --> J[Celery worker]
  J --> X[Offline analysis]
  J --> P
  J --> G[Optional model gateway]
  A --> R[Report and PDF renderer]
```

The database is authoritative for work state and reports. The broker only transports jobs. A stale lease cannot publish. Provider calls happen after deterministic verification and receive a minimized projection.

| Concern | Decision |
|---|---|
| Web | React, Vite, Arabic and English, RTL and LTR, dark and light |
| API | Python 3.13, FastAPI, Pydantic; routes under `/api/platform` |
| Data | PostgreSQL 17, SQLAlchemy, Alembic, row-level security; SQLite only for the anonymous lab until it is removed in P18 |
| Jobs | Redis, Celery, transactional outbox, leases, bounded retries |
| Agents | LangGraph, five deterministic stages |
| PDF | fpdf2, uharfbuzz, embedded Arabic font |
| Deploy | Local lab, Docker Compose; pytest and Playwright |

ZIP limits: 2,000,000 bytes per archive, 8,000,000 expanded, 1,000,000 per file, 200 entries. Details: [architecture](ARCHITECTURE.md), [data model](ERD.md), [operations](PLATFORM.md), [workspace](WORKSPACE.md).

## 6. Agents, tools and memory

Five stages run in order. They are responsibilities, not model calls; queueing, auth, export, tool dispatch and proof validation are ordinary services.

| Role | Reads | Writes | Denied |
|---|---|---|---|
| Coordinator | Snapshot envelope, approved source identity, limits | Source kind, routing decision | Scope or digest mismatch |
| Planning | Source kind, artifact inventory, pinned policy and registry | Immutable tool selection with reason, expected coverage | Model-originated commands, network, installs |
| Analysis | Matched artifacts, allowlisted adapters | Candidate findings, per-tool status and coverage | Network, project code execution, writes |
| Verification | Artifacts, plan, candidates, results | Validated findings, evidence digest | Invalid scope, path, position or rule cannot publish |
| Reporting | Validated findings, scope, coverage | `ReportModel` and projections | Publishing a provisional result |

Role manifests carry ID, typed input and output, allowed tools, budgets, failure behavior and fixtures. The ten-role specialist catalogue (injection, authentication, authorization, API, client, infrastructure, file, business logic, remediation, coordinator) is a design target. A role is added only when it fills a named gap and beats the simpler alternative on held-out fixtures at equal budget.

Memory: working state (job service, cleared after terminal state), episodic (published scans and reports), procedural (versioned rules and tool registry), project (owner notes, never sent to a model by default), finding and review (fingerprints, human decisions separate), semantic (curated help, proposed), conversational (session only, proposed). Every record carries owner and project; the app authorizes before the query and at delivery; RLS is defense in depth.

Tools: each analyzer needs a registry entry, license review, pinned version and data, positive and negative fixtures, offline isolation, normalized output and partial-failure behavior. Semgrep CE and Trivy stay shadow-only.

## 7. Contracts

**ReportModel** (frozen at publication): `report_version`, scan ID, source and scope digests, policy version, tool manifest digest, state, timestamps, findings, evidence references, severity totals, coverage. Translated text is separate from the technical record. Old reports are read through a compatibility adapter; unknown legacy fields stay unknown.

**Coverage states:** registered, eligible, executed, matched or clear, skipped, error, requires context, not applicable. Only executed and eligible checks count as clear.

**Finding:** ID and fingerprint, project, scan, snapshot, title, category, severity (Critical, High, Medium, Low, Informational, with rationale), confidence (evidence strength, independent of severity), verification status, location, rule and tool versions, evidence references, fix, timestamps. Duplicates group by fingerprint and keep each original reference.

**Interaction modes** (stored with the scan): Manual (owner selects and submits), Ask (owner confirms the suggested plan), Agent (owner confirms scope, agents choose eligible checks). A new mode or broader scope is a new request.

**Screens:** welcome and sign-in, projects, project home and dashboard, new review, live scan, findings explorer and finding detail, report, recheck, remediation, help, settings. Each has empty, partial, failure and permission-denied behavior.

## 8. Acceptance

| Gate | Pass condition |
|---|---|
| A1 Scope and intake | Scan starts from a ZIP only after scope is confirmed; invalid archives rejected; a second account cannot read the scan, report or export |
| A2 Execution and evidence | Job ID survives reload; a tool timeout gives a partial report with explicit coverage; duplicate dispatch cannot publish twice |
| A3 Bilingual report | Arabic and English web and PDF match finding IDs, severity totals, evidence IDs and coverage; keyboard-only core flow |
| A4 Recheck | Original and repaired ZIP give Fixed; missing coverage gives Inconclusive |
| A5 Evaluation and handoff | Frozen manifest reproduces the comparison; test summary, digests, known limits and an isolated restore record attached |

Test layers: unit and contracts; database and API with two owners; worker and queue failure injection; browser (Playwright) in both languages; fix and regression; recovery and release. Unit and docs tests run with `npm test`.

## Graduation scope

What makes this graduation-worthy, in priority order: (1) live multi-agent view with real events (P09); (2) a measured four-configuration evaluation with honest numbers (P17); (3) recheck of a fix with Fixed and Inconclusive outcomes (P11); (4) learning from past scans, measured (P15); (5) cited report assistant (P13); (6) performance numbers (P16); (7) active verification for owned sites (P14, if approved); (8) patch draft on one fixture (P12). Items 1 to 3 and 6 are the core; 4, 5, 7 and 8 are added only when their phase gate passes.

## 9. Risks and limits

- Passive checks cannot find injection, XSS, IDOR or SSRF. Until P14 these stay listed as gaps.
- No accuracy is published. The synthetic corpus proves rule behavior, not real-world detection.
- Model-backed configurations in P17 need a provider key and budget; none is configured in the review environment.
- Docker has not been run in the review environment.
- The model is advisory only. It cannot add, remove or rewrite findings.
- Hosted or team use needs a separate design: tenant access, storage, cost and support.

## 10. Decisions

| ID | Decision | Status |
|---|---|---|
| A | Add the owner-verified active verification tier (P14), opt-in, runs only for an owner-verified target | decided 27 November 2026 (owner delegated the call; built in P14) |
| B | Rename the product from Marsad to Basira (بصيرة, insight): repo text, package, UI, docs, tests applied in one change; the GitHub repository is renamed after the change merges | decided 27 November 2026 (owner approved a rename; name chosen by the agent) |
| F | Report assistant stays in scope (owner decision 27 November 2026), read-only and cited | decided |
| C | One tracker, this file; blueprint and repository phase IDs retired | decided 27 November 2026 |
| D | Initial user is the individual developer, local first | decided |
| E | Patch drafting stays behind a flag until gates A3 and A4 pass | decided |

## 11. Conventions

- This file is the only tracker. Do not add phase notes elsewhere. Record shipped changes in `CHANGELOG.md`.
- IDs: phases `P01` to `P16`, gates `A1` to `A5`, decisions letters, rules keep their registry IDs (for example `WEB-05`, `INF-03`).
- Files: Python and docs use lowercase snake_case (`scan_contracts.py`) except `README`, `PLAN`, `CHANGELOG`, `LICENSE`; docs folders use lowercase kebab-case. Names describe what a file does, never when it was written. No phase numbers in file, function or variable names.
- Tests: `backend/test_<module>.py`; browser suites `tests/browser_<what>.py`; fixtures under `tests/fixtures/<what>/`.
- Environment variables start with `BASIRA_`.
- Generated files say so in their header and have a freshness test.
- Documentation language: English for new files; existing Arabic files stay Arabic until translated. The owner decides the language.
