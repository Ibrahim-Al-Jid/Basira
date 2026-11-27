# Changelog

## 2026-11-27

### Changed
- Plan: Release 1 is defined (P10 redesign, P20 replay, what is already merged, and a short P18 release checklist). The assistant (P13), recheck, remediation, learning, active verification, performance work and the full four-configuration evaluation are listed as future additions.
- The product is renamed from Marsad to Basira (بصيرة) in code, UI, docs, tests and fixtures; the reference-corpus manifest checksum was recomputed. Environment variables are now `BASIRA_*` and database roles `basira_*`; existing local setups must be recreated.

### Added
- Personal scan flow is shorter: the project step is skipped when a project is already chosen, and choosing or dropping a file opens the review step directly. From New scan to a started scan is now 4 actions (was 8); the report then opens by itself. Browser acceptance for personal projects updated and passing; other Playwright suites not re-run. Organization mode keeps the three-step flow.
- Scan page opens the report by itself 4 seconds after a scan you just submitted finishes, with a "Stay here" button (P10, flow automation). Scans opened from history do not redirect. Checked in a real browser (Arabic); the older Playwright suites were not re-run.
- Plan: P10 is now the redesign (new UI/UX, 10 user actions to 3, automation backlog, six PR slices) and moves ahead of P20 and P19. The order of work was reset by the agent as the owner delegated sequencing.
- Live model stage: the scan page shows a Model lane as Running while the single model request is in flight, then Done with its time and whether it used the model or fell back. Events are written only by the current lease holder (`record_stage`). The five analysis roles still appear when analysis ends.
- Provider-agnostic model settings (P21): the personal Settings page now has a provider dropdown (OpenRouter, OpenAI, Anthropic, Google Gemini, custom OpenAI-compatible with an https base URL), a model list with a free-only filter, and a required acknowledgement before saving a non-free or unknown-price model. The key stays encrypted and is never shown back. A stored key is refused for a different provider or address, so it cannot be redirected. Migration `platform_providers_0016` adds `provider` and `base_url`. Calls to Anthropic, Gemini and OpenAI were not made live; only OpenRouter was.
- Gateway functions for non-OpenRouter providers (`other_provider_models`, `other_provider_reply`): catalog and completion for OpenAI, Anthropic, Google and custom providers; no redirects, base URL checked on every request, key rejected gives 422, outage gives 503. Not yet reachable from the settings API (P21).
- Plan review: added P22 self-security, P23 quality gates (precision, not only detection), P24 thesis and defense package; P19 now names source-code analysis as the main coverage gap; order of work re-sorted by value for the demo.
- Report findings can be revealed one at a time for presenting: "Step-by-step view" with Next finding, Restart, Show all and keyboard control.
- Provider adapters for OpenRouter, OpenAI, Anthropic and Google Gemini (`backend/llm_providers.py`): model listing, free/paid classification, cost warning text, chat request and response shapes, custom OpenAI-compatible provider with base-URL safety checks (https, no credentials, public addresses only), key masking. Not yet connected to the gateway or settings UI (P21).
- Detection experiment on DVWA (pinned commit, 13 vulnerable and 13 fixed files): static checks 0 of 13, one agent without tools 8 of 13 with 5 clean files flagged (free model, one run). Team configurations are coded but not run: free daily request cap. See `docs/research/detection-experiment.md`.
- Vulnerability taxonomy: 17 domains, 75 subdomains, 159 problems, mapped to CWE, OWASP Top 10:2025, OWASP API Top 10 2023 and WSTG. Served at `GET /api/taxonomy`; generated reference in `docs/taxonomy.md`.
- Research: `docs/research/competitors.md` (72 tools from public listings) and `docs/research/benchmarks.md`.
- Tests for taxonomy, markdown links and generated-doc freshness (251 backend tests pass).
- `docs/README.md`, the single documentation index.
- Scan page lists the five agents with state, duration and tools used, from persisted `agent_done` events.
- CI (P22, P23): `.github/workflows/ci.yml` builds the frontend, then runs the backend tests and the quality gate on every pull request and push to main. The frontend build is needed: with `frontend/dist` missing `test_api.py` fails locally, with it built all 7 pass. Not yet seen running on GitHub.
- Self-security tests (P22): `backend/test_self_security.py`, 56 offline tests. Injected instructions in scanned file text, paths and evidence never reach the model request; a model that obeys an injection (unapproved tool, extra field, prose) is rejected and the report stays deterministic; custom-provider URLs are checked against 29 SSRF forms, numeric host spellings, DNS rebinding at every request and unfollowed redirects; stored keys are bound to organization and generation and absent from errors. Threat model table added to `docs/ARCHITECTURE.md`. Not yet in CI.
- Upload and export self-security tests (P22): `backend/test_upload_and_export.py`, 29 offline tests. Hostile ZIPs (escaping paths, symlink, encrypted flag, nested archives, compression bomb, 200-file and 8 MB limits, a size that lies), hostile JSON, secrets in file names, and HTML export of report text containing markup (escaped, CSP set, hostile report IDs give 404). Basira scanned its own 166 text files with the built-in checks: 0 findings, which proves little until P19 lands.
- Quality gate (P23): `python -m backend.quality_gate` measures precision, recall and false-positive rate and fails when any gets worse than `tests/fixtures/quality-baseline.json`. Measured today: reference corpus (mocked profile) precision 0.900, recall 0.900; DVWA static recall 0 of 13, precision undefined (no findings), 0 of 13 fixed files flagged. Flaky-test policy and run instructions in `docs/QUALITY.md`. Not yet in CI.
- Thesis and defense package (P24) in `docs/thesis/`: problem and scope, related work, architecture and data, evaluation with every limit, ethics, usability-check protocol (no users tested yet), slides outline and 18 prepared professor questions. RELEASE.md evaluation table corrected (HTML has 1 missed match: two scripts on one line are merged). README verification refreshed (Python 3.13, 284 tests, `/`, `/demo`, `/api/taxonomy` checked).
- Source-code security checks (P19): 14 new rules `SRC-01` to `SRC-14` for PHP, JavaScript/TypeScript and Python (SQL, command and code injection, XSS, open redirect, path traversal and include, unrestricted upload, CSRF, predictable tokens, SSRF, unsafe deserialization, template injection, cookie flags, disabled TLS verification), a new `source-code` analyzer and `source` domain, 13 taxonomy subdomains now backed by checks (44 of 75, was 34), ruleset `basira-static-3` with 114 rules. DVWA static detection goes from 0 of 13 to 8 of 13 with 1 of 13 fixed files flagged (development score, rules written after reading those files); 11 new tests. Details in `docs/checks/source-code.md` and `docs/research/detection-experiment.md`.

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
