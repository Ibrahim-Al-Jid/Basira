# HTTP API reference

Basira serves its own API and the React app from the same origin. This page lists every operation the app exposes on `main` at commit `ccf076c` (28 November 2026): 72 operations on 54 paths. The OpenAPI schema at `/openapi.json` and the interactive page at `/docs` (served only when `BASIRA_API_DOCS=1`) are generated from the code and are the authority if this page ever drifts; see "Regenerate this list" at the end.

Related: [architecture](ARCHITECTURE.md), [configuration](CONFIGURATION.md), [data model](ERD.md).

## Conventions

| Topic | Behaviour |
|---|---|
| Base URL | `http://127.0.0.1:8765` locally. Every path below is relative to it. |
| Content type | JSON in, JSON out, except report downloads (HTML, JSON or PDF). |
| Platform session | `basira_platform_session` cookie, set by sign-in. HttpOnly, 8 hours, revoked on sign-out. |
| CSRF | A state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`) that carries an `Origin` header must match the app origin, otherwise `403`. |
| Idempotency | `POST /api/platform/projects/{project_id}/scans` requires an `Idempotency-Key` header, 8 to 100 characters. The same key returns the same scan instead of starting a second one. |
| Caching | API responses carry `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. |
| Errors | `{"detail": "..."}`. Server messages are Arabic; the UI maps the common ones to English. Validation errors add a `fields` list on the account endpoints. |

Error codes used by the platform API:

| Code | Meaning |
|---|---|
| 401 | No valid session. |
| 403 | Signed in, but the role does not allow the action, or the request origin is not the app. |
| 404 | The project, scan or report is not visible to this account. Also what the closed `/demo` and organization routes return when personal projects are on. |
| 408 | A ZIP upload was cut off or ran past its 90-second window. |
| 409 | Conflict, for example a repeated or stale scope version. |
| 415 | A ZIP upload that did not declare a ZIP content type. |
| 422 | Invalid input: wrong extension, unacknowledged scope, unsupported input kind for the project, unknown or unavailable `analysis_mode`. The message names the fields that failed (`الحقول: ...`), never their values. |
| 429 | Too many requests. For scans: the per-project limit of queued scans, or the evidence-capture limit (personal projects), was reached. For password sign-in and sign-up: too many attempts from one address or for one email from one address. Every 429 carries a `Retry-After` header in seconds (60 for scans). |
| 503 | Storage or queue unavailable; retry later. |

## Roles

Project access comes from the organization role, or from an explicit project grant. Actions map to roles as follows.

| Action | Owner, Admin | Analyst | Viewer |
|---|---|---|---|
| `read` (view project, scans, reports) | yes | yes | yes |
| `export` (download a report) | yes | yes | yes |
| `scan` (start or cancel a scan) | yes | yes | no |
| `finding` (review a finding, comment, change status) | yes | yes | no |
| `manage` (policy, members, grants, rename, delete, restore) | yes | no | no |

An account that is not a member and has no grant gets `404`, not `403`, so project existence is not disclosed.

## Public reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog` | The rule catalog: rules, tools, ruleset version. |
| GET | `/api/taxonomy` | The vulnerability taxonomy (17 domains, 75 subdomains, 159 problems) with CWE, OWASP and WSTG mapping. |


## Authentication and account

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/auth/options` | Which sign-in methods this install offers: `oidc`, `password`, `registration`. Public. |
| GET | `/api/platform/auth/login` | Start OIDC sign-in. |
| GET | `/api/platform/auth/callback` | OIDC callback. Must match `BASIRA_OIDC_REDIRECT_URI`. |
| POST | `/api/platform/auth/logout` | Revoke the session. |
| GET | `/api/platform/auth/me` | Current account and its memberships. |
| PUT | `/api/platform/auth/profile` | Update the display name. |
| POST | `/api/platform/auth/password/register` | Create a local account. Needs `BASIRA_PASSWORD_SELF_SIGNUP=1`. Password 12 characters or more. |
| POST | `/api/platform/auth/password/login` | Local sign-in. Needs `BASIRA_PASSWORD_AUTH_ENABLED=1`. Attempts are rate limited per account. |

## Account model connection

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/account/model-connection` | Read the stored provider, model and key state (never the key itself), plus `reason` when the gateway is not set up or not answering. |
| PUT | `/api/platform/account/model-connection` | Save provider, base URL, key and model. A non-free model needs the cost acknowledgement. |
| POST | `/api/platform/account/model-connection/models` | List that provider's models, with free and paid marked. |
| DELETE | `/api/platform/account/model-connection` | Remove the connection. |

