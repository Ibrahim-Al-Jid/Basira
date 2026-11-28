# Setup and run guide

Every command on this page was checked against `main` at commit `d24568c` on 28 November 2026 (Linux, Python 3.13.18, Node 22.23.5). The last section states what was not run, so nothing here is claimed beyond its evidence.

Related: [configuration](CONFIGURATION.md) for every environment variable, [API](API.md) for the HTTP surface, [troubleshooting](TROUBLESHOOTING.md) when a step fails, [PLATFORM.md](PLATFORM.md) for the Arabic operations notes and the ownership migration.

## Choose a mode

| Mode | What works | Needs | Accounts, projects, GitHub |
|---|---|---|---|
| 1. Local lab | `POST /api/run` HTML review (the `/demo` page only redirects), reports in SQLite, taxonomy and catalog endpoints | Python 3.13, Node 22 | no |
| 2. Windows local stack | Everything: accounts, projects, ZIP scans, GitHub App, PDF, dashboard | Mode 1 prerequisites, Docker Desktop, Git | yes |
| 3. Docker Compose (manual) | Same as mode 2, any OS | Docker Engine or Desktop with Compose, Git | yes |

All three serve the app at `http://127.0.0.1:8765` by default. Use `127.0.0.1`, not `localhost`: the GitHub callback and the session cookie are registered for that host.

## Prerequisites

- Python 3.13. 3.10 is not supported; a 3.10 run is not evidence (see the note in [RELEASE.md](RELEASE.md)).
- Node 22 and npm 10 or newer.
- Git.
- Docker Desktop (Windows, macOS) or Docker Engine with the Compose plugin (Linux) for modes 2 and 3.
- Optional: Windows PowerShell 5.1 or PowerShell 7 for `ops/start-local.ps1`.

## Mode 1: local lab

From the repository root. Use `.venv/bin/python` on macOS and Linux, `.\.venv\Scripts\python` on Windows.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix frontend ci
npm run build
npm start
```

The `/demo` page is retired; it opens the workspace when signed in and the sign-in page when not. Run a review through the API instead:

```bash
curl -N -X POST http://127.0.0.1:8765/api/run -H 'content-type: application/json' -d '{"source":"<form action=\"/x\"><input name=p type=password></form>"}'
```

`PORT` changes the port. `npm test` runs the backend suite through the same launcher.

Checks that should pass:

```bash
.venv/bin/python -m pytest backend -q            # 544 passed, 22 skipped on 28 Nov 2026
node --test frontend/src/replay.test.mjs frontend/src/dashboard.test.mjs   # 8 pass
```

`frontend/dist` must exist before the backend tests run: `backend/test_api.py` serves the built frontend. Build first, then test.

Reports and lab sessions live in SQLite at `data/basira.sqlite3`; `BASIRA_DB_PATH` moves it. Accounts and projects are not available in this mode.

## Mode 2: Windows local stack (accounts, projects, Connect GitHub)

One time per machine: install Docker Desktop and Git, then clone the repository.

1. Start Docker Desktop and wait until the engine reports it is running.
2. From the repository root in PowerShell, run the script once with the public identifiers of your GitHub App. It creates `.env.local` with random database passwords, generates the GitHub credential key and callback line, and asks for the Client Secret with hidden input:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\ops\start-local.ps1 -GitHubClientId <client id> -GitHubAppSlug <app slug>
```

3. Open http://127.0.0.1:8765/signin, create the local account, and press Connect GitHub.

Every later run: start Docker Desktop, run `.\ops\start-local.ps1`, open the same address.

Script parameters:

| Parameter | Default | Effect |
|---|---|---|
| `-Port` | `8765` | Port for the app. Writes `BASIRA_PORT` and the callback line. On later runs the value in `.env.local` wins. |
| `-GitHubClientId` | empty | Public client id, written only into empty lines. |
| `-GitHubAppSlug` | empty | App slug, used to build the install link. |
| `-Model` | off | Writes the four gateway settings with random values and starts the `model` profile. Also on when `BASIRA_PROJECT_MODEL_ENABLED=1` is already in `.env.local`. |

