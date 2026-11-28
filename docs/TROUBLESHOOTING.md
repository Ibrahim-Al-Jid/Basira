# Troubleshooting

Symptoms are grouped by where they appear. Each entry gives the cause and the check that confirms it. Related: [setup](SETUP.md), [configuration](CONFIGURATION.md), [API](API.md).

## Sign-in and accounts

| Symptom | Likely cause | Check and fix |
|---|---|---|
| The sign-in page says sign-in to projects is not available | `.env.local` has `BASIRA_PASSWORD_AUTH_ENABLED=0` (or the flag is missing) | `curl -s http://127.0.0.1:8765/api/platform/auth/options` should show `"password":true`. If not, set `BASIRA_PERSONAL_PROJECTS=1`, `BASIRA_PASSWORD_AUTH_ENABLED=1` and `BASIRA_PASSWORD_SELF_SIGNUP=1` in `.env.local` (`ops/start-local.sh` and `ops/start-local.ps1` do this on every run) and re-run `up -d` |
| No "Create account" option | `BASIRA_PASSWORD_SELF_SIGNUP=0` | Same `options` call must show `"registration":true`. `ops/start-local.*` sets it to `1` in `.env.local` |
| Sign-in works on one machine but the old account is rejected on another | Every install has its own PostgreSQL database | Create an account on the new machine, or move the PostgreSQL data |
| Password rejected at 12 characters or more | The password has leading or trailing spaces, or the account is rate limited after repeated attempts | Wait for the attempt window to pass, then retry. Register and login limits are separate |
| Session ends after 8 hours | By design (`SESSION_TTL`) | Sign in again. There is no refresh token |
| `404` on `/demo` or `/api/platform/organizations` while the stack is up | Personal projects are on, and those routes are deliberately closed in that mode | Use the project workspace |

## Docker and Compose

| Symptom | Likely cause | Check and fix |
|---|---|---|
| `docker compose up` fails on a missing `BASIRA_*` variable | The `:?Set ...` guard in `compose.yaml` fired | Pass `--env-file .env.local` and fill the three passwords |
| `db` keeps restarting | A password contains a character that breaks the connection string | Use letters and digits only, then `docker compose -p basira-local down` and up again. The database volume keeps the old password, so a changed password needs `down -v` on a fresh install |
| The app container exits and `migrate` failed | Alembic ran before the database was healthy, or the migration role cannot connect | `docker compose -p basira-local logs migrate`, then `ps -a` to see the exit code |
| Port 8765 already in use | The development server or another stack is running | Stop the other process, or set `BASIRA_PORT` in `.env.local` (and re-run `start-local.ps1 -Port` once so the callback line matches) |
| Connect GitHub missing after the stack starts | The GitHub lines in `.env.local` are empty or incomplete | `GET /api/platform/github/setup` returns the callback and install URL. If the install URL is null, `BASIRA_GITHUB_APP_SLUG` is missing |

## Scans and intake

| Symptom | Likely cause | Check and fix |
|---|---|---|
| `422` with an Arabic message on submit | Wrong file extension for the input kind, unacknowledged scope, or an unsupported kind for a personal project | Personal projects accept ZIP only. The English UI maps the common reasons; the raw reason is in the response `detail` |
| "The snapshot has no supported source files" | The ZIP contains only Markdown, images or other unscanned types | Include at least one supported source file (HTML, JS, TS, PHP, Python, config, manifests) |
| `415` on a ZIP upload | The request did not declare `application/zip`, `application/x-zip-compressed` or `application/octet-stream` | Send the file body with the right content type and `X-Artifact-Name` |
| `408` on a ZIP upload | The upload stalled past the 30-second window | Retry on a better connection |
| `429` on submit | The project has the maximum number of queued scans | Wait 60 seconds, or cancel a running scan |
| A scan sits at queued and never moves | The dispatcher or worker is not running, or Redis is unreachable | `docker compose ps -a`, then logs for `dispatcher` and `worker` |
| Coverage shows `adapter_output_limit` or `database_unavailable` | A static adapter hit its output limit or its offline database is missing | This is partial coverage, not a clean result. Check `BASIRA_SOURCE_ADAPTERS` and the image's `/opt/basira-osv` |
| A cancelled scan still writes a report | It cannot: a stale lease holder cannot publish after cancellation | If it happens, it is a defect. Record the scan id and the report id |

## Model gateway

| Symptom | Likely cause | Check and fix |
|---|---|---|
| Account, Model connection says the gateway is not set up (`reason: not_configured`) | `BASIRA_PROJECT_MODEL_ENABLED`, `BASIRA_GATEWAY_URL` or `BASIRA_GATEWAY_TOKEN` is missing | Run `start-local.ps1 -Model` once, or set the four values by hand and start the `model` profile |
| The gateway is configured but not answering (`reason: unreachable`) | The `model-gateway` service is not running, or the token does not match | `docker compose ps -a` for `model-gateway`, then compare `BASIRA_GATEWAY_TOKEN` on both sides |
| `422` when saving a key | The provider refused the key, or the base URL failed the safety check (must be https, public host, no credentials in the URL) | Re-check the key at the provider, and use a public https base URL |
| `503` from the gateway | The provider is down or rate limited | The scan still completes with local analysis. Retry later or pick another model |
| A non-free model will not save | The cost acknowledgement is required | Tick the acknowledgement. The free default path is an OpenRouter `:free` model |
| Stored keys disappeared after a rebuild | The `model-secrets` volume was removed | Save the provider key again. Nothing else is affected |

## Tests and local development

| Symptom | Likely cause | Check and fix |
|---|---|---|
| `test_api.py` fails with a missing file | `frontend/dist` is not built | `npm --prefix frontend ci && npm run build`, then run pytest |
| Backend tests fail in odd ways on Python 3.10 | The project targets 3.13 | Use 3.13. A 3.10 run is not evidence (see [RELEASE.md](RELEASE.md)) |
| `python -m backend.quality_gate` exits 1 with `REGRESSION` | Precision or recall dropped, or false positives rose, against `tests/fixtures/quality-baseline.json` | Read the printed numbers. Fix the regression. Never lower the baseline to pass; a lower number needs the owner's decision recorded in the plan |
| Quality gate cannot download DVWA files | The network is blocked | The offline corpus still runs. Use `--network` only where the pinned files can be fetched |
| Playwright suite cannot find the app | The suites expect `BASIRA_QA_ORIGIN`, default `http://127.0.0.1:8776` | Start a separate stack on that port with test data, or set the variable |

## Reports and exports

| Symptom | Likely cause | Check and fix |
|---|---|---|
| PDF has boxes instead of Arabic text | The embedded font failed to load | Rebuild the image or reinstall requirements; the font ships in `backend/report_fonts` |
| HTML export shows nothing | A strict Content-Security-Policy blocks inline scripts, by design | Open the report in the app, or use the JSON export |
| A blank page on an unknown URL, or on a project/report link | Fixed on 28 November 2026 (PR #52) | Update to current `main`. API routes still return JSON `404` |

## Where to look next

- `docs/RELEASE.md` for what was verified and what was not.
- `docs/PLATFORM.md` for the Arabic operations notes, the ownership migration and the S3 setup.
- `docs/QUALITY.md` for the gate numbers and the flaky-test policy.