## Organizations, members, invitations

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/organizations` | Organizations the account belongs to. |
| POST | `/api/platform/organizations` | Create one. |
| GET | `/api/platform/organizations/{org_id}/members` | List members and roles. |
| POST | `/api/platform/organizations/{org_id}/members` | Add or change a member. Manager only. |
| DELETE | `/api/platform/organizations/{org_id}/members/{user_id}` | Remove a member. Manager only. |
| GET | `/api/platform/organizations/{org_id}/invitations` | List invitations. |
| POST | `/api/platform/organizations/{org_id}/invitations` | Create a private invitation. |
| DELETE | `/api/platform/organizations/{org_id}/invitations/{invitation_id}` | Revoke one. |
| POST | `/api/platform/invitations/accept` | Accept an invitation as the signed-in account. |
| GET, PUT, DELETE | `/api/platform/organizations/{org_id}/model-connection` | Organization-level model connection (OpenRouter only). |
| GET, PUT, DELETE | `/api/platform/organizations/{org_id}/github-source` | Operator-managed GitHub App installation linked to the organization. Needs `compose.github.yaml`. |

## Projects

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/projects` | List projects. `?archived=true` lists deleted ones (owner only). |
| POST | `/api/platform/projects` | Create a project. |
| GET | `/api/platform/projects/{project_id}` | Project detail. |
| PATCH | `/api/platform/projects/{project_id}` | Rename. |
| DELETE | `/api/platform/projects/{project_id}` | Soft delete: hides the project and cancels running scans. |
| POST | `/api/platform/projects/{project_id}/restore` | Restore a soft-deleted project. Scans are not resumed. |
| POST | `/api/platform/organizations/{org_id}/projects` | Create a project inside an organization. |
| GET | `/api/platform/projects/{project_id}/dashboard` | Latest findings, severity split, coverage, change since the previous scan, 12-scan trend. Every number carries the scan it came from. |
| GET | `/api/platform/projects/{project_id}/grants` | Project grants. |
| POST | `/api/platform/projects/{project_id}/grants` | Add a grant. |
| DELETE | `/api/platform/projects/{project_id}/grants/{user_id}` | Remove a grant. |

## Scans and intake

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/projects/{project_id}/policy` | Current scan policy and its version. |
| PUT | `/api/platform/projects/{project_id}/policy` | Update policy. `expected_version` guards against a stale write. |
| GET | `/api/platform/projects/{project_id}/scan-profile` | Which inputs and rules apply, and the scope to acknowledge. |
| GET | `/api/platform/projects/{project_id}/technical` | Technical registry: rules, tools, adapter versions. |
| POST | `/api/platform/projects/{project_id}/intake/zip` | Upload a ZIP body and start a scan. Requires `Idempotency-Key`, `X-Artifact-Name` (the file name, `.zip`), `X-Scope-Version`, `X-Acknowledge-Scope: true`, and a ZIP content type. Optional `X-Model-Connection` and `X-Analysis-Mode` (`rules`, `agents` or `hybrid`; default `hybrid`). |
| POST | `/api/platform/projects/{project_id}/intake` | Start a scan from an approved remote source: a JSON body with `source` set to `github` or `website`, plus the scope version and acknowledgement. Requires `Idempotency-Key`. |
| POST | `/api/platform/projects/{project_id}/scans` | Start a scan from a JSON body. Requires `Idempotency-Key`. |
| GET | `/api/platform/projects/{project_id}/scans` | List scans. |
| GET | `/api/platform/projects/{project_id}/scans/{scan_id}` | Status. `?after=<event number>` returns events after that number, for live polling. |
| POST | `/api/platform/projects/{project_id}/scans/{scan_id}/cancel` | Cancel. A late worker attempt cannot publish after this. |
| GET | `/api/platform/projects/{project_id}/scans/{scan_id}/evidence` | Evidence records for the scan. |
| GET | `/api/platform/projects/{project_id}/scans/{scan_id}/provenance` | Source identity: repository, commit, digest, tool versions. |
| GET | `/api/platform/projects/{project_id}/github-source` | The project's connected repository. |
| POST | `/api/platform/projects/{project_id}/github-source/scans` | Import a snapshot from the connected repository and scan it. |


`POST /scans` takes `analysis_mode` in its JSON body: `"rules"`, `"agents"` or `"hybrid"` (default `"hybrid"`). A report records what was asked and what ran: `analysis_mode`, `mode_effective` and, when they differ, `fallback_reason`. The agent path runs only when `BASIRA_AGENT_LOOP=1`, the scan has a model connection and the input is a repository upload or a config file or bundle. Otherwise `hybrid` runs as `rules` with `fallback_reason: "agent_path_unavailable"`, and `"agents"` is refused with 422 (`وضع الوكلاء غير متاح لهذا الفحص`) instead of quietly becoming a rules scan. Places the Hunter found appear in the separate `agent_findings` list, each with `source: "agent"`, `assessment: "review_required"`, `rule`, `path`, `line` and a redacted `quote` the Auditor re-read in the snapshot. `agent_run` says how the agent run ended: `{status: "completed", phases}` or `{status: "fell_back", reason_code, phases}`. `reason_code` is `model_unavailable`, `model_error`, `invalid_output`, `budget_steps`, `budget_tool_calls`, `budget_tokens` or `budget_time`. `phases` has one entry per role, `{role, status, reason_code?}`: `role` is `maestro`, `scout`, `hunter` or `scribe`, `status` is `completed`, `fell_back` or `skipped`, and a phase `reason_code` can also be `not_planned` (Maestro dropped the role) or `empty` (Scribe had nothing to describe). When Scribe wrote a summary the report also has `agent_summary`: `{source: "agent", summary_en, summary_ar, cited}` (each summary up to 800 characters; `cited` lists the fact ids it described). It sits beside `summary_en` and `summary_ar`, is model-written and never replaces them. Each finding can carry `guidance` (`fix`, `fix_ar`, `verify`, `verify_ar`): fixed text from a rule table, never model output, with the first line of `fix` as the lead and the remaining lines as an example; it is absent for a rule with no entry and appears in the HTML and PDF exports. It is absent when the agent path never ran, and `mode_effective` stays what was decided at creation. Agent findings never enter `findings`, so rules results, fingerprints, comparisons and exports are unchanged. Reports written before run modes existed read as `rules` in both fields.

Submit a ZIP scan:

```bash
curl -s -X POST http://127.0.0.1:8765/api/platform/projects/$PROJECT/scans \
  -b "basira_platform_session=$SESSION" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"kind":"repository","name":"project.zip","content":"<base64>","scope_version":1,"acknowledge_scope":true}'