The script fills only empty lines, stops with a clear message when the credential key is malformed, and warns when the GitHub lines are incomplete. Without the GitHub lines the app still starts, but Connect GitHub is unavailable.

Stop with `docker compose -p basira-local down`. Data is kept. Add `-v` only when you intend to delete the database and the lab reports.

## Mode 3: Docker Compose (macOS, Linux, or Windows by hand)

1. Copy the template and fill the three password values with random letters and digits. They are part of PostgreSQL connection strings, so letters and digits only.

```bash
cp ops/platform.env.example .env.local
```

2. Start the stack:

```bash
docker compose -p basira-local -f compose.yaml -f compose.local.yaml --env-file .env.local up -d --build
```

3. Check the services and open the app:

```bash
docker compose -p basira-local ps -a
```

`migrate` runs Alembic and exits; `app`, `dispatcher`, `worker`, `scanner`, `db` and `broker` stay up. Then open http://127.0.0.1:8765/signin and choose "Create account" on a fresh install.

`.env.local` is read for every setting Compose forwards, including `BASIRA_LOG_LEVEL` and the two lab run limits `BASIRA_LAB_RUN_LIMIT` and `BASIRA_LAB_RUN_CONCURRENCY` (defaults `INFO`, `30` and `8`). Change a value there and re-run the `up -d` command; no image rebuild is needed for these three.

`compose.local.yaml` turns on personal projects, local password accounts and self sign-up, and mounts `./data` so the lab SQLite file survives a rebuild. Without it the email and password sign-in stays off.

### One command on Linux and macOS

`bash ops/start-local.sh` does steps 1 to 3 for you: it writes `.env.local` the first time (random passwords and a GitHub credential key; values already there are never overwritten), starts the local profile and waits until the app answers.

```bash
bash ops/start-local.sh                              # http://127.0.0.1:8765
bash ops/start-local.sh --port 9000 --model          # another port, with the model gateway profile
bash ops/start-local.sh --github-client-id <id> --github-app-slug <slug>
```

The script is not executable in the repository (mode 644), so run it with `bash`. Run here: `bash ops/start-local.sh --help` prints that usage, `--port 80` is refused with `--port must be between 1024 and 65535.`, and with no Docker engine it stops with `Install Docker and start it, then run this script again.` The stack itself was not started (no Docker in this environment).

Optional profiles:

```bash
# Model gateway (Account -> Model connection)
docker compose -p basira-local -f compose.yaml -f compose.local.yaml --env-file .env.local --profile model up -d --build

# GitHub App archive import for operator-assigned installations
docker compose -p basira-local -f compose.yaml -f compose.local.yaml -f compose.github.yaml --env-file .env.local up -d
```

## Model gateway

The gateway is a separate service that holds provider keys. It is optional: with no gateway the scan still finishes with local analysis.

1. Turn it on with `.\ops\start-local.ps1 -Model`, or by hand: set `BASIRA_PROJECT_MODEL_ENABLED=1`, `BASIRA_GATEWAY_URL=http://model-gateway:8001`, and random values for `BASIRA_GATEWAY_TOKEN` and `BASIRA_MODEL_DB_PASSWORD`, then start the `model` profile.
2. Open Account, then Model connection, choose the organization, paste the provider key and pick a model.
3. The page says which problem it found: gateway not set up, or gateway not answering. Both come from the same `reason` field in `GET /api/platform/account/model-connection`.

The gateway encrypts stored keys with a master key kept in the `model-secrets` volume. Losing that volume loses the stored keys, not the rest of the install.

## GitHub App

Two supported routes.

**Automatic (recommended on a workstation).** Run the helper with the project virtual environment and follow the page it opens:

```powershell
.\.venv\Scripts\python.exe .\ops\configure-local-github.py
```

It creates the app through a GitHub App manifest, receives the credentials and stores them in the local `data` folder, which is ignored by Git. Add `--port` when the app does not run on 8765, and `--manual` to paste credentials of an app you already created.

