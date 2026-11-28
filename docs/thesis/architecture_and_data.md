# 3. Architecture and data design

This chapter summarizes [ARCHITECTURE.md](../ARCHITECTURE.md), [ERD.md](../ERD.md) and [PLATFORM.md](../PLATFORM.md), which are written in Arabic and stay the detailed source. If this chapter and those files differ, those files win.

## Two ways to run

- **Local lab**: FastAPI, React (Vite), LangGraph, SQLite. One command (`npm start`). Reports persist in SQLite tied to the browser session; a session keeps its last 100 reports for 30 days.
- **Platform**: adds local accounts and OIDC, PostgreSQL with row-level security, Redis and Celery (outbox, leases, idempotent jobs), a separate analysis worker, optional S3-compatible storage, and personal projects. The full stack (PostgreSQL 17, Redis, API, dispatcher, worker, Chromium) passed the personal-projects browser acceptance in Arabic and English without containers; the Docker image and Compose files were **not** run in the review environment.

## The five roles

The execution path is a deterministic contract of five LangGraph nodes: Maestro (`orchestrator`), Scout (`planning`), Hunter (`analysis`), Auditor (`validation`), Scribe (`reporting`). The identifiers in parentheses are stored in data and never change; see [agent system design](../ARCHITECTURE-agents.md). Each node is limited to the tools its role allows and records name, duration and role in `task_runs`.

| Role | What it does | Model's part |
|---|---|---|
| Maestro | chooses one path or two parallel branches from item counts and the previous scan | its decision is used only if valid |
| Scout | orders rule groups into one or two analysis branches | its order is used only if complete |
| Hunter | extracts properties locally and matches rules from the catalog | may suggest; compared against local facts |
| Auditor | confirms each matching finding from the catalog, keeps every location | none |
| Scribe | builds both language summaries from a local template | may reorder fix priorities if it covers all matches |

Design rule: **the model is advisory.** The server accepts a model reply whole or rejects it whole; on failure the scan completes with local analysis. The model gets rule IDs, counts, reference labels and allowed tool names, never file paths, content, secrets or account IDs.

## Tools

Each tool adapter has an ID, version, allowed inputs, rule list, time, memory and output limits, and a success or failure signal. Versions are pinned and checked with `--version` before each run; a different version is refused. Gitleaks (full redaction) and OSV-Scanner (local mode, dependency resolution disabled) run with fixed commands.

## Memory

Working (LangGraph state plus a server checkpoint protected by a lease), episodic (past scans in PostgreSQL), semantic (reviewed reference records), procedural (tool registry and rules), project, and finding memory. User comments are treated as untrusted content.

## Data design

Key entities: accounts, projects (owned by an account), source snapshots (SHA-256 digest), scans, task runs, findings with evidence, reports, comments and status events. The scan job uses an idempotency key, an outbox row written in the same transaction as the job, and a lease per attempt, so a crash or duplicate dispatch cannot publish two results. See the ERD for tables and keys.

## Security design

- Ownership is checked on every project, scan, finding and report route.
- Provider keys are encrypted server-side and masked in the UI; a stored key is refused for a different provider or address. Custom provider URLs must be https on port 443, no credentials, public IPs only, and are checked again at request time.
- Website collection: one GET per approved public HTTPS page, at most three pages of the same origin, all resolved addresses checked before connecting, redirects refused.
- Scanned content is untrusted data. Self-security tests (P22) exist in `backend/test_self_security.py` (56 offline tests: injected instructions in scanned content, SSRF forms, DNS rebinding, key handling) and run with `npm test`. They test the design with fakes, not a live model; a threat model table is in the architecture file.
