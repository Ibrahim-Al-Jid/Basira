# Configuration and secrets

One template holds every setting: `ops/platform.env.example`. Copy it to `.env.local` at the repository root, fill the values, and pass the file to Compose. `ops/start-local.ps1` creates and updates the same file on Windows. `.env.local` is ignored by Git and by the Docker build context; it must never be committed.

Related: [setup](SETUP.md) for the commands, [API](API.md) for the endpoints these settings affect, [PLATFORM.md](PLATFORM.md) for the Arabic operations notes.

## Rules for values

- Database passwords are part of a connection string. Use letters and digits only, 24 to 128 characters (`BASIRA_MODEL_DB_PASSWORD` is checked by the start script; the others are not checked, so keep the same shape).
- Use a different value for each password. The stack has four database roles: `basira_app` (the application, row-level security applies), `basira_dispatch` (outbox only), the migration role, and `basira_model_gateway` (the gateway).
- Anything named `*_KEY`, `*_SECRET`, `*_TOKEN` or `*_PASSWORD` is a server-side secret: never in a report, a log line, a screenshot or a chat message.
- Empty means "off" for most settings. Where empty has a different meaning, the table says so.

## Application and runtime

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_PORT` | `8765` | Host port Compose publishes on `127.0.0.1`. The container always listens on 8000. |
| `PORT` | `8765` | Port for the development launcher (`npm start`). Not read by Compose. |
| `BASIRA_PLATFORM_DATABASE_URL` | none | Application connection string. Compose builds it from `BASIRA_DB_PASSWORD` with the `basira_app` role. |
| `BASIRA_PLATFORM_MIGRATION_URL` | none | Migration connection string, used by `ops/migrate-platform.py` and `ops/review-project-ownership.py`. |
| `BASIRA_REDIS_URL` | `redis://broker:6379/0` | Queue address. |
| `BASIRA_ANALYSIS_SPOOL` | `/srv/basira/spool` in Compose | Shared directory between the worker and the isolated scanner. |
| `BASIRA_SOURCE_ADAPTERS` | `gitleaks,osv-scanner` | Supplementary static adapters. Empty disables them; the report then shows the coverage they would have added as missing. |
| `BASIRA_OSV_DB_DIRECTORY` | `/opt/basira-osv` | Offline OSV database shipped in the image. Do not point it at a downloaded copy at runtime. |
| `BASIRA_ALLOW_INLINE_ANALYSIS` | unset | Development only. Runs analysis in the web process instead of the isolated worker. Never set this in a shared environment. |
| `BASIRA_LOG_LEVEL` | `INFO` | Level of the request access log (`DEBUG`, `INFO`, `WARNING`, `ERROR`). The log writes one line per request with a request id, the method, the path without its query string, the status and the duration, and the response carries the same id as `X-Request-ID`. |

## Accounts and projects

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_PERSONAL_PROJECTS` | `0` | Turns on accounts, projects and personal scans. `ops/start-local.*` writes `1` to `.env.local`; Compose passes it to the app, dispatcher and worker. |
| `BASIRA_PASSWORD_AUTH_ENABLED` | `0` | Email and password sign-in. `ops/start-local.*` writes `1`. |
| `BASIRA_PASSWORD_SELF_SIGNUP` | `0` | "Create account" on the sign-in page. `ops/start-local.*` writes `1`. Passwords need 12 or more characters; sessions last 8 hours; attempts are rate limited per account. |

OIDC is the alternative to local passwords, for a team install:

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_OIDC_ISSUER` | empty | Issuer URL. Must match the `iss` claim exactly. |
| `BASIRA_OIDC_CLIENT_ID` | empty | Client id. Must match the token audience. |
| `BASIRA_OIDC_CLIENT_SECRET` | empty | Client secret. |
| `BASIRA_OIDC_REDIRECT_URI` | `http://127.0.0.1:8765/api/platform/auth/callback` | Registered callback. Must match character for character, including the port. |
| `BASIRA_OIDC_STATE_SECRET` | empty | Random string, 32 characters or more, for the signed state cookie. |

