# Changelog

## 2026-11-27

### Added
- Vulnerability taxonomy: 17 domains, 75 subdomains, 159 problems, mapped to CWE, OWASP Top 10:2025, OWASP API Top 10 2023 and WSTG. Served at `GET /api/taxonomy`; generated reference in `docs/taxonomy.md`.
- Research: `docs/research/competitors.md` (72 tools from public listings) and `docs/research/benchmarks.md`.
- Tests for taxonomy, markdown links and generated-doc freshness (251 backend tests pass).
- `docs/README.md`, the single documentation index.

### Changed
- One plan: `work/plan.md` now has 10 phases, regrouped from the original 19.
- README run instructions rewritten with a verification status for each method.

### Fixed
- `check_dockerfile` used `current_alias` before assignment.

### Removed
- All archive material: `docs/archive/` (old phase notes, the 19-phase plan, acceptance logs, consolidation notes) and the unused `docs/phase15-tools-baseline.json`. History stays in git.
- Stale remote branches. Only `main` remains.