```

The response is `202` with the scan id. Then poll `GET .../scans/{scan_id}?after=0`.

## Reports

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/projects/{project_id}/reports` | Report history for the project. |
| GET | `/api/platform/projects/{project_id}/reports/{report_id}` | One report. |
| GET | `/api/platform/projects/{project_id}/reports/{report_id}/download` | `lang=en|ar`, `format=html|json|pdf`. HTML carries a strict Content-Security-Policy. |
| GET | `/api/platform/projects/{project_id}/reports/{report_id}/compare` | Compare with a baseline report. `?baseline=<32 hex>`. |
| GET, POST | `/api/platform/projects/{project_id}/reports/{report_id}/review` | Read or update a finding's review state and comments. Human review is stored separately from the technical finding. |
| GET | `/api/platform/projects/{project_id}/reports/{report_id}/link-candidates` | Evidence link candidates. |
| GET, POST | `/api/platform/projects/{project_id}/reports/{report_id}/links` | Read or create evidence links. |
| DELETE | `/api/platform/projects/{project_id}/reports/{report_id}/links/{link_id}` | Remove a link. |

## Project memory

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/projects/{project_id}/memory` | Project memory: notes, prior scans, rule history. Owner notes are never sent to a model by default. |
| POST | `/api/platform/projects/{project_id}/memory/knowledge` | Add a note. Title up to 160 characters, reference up to 500, note up to 2000. |
| DELETE | `/api/platform/projects/{project_id}/memory/knowledge/{note_id}` | Delete a note. |

## GitHub connection (personal)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/platform/github/connection` | Current connection state. |
| POST | `/api/platform/github/authorize` | Start the GitHub App authorization. |
| DELETE | `/api/platform/github/connection` | Disconnect. |
| GET | `/api/platform/github/repositories` | Repositories visible to the installation. |
| GET | `/api/platform/github/setup` | Callback and install URL for this install. Signed in; `404` when personal projects are off. |

## Regenerate this list

```bash
.venv/bin/python - <<'PY'
from backend.main import app
schema = app.openapi()
print(len(schema["paths"]), "paths")
for path in sorted(schema["paths"]):
    for method, op in sorted(schema["paths"][path].items()):
        print(method.upper(), path, "::", op.get("summary", ""))
PY
```

The count printed on `main` at `ccf076c` is 54 paths and 72 operations. `GET /openapi.json` returns the same schema from the running app, and `/docs` renders it when `BASIRA_API_DOCS=1`.
