<div align="center">

# Marsad (مرصد)

**A multi-agent security-review workspace for project files.**

Pick a project and an evidence source, follow the scan as it runs, and open a report in Arabic or English.

[العربية](README.ar.md) &nbsp;·&nbsp; English

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=flat-square&logo=langchain&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)

</div>

---

## Highlights

- **Five LangGraph agent roles.** A coordinator routes the work, then planning, analysis, verification, and reporting roles run it, with parallel branches that merge before verification.
- **100 defensive checks.** A documented catalog of rules. The lab runs the ones that apply to HTML; projects also accept ZIP archives, HAR captures, and JSON snapshots.
- **Reports people can use.** Findings come with redacted evidence, line numbers, severity, and a fix. Export to HTML (Arabic or English), JSON, PDF, and SARIF.
- **Model-optional by design.** Optional model enrichment is configured per account. If the provider fails, Marsad completes the scan with local analysis instead of failing.
- **Bilingual UI.** Arabic and English, RTL and LTR, dark and light themes.
- **Project workspace.** Scan comparison, comments, finding statuses, and local accounts with email and password. OIDC sign-in is supported when a provider is configured.

## How it works

| Role | Input | What it does | Output |
|---|---|---|---|
| Coordinator | Item counts and the previous scan of the session | Chooses one path or two parallel branches, using the model's decision when it is valid | Routing decision and its source |
| Planning | Routing decision and available rule groups | Accepts the model's ordering if it is complete, otherwise uses the local order | One or two analysis branches |
| Analysis | Properties extracted locally from the HTML | Matches rules from the catalog and compares model suggestions against the facts | Branch events and match status |
| Verification | All local evidence matches | Confirms findings from the rule catalog and keeps every matching location | Findings with redacted evidence, line number, severity, and fix |
| Reporting | Confirmed findings, coverage, and fix guidance | Builds both summaries from a local template and accepts the model's priority order when it covers all matches | Saved report with HTML (both languages) and JSON export |

Working memory is the LangGraph state. Completed reports persist in SQLite, tied to the browser session profile; a session keeps its last 100 reports for 30 days.

## Run it locally

**New Windows machine.** Start Docker Desktop, then run this from the repo root in PowerShell to open the projects edition with accounts:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\start-local.ps1
```

Open the [local sign-in](http://127.0.0.1:8765/signin) and choose "Create account" on a fresh install. Accounts and projects are stored in PostgreSQL on the machine that runs it. See the [platform guide](docs/PLATFORM.md) for manual setup and sign-in troubleshooting.

**Lab only**, in an isolated dev environment. Run these from the `sentinel` folder before starting anything else on port 8765:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm run build
npm start
```

Open the [lab](http://127.0.0.1:8765/demo), choose an HTML file, paste markup, or use the built-in sample. Extended mode is the default; switch back to basic with the scan scope field. Open reports from [lab reports](http://127.0.0.1:8765/reports?scope=demo) in the browser session that created them, or download HTML (Arabic or English) or JSON.

## Status

- Five LangGraph roles are implemented. The server analyzes HTML locally in the lab and stores reports in SQLite under the browser session name.
- The release catalog has 100 defensive checks. The extended lab runs the rules that apply to HTML. Projects also accept ZIP, HAR, and JSON snapshots, and add scan comparison, comments, finding statuses, and PDF (Arabic and English) and SARIF export.
- Optional enrichment through Account → Model connection. The scan continues with local analysis if the provider is down.
- Detection quality is measured against a reference sample, and the project states plainly that there is no real-world data yet to measure general accuracy or model cost.

## Documentation

Most project documents are written in Arabic.

| Document | Covers |
|---|---|
| [Implementation plan](work/plan.md) | Status of phases 1 to 12 with dependencies and acceptance criteria |
| [Architecture](docs/ARCHITECTURE.md) | Role responsibilities and limits, tools, memory types, technologies, research sources |
| [ERD](docs/ERD.md) | PostgreSQL schema as built and as targeted, relations, constraints, indexes, migrations |
| [Checks catalog](docs/CHECKS.md) | The 100 rules, when they apply, and references |
| [Platform guide](docs/PLATFORM.md) | Local accounts and OIDC, PostgreSQL and Redis, supported inputs, memory |
| [Release acceptance](docs/RELEASE.md) | Verification, evaluation, comparison limits, provider test result |
| [Project reference](docs/PROJECT.md) | Run paths, storage, acceptance log |
| [Workspace](docs/WORKSPACE.md) | Scan and report journeys, themes, tests |
| [Product expansion](docs/PRODUCT-EXPANSION.md) | Product journey, D01 to D18 classification, agent value evaluation plan |
