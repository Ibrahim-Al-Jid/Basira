# Changelog

## 2026-11-27

### Changed
- The product is renamed from Marsad to Basira (بصيرة) in code, UI, docs, tests and fixtures; the reference-corpus manifest checksum was recomputed. Environment variables are now `BASIRA_*` and database roles `basira_*`; existing local setups must be recreated.

### Added
- Plan review: added P22 self-security, P23 quality gates (precision, not only detection), P24 thesis and defense package; P19 now names source-code analysis as the main coverage gap; order of work re-sorted by value for the demo.
- Provider adapters for OpenRouter, OpenAI, Anthropic and Google Gemini (`backend/llm_providers.py`): model listing, free/paid classification, cost warning text, chat request and response shapes, custom OpenAI-compatible provider with base-URL safety checks (https, no credentials, public addresses only), key masking. Not yet connected to the gateway or settings UI (P21).
- Detection experiment on DVWA (pinned commit, 13 vulnerable and 13 fixed files): static checks 0 of 13, one agent without tools 8 of 13 with 5 clean files flagged (free model, one run). Team configurations are coded but not run: free daily request cap. See `docs/research/detection-experiment.md`.
- Vulnerability taxonomy: 17 domains, 75 subdomains, 159 problems, mapped to CWE, OWASP Top 10:2025, OWASP API Top 10 2023 and WSTG. Served at `GET /api/taxonomy`; generated reference in `docs/taxonomy.md`.
- Research: `docs/research/competitors.md` (72 tools from public listings) and `docs/research/benchmarks.md`.
- Tests for taxonomy, markdown links and generated-doc freshness (251 backend tests pass).
- `docs/README.md`, the single documentation index.
- Scan page lists the five agents with state, duration and tools used, from persisted `agent_done` events.

### Changed
- One plan: `docs/PLAN.md` (product, current position, 18 phases P01 to P18, contracts, acceptance gates, decisions, naming conventions). It replaces the blueprint, the 19-phase plan and `work/plan.md`.
- Names: files, tests, fixtures and environment variables no longer carry phase numbers (for example `phase9_contracts.py` is now `scan_contracts.py`, `browser_phase13.py` is now `browser_personal_projects.py`, `BASIRA_PHASE13_QA_ORIGIN` is now `BASIRA_QA_ORIGIN`).
- README run instructions rewritten with a verification status for each method.

### Fixed
- `check_dockerfile` used `current_alias` before assignment.

### Removed
- `work/` folder (its content moved into `docs/PLAN.md`).
- All archive material: `docs/archive/` (old phase notes, the 19-phase plan, acceptance logs, consolidation notes) and the unused `docs/phase15-tools-baseline.json`. History stays in git.
- Stale remote branches. Only `main` remains.