**Existing app.** Create the app once by hand, then pass its public identifiers to the start script as shown in mode 2. Required settings:

| Setting | Value |
|---|---|
| Callback URL | `http://127.0.0.1:8765/api/platform/github/callback` (use 127.0.0.1, and the same port as `BASIRA_PORT`) |
| Repository permissions | Contents: read-only. Metadata: read-only |
| User authorization | Expiring user tokens on |
| Installation | Only select repositories |

After the app is installed, open Settings, then GitHub, press "Connect GitHub" and confirm the authorization. A second repository that exists on GitHub but was not selected must not appear in Basira.

## Where the data lives

| Data | Location |
|---|---|
| Lab reports and sessions (SQLite) | `./data/basira.sqlite3`, or `BASIRA_DB_PATH` |
| Accounts, projects, scans, reports (PostgreSQL) | `database` volume |
| Queue | `redis` volume |
| Analysis spool | `spool` volume |
| Gateway master key | `model-secrets` volume |
| GitHub App manifest credentials | `./data` (ignored by Git) |

## Verification record (28 November 2026)

| Step | Command | Result |
|---|---|---|
| Install | `python -m venv .venv`, `pip install -r requirements-dev.txt` | ok, Python 3.13.18 |
| Frontend | `npm --prefix frontend ci`, `npm run build` | ok, Vite build 686 ms |
| Backend suite | `.venv/bin/python -m pytest backend -q` | 544 passed, 22 skipped, 8 subtests, 31.9 s |
| Frontend unit tests | `node --test frontend/src/replay.test.mjs frontend/src/dashboard.test.mjs` | 8 pass |
| App start | `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765` | `/`, `/demo`, `/signin`, `/projects`, `/api/taxonomy`, `/api/product` all 200 |

Not run in this environment, and therefore not claimed:

- `ops/start-local.ps1` (no PowerShell here). The script is read and its parameters are documented above, not executed.
- The Docker image build, `docker compose up`, and `tests/container_smoke.py` (no Docker here). An earlier acceptance record in [RELEASE.md](RELEASE.md) covers an earlier environment.
- The Playwright browser suites in `tests/` (they need a running stack with test data).
- Live provider calls to OpenAI, Anthropic or Gemini, and S3 or MinIO intake.

## The five agents

The interface shows these names; the id in the table is what rows, events and tool allow-lists store and never changes (`backend/agent_roles.py`).

| Id | Name | Arabic | Job |
|---|---|---|---|
| `orchestrator` | Maestro | المايسترو | Plans the run, sets budgets and routes work |
| `planning` | Scout | الكشّاف | Reads the whole project and maps it |
| `analysis` | Hunter | الصيّاد | Finds vulnerabilities with the rules, scanners and tools |
| `validation` | Auditor | المدقّق | Re-checks every finding against the evidence |
| `reporting` | Scribe | الكاتب | Writes the report from validated findings only |

## Backup and restore

Two scripts, both plain standard library plus the PostgreSQL client binaries.

```bash
# A dump plus a readability check; a corrupt archive fails here, not at restore time.
BASIRA_PLATFORM_MIGRATION_URL=postgresql://postgres@host/basira python ops/backup-platform.py --output-dir backups

# Dump, restore into a scratch database, then compare shape and posture between the two.
sh ops/verify_restore.sh
```

`ops/verify_restore.sh` compares two things and fails on any difference: shape (public tables, policies, functions, tables with row level security, and the `alembic_version` row) and posture (whether `basira_app` can delete from `users`, whether it can read `password_attempt_limits`, whether it can execute `basira_login_identity`, and how many definer functions PUBLIC may execute). The security posture is part of the backup here: a restore that drops a policy hands one tenant another tenant's rows and nothing in the application would notice.

Not run here: neither script was run in this environment (no PostgreSQL server or client). The behaviour above is read from the scripts and from the pull requests that added them (#82, #129).
