# Changelog

## 2026-11-27

### Added
- Vulnerability taxonomy: 17 domains, 75 subdomains, 159 problems, mapped to CWE, OWASP Top 10:2025, OWASP API Top 10 2023 and WSTG. Served at `GET /api/taxonomy`; generated reference in `docs/taxonomy.md`.
- Research: `docs/research/competitors.md` (72 tools from public listings) and `docs/research/benchmarks.md`.
- Tests for taxonomy, markdown links and generated-doc freshness (251 backend tests pass).
- `docs/README.md`, the single documentation index.

### Changed
- One plan: `docs/PLAN.md` (product, current position, 16 phases P01 to P16, contracts, acceptance gates, decisions, naming conventions). It replaces the blueprint, the 19-phase plan and `work/plan.md`.
- Names: files, tests, fixtures and environment variables no longer carry phase numbers (for example `phase9_contracts.py` is now `scan_contracts.py`, `browser_phase13.py` is now `browser_personal_projects.py`, `MARSAD_PHASE13_QA_ORIGIN` is now `MARSAD_QA_ORIGIN`).
- README run instructions rewritten with a verification status for each method.

### Fixed
- `check_dockerfile` used `current_alias` before assignment.

### Removed
- `work/` folder (its content moved into `docs/PLAN.md`).
- All archive material: `docs/archive/` (old phase notes, the 19-phase plan, acceptance logs, consolidation notes) and the unused `docs/phase15-tools-baseline.json`. History stays in git.
- Stale remote branches. Only `main` remains.
