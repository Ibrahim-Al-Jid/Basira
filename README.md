<div align="center">

# Basira (بصيرة)

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
- **114 defensive checks.** A documented catalog of rules. The lab runs the ones that apply to HTML; projects also accept ZIP archives, HAR captures, and JSON snapshots.
- **Reports people can use.** Findings come with redacted evidence, line numbers, severity, and a fix. Export to HTML (Arabic or English), JSON, and PDF.
- **Model-optional by design.** Optional model enrichment is configured per account. If the provider fails, Basira completes the scan with local analysis instead of failing.
- **Bilingual UI.** Arabic and English, RTL and LTR, dark and light themes.
- **Project workspace.** Scan comparison, comments, finding statuses, and local accounts with email and password. OIDC sign-in is supported when a provider is configured.

## How it works

| Role | Input | What it does | Output |
|---|---|---|---|
| Maestro | Item counts and the previous scan of the session | Chooses one path or two parallel branches, using the model's decision when it is valid | Routing decision and its source |
| Scout | Routing decision and available rule groups | Accepts the model's ordering if it is complete, otherwise uses the local order | One or two analysis branches |
| Hunter | Properties extracted locally from the HTML | Matches rules from the catalog and compares model suggestions against the facts | Branch events and match status |
| Auditor | All local evidence matches | Confirms findings from the rule catalog and keeps every matching location | Findings with redacted evidence, line number, severity, and fix |
| Scribe | Confirmed findings, coverage, and fix guidance | Builds both summaries from a local template and accepts the model's priority order when it covers all matches | Saved report with HTML (both languages) and JSON export |

Working memory is the LangGraph state. Completed reports persist in SQLite, tied to the browser session profile; a session keeps its last 100 reports for 30 days.

## Run it

Two ways. Both serve the app at http://127.0.0.1:8765. The full guide, including the Windows script, Docker Compose, the GitHub App and the model gateway, is [docs/SETUP.md](docs/SETUP.md); this section is the short version.

### 1. Local lab (Python and Node, no Docker)

Needs Python 3.13 and Node 22. From the repo root (use `.venv/bin/python` on macOS and Linux, `.\.venv\Scripts\python` on Windows):

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm run build
npm start
```

Open http://127.0.0.1:8765/demo, choose an HTML file, paste markup, or use the built-in sample. Set `PORT` to change the port. Run the tests with `npm test`.

Verified on 28 November 2026 on Linux with Python 3.13.18 and Node 22.23.5, following exactly the commands above at commit `0438894`: the build succeeds (Vite, 444 ms), the app starts, `/`, `/demo`, `/signin`, `/projects`, `GET /api/taxonomy` and `GET /api/product` return 200, `python -m pytest backend -q` gave 443 passed and 19 skipped, and `node --test frontend/src/replay.test.mjs frontend/src/dashboard.test.mjs` gave 8 pass. The lab keeps reports in SQLite; accounts and projects need option 2. The Docker path and the Windows script were not run in that environment, and the [setup guide](docs/SETUP.md) says so per item.

### Run locally on Windows (accounts, projects, Connect GitHub)

One time per machine: install Docker Desktop and Git, then clone the repo.

1. Start Docker Desktop and wait for the engine to be ready.
2. From the repo root in PowerShell, run the script once with the public identifiers of your GitHub App. It creates `.env.local` with random passwords, generates the GitHub credential key and the callback line, and asks for the Client Secret with hidden input:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\start-local.ps1 -GitHubClientId <client id> -GitHubAppSlug <app slug>
```

3. Open http://127.0.0.1:8765/signin, create the local account, and press Connect GitHub.

Every later run: start Docker Desktop, run `.\ops\start-local.ps1`, open the same address. Stop with `docker compose -p basira-local down` (data is kept).

The GitHub App itself is created once by the project owner, with the callback `http://127.0.0.1:8765/api/platform/github/callback` (use 127.0.0.1, not localhost) and Contents read-only. The script fills only empty lines in `.env.local`, stops with a clear message if the credential key is malformed, and warns when the GitHub lines are incomplete. Without them the app still starts, but Connect GitHub is unavailable. Not verified end to end: Docker is not available in the review environment.

### 2. Docker Compose (accounts, projects, background jobs)

Needs Docker Desktop or Docker Engine with Compose. On Windows, one command does everything, including random passwords in `.env.local`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\start-local.ps1
```

On macOS and Linux, copy `ops/platform.env.example` to `.env.local`, fill the three `*_PASSWORD` values with random letters and digits, then:

```bash
docker compose -p basira-local -f compose.yaml -f compose.local.yaml --env-file .env.local up -d --build
```

Open the sign-in page and choose "Create account" on a fresh install. More detail is in the [platform guide](docs/PLATFORM.md).

Verification status: the Docker image build and these Compose commands have not been run in the review environment, which has no Docker. The same stack (PostgreSQL 17, Redis, API, dispatcher, Celery worker, Chromium) was run there without containers and passed the Personal projects browser acceptance in Arabic and English.

## Status

- Five LangGraph roles are implemented. The server analyzes HTML locally in the lab and stores reports in SQLite under the browser session name.
- The release catalog has 114 defensive checks. The extended lab runs the rules that apply to HTML. Projects also accept ZIP, HAR, and JSON snapshots, and add scan comparison, comments, finding statuses, and PDF (Arabic and English) export.
- Optional enrichment through Account → Model connection. The scan continues with local analysis if the provider is down.
- Detection quality is measured against a reference sample, and the project states plainly that there is no real-world data yet to measure general accuracy or model cost.

## Documentation

Start at the [documentation index](docs/README.md). The plan, phase status and pull requests are in [docs/PLAN.md](docs/PLAN.md), the [vulnerability taxonomy](docs/taxonomy.md) shows what Basira covers and what it does not yet, and the [thesis and defense package](docs/thesis/README.md) holds the written thesis, slides outline and prepared answers. For running it, read [setup](docs/SETUP.md) and [configuration](docs/CONFIGURATION.md); for the HTTP surface, [API](docs/API.md); when a step fails, [troubleshooting](docs/TROUBLESHOOTING.md).

## Credits

The entry page renders a planet with NASA-derived imagery shipped by the [three-globe](https://github.com/vasturiano/three-globe) package.