## Model gateway

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_PROJECT_MODEL_ENABLED` | `0` | Lets scans use a model connection. `1` also makes the start script launch the `model` profile. |
| `BASIRA_GATEWAY_URL` | empty | Gateway address as seen from the app. `http://model-gateway:8001` inside Compose. |
| `BASIRA_GATEWAY_TOKEN` | empty | Shared secret between app and gateway. Random, independent of every password. |
| `BASIRA_AGENT_LOOP` | `0` | `1` turns the agent path on: a repository or config scan with a model connection whose requested mode is `agents` or `hybrid` runs Maestro, Scout, the Hunter tool loop with the Auditor, and Scribe in the worker; Hunter findings appear in `report.agent_findings` and Scribe's summary in `report.agent_summary`. Every turn goes through the gateway `/chat` route, which holds the key and caps calls per scan. Off by default; with it off, every scan runs the rules. With it off, `hybrid` runs as `rules` with `fallback_reason: "agent_path_unavailable"` and `agents` is refused with 422. HTML, HAR, OpenAPI and ZAP inputs always run the rules. |
| `BASIRA_MODEL_DB_PASSWORD` | empty | Password for the gateway's database role. 24 to 128 letters or digits; the start script refuses anything else. |
| `BASIRA_MODEL_MASTER_KEY_FILE` | `/srv/basira/model-secrets/master.key` | Master key file that encrypts stored provider keys. Created by the `model-secrets` service. |
| `BASIRA_MODEL_DAILY_LIMIT` | unset | Overrides the per-model daily request cap. A `:free` model defaults to 50 requests a day; a paid model has no default cap. `0` blocks the model, a negative value means no cap. |
| `BASIRA_OPENROUTER_MODEL` | empty | Operator-managed fallback model id, used only for the organizations listed below. |
| `BASIRA_OPERATOR_MODEL_ORGS` | empty | Comma-separated organization ids allowed to use the operator fallback. |
| `BASIRA_OPENROUTER_SECRET_DIR` | none | Host directory holding `openrouter.key`, mounted read-only into the gateway by `compose.model.yaml`. |
| `BASIRA_OPENROUTER_KEY` / `BASIRA_OPENROUTER_KEY_FILE` | empty | The operator key itself, or a file that contains it. Prefer the file. |

Normal use is not the fallback: each account saves its own provider and key in Account, then Model connection, and the gateway stores it encrypted.

## GitHub

There are two separate GitHub paths. Do not mix their settings.

**Personal GitHub (Connect GitHub, read a user's repository).**

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_GITHUB_CLIENT_ID` | empty | Public client id of the GitHub App. |
| `BASIRA_GITHUB_APP_SLUG` | empty | App slug, used for the install link. |
| `BASIRA_GITHUB_CLIENT_SECRET` | empty | Client secret. Asked for with hidden input by the start script. |
| `BASIRA_GITHUB_CALLBACK_URL` | `http://127.0.0.1:8765/api/platform/github/callback` | Registered callback. Use `127.0.0.1` and the port in `BASIRA_PORT`. |
| `BASIRA_GITHUB_CREDENTIAL_KEY` | empty | Fernet key that encrypts stored GitHub credentials. 32 random bytes in URL-safe base64, ending in `=`. The start script generates it and refuses a malformed one. |

App settings on GitHub: Contents read-only, Metadata read-only, expiring user tokens on, install on selected repositories only.

**Organization archive import (operator-assigned installations).**

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_GITHUB_APP_ID` | empty | App id for the operator-managed installation. |
| `BASIRA_GITHUB_APP_KEY_PATH` | none | Host path to the app private key, mounted by `compose.github.yaml`. |
| `BASIRA_GITHUB_APP_KEY_FILE` | `/run/basira-source/github-app.pem` | Key path inside the container. Set by the compose file. |
| `BASIRA_GITHUB_INSTALLATIONS` | empty | Installation map the operator assigns to organizations. |

## Website evidence

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_APPROVED_WEBSITE_PAGES` | `{}` | JSON map of project id to a list of full HTTPS page URLs the owner approved, for example `{"project_id":["https://example.com/"]}`. Remove an entry when the approval is withdrawn. At most three pages per origin are fetched, one GET each, 250,000 bytes per response. |

## Intake storage

| Variable | Default | Effect |
|---|---|---|
| `BASIRA_INTAKE_S3_BUCKET` | empty | Private quarantine bucket. Empty means local temporary storage, which is development only. |
| `BASIRA_INTAKE_S3_ENDPOINT` | empty | Endpoint for MinIO or another S3-compatible store. |
| `BASIRA_INTAKE_S3_REGION` | `us-east-1` | Region passed to the storage client. |
| `BASIRA_INTAKE_S3_ACCESS_KEY_ID` / `BASIRA_INTAKE_S3_SECRET_ACCESS_KEY` / `BASIRA_INTAKE_S3_SESSION_TOKEN` | empty | Credentials for that bucket. Grant `s3:PutObject`, `s3:GetObject` and `s3:DeleteObject` on the `quarantine/` prefix only. |
| `BASIRA_INTAKE_STORAGE_REQUIRED` | `0` | `1` returns a retryable error when storage is unavailable instead of falling back to local disk. |

Apply `ops/intake-quarantine-lifecycle.json` to the bucket so abandoned uploads expire.

## Development and test only

| Variable | Effect |
|---|---|
| `BASIRA_EVAL_NETWORK` | `1` lets the evaluation and quality gate download the pinned DVWA files. CI sets it. |
| `BASIRA_REAL_ADAPTERS` | Runs the real Gitleaks and OSV-Scanner instead of fakes. |
| `BASIRA_QA_ORIGIN` | Origin for `tests/browser_smoke.py` and `tests/browser_personal_projects.py`. No default: the suite fails when it is unset. CI uses `http://127.0.0.1:8901`. |
| `BASIRA_TEST_URL` | Origin for `tests/browser_local_build.py`, default `http://127.0.0.1:8766`. CI uses `http://127.0.0.1:8901`. |
| `BASIRA_TEST_PLATFORM_URL` | Origin for the release suite and the suites that import it (account, workspace, password, source intake, compose release), default `http://127.0.0.1:8901`. |
| `BASIRA_BROWSER_CHANNEL` | Browser channel for the Playwright suites, for example `msedge`. |

## Checking a configuration

```bash
# Which sign-in options the running app offers
curl -s http://127.0.0.1:8765/api/platform/auth/options

# Whether the model gateway is configured and answering
curl -s -b "basira_session=<cookie>" http://127.0.0.1:8765/api/platform/account/model-connection

# Effective Compose configuration after .env.local is applied
docker compose -p basira-local -f compose.yaml --env-file .env.local config
```

`options` reports `password` and `registration` booleans, which is the fastest way to confirm that the three local flags in `.env.local` actually applied.

## Compose and these settings

`BASIRA_LOG_LEVEL` is forwarded to the `app` service in `compose.yaml`, so setting it in `.env.local` changes the running container. The values in the table are the defaults Compose substitutes when a variable is unset.

## Limits the gateway enforces

These are constants in `backend/model_gateway.py`, not settings; they exist because a provider address can be chosen by a user.

| Limit | Value | What it stops |
|---|---|---|
| `CATALOG_LIMIT` | 4 MiB | A provider catalogue response larger than this is refused instead of read into memory. |
| `REPLY_LIMIT` | 256 KiB | Same cap for a provider reply. |
| `ADVISOR_EVIDENCE_LIMIT` | 12 | More than twelve evidence items in an advisor request is rejected. |
| `ADVISOR_HINT_LIMIT` | 3 | More than three planning or validation hints is rejected. |
