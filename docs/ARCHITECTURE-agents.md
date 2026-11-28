# Agent system design

Status: design. Section 1 describes what runs today and was checked against the code on 28 November 2026. Sections 2 to 10 are the target. Nothing in sections 2 to 10 is implemented unless stated.

## 1. What runs today

| Role (id) | Code | What it does |
|---|---|---|
| Maestro (`orchestrator`) | `backend/offline_worker.py` `orchestrate` | Decodes the envelope, routes the input kind, pins the source digest and trace id. |
| Scout (`planning`) | `plan` | Normalizes files, computes the inventory digest, resolves which checks apply. |
| Hunter (`analysis`) | `review_prepared` in `backend/artifact_review.py` | Runs the fixed check catalog (114 rules: 100 for HTML, HAR, configuration and dependencies and 14 for PHP, JavaScript and Python source), the OpenAPI and ZAP document rules, gitleaks and osv-scanner. |
| Auditor (`validation`) | `review` and `verify_evidence` | Checks coverage counts, that each line exists in its file, fingerprints, and tool versions. |
| Scribe (`reporting`) | `report` | Checks both summaries exist and projects the report. |

Facts that matter for the design:

- On the platform scan path the five roles are deterministic Python functions chained in LangGraph, and none calls a model. A second, separate implementation, the HTML demo graph in `backend/graph.py`, reuses the same role names and lets a model choose the layout and the order of check groups from element counts. README, the thesis pages and `docs/ARCHITECTURE.md` describe that demo graph, not the platform path. Step 2 of the order below removes the duplication. `ROLE_TOOLS` in `backend/scan_contracts.py` is an allow-list per role, enforced before each step.
- The only model call comes after analysis (`backend/model_gateway.py`). It receives rule ids, severities and counts, never source text or evidence, and its answer is validated against enums and the supplied evidence ids. It reorders priorities. It cannot add, remove or rewrite a finding.
- Memory today: a lease-protected checkpoint of the analysis, and review decisions (triaged, resolved, accepted) carried to a later scan of the identical source digest for the same owner within 90 days (`backend/scan_memory.py`).
- Inputs: ZIP, GitHub import, exact operator-approved HTTPS pages captured as HAR (at most 3 pages, passive), OpenAPI and ZAP files.
- Measured detection (`docs/research/detection-experiment.md`, 13 labeled DVWA modules): static checks found 8 of 13 and flagged 1 of 13 fixed files (a development score, the rules were written after reading these files). One agent without tools found 8 of 13 and flagged 5 of 13 fixed files. The team and team-with-tools configurations are coded in `backend/detection_agents.py` and have no result yet.
- `docs/ARCHITECTURE.md` describes an orchestrator that chooses split or combined analysis and an analysis role that compares local matches with model candidates. The code does neither. That page needs correcting when the first implementation PR lands.

## 1a. Names

The five roles have one stable id and one display name each. The id is what rows, events, contracts and tool allow-lists store, and it never changes, so existing data stays valid. The name is what the interface and the docs show. The registry is `backend/agent_roles.py`, and `backend/test_agent_roles.py` fails if the interface or the docs drift from it.

| Id (stored) | English | Arabic | Job |
|---|---|---|---|
| `orchestrator` | Maestro | المايسترو | Plans the run, sets budgets and routes work |
| `planning` | Scout | الكشّاف | Reads the whole project and maps it |
| `analysis` | Hunter | الصيّاد | Finds vulnerabilities with the rules, scanners and tools |
| `validation` | Auditor | المدقّق | Re-checks every finding against the evidence |
| `reporting` | Scribe | الكاتب | Writes the report from validated findings only |

The names avoid the membership roles (Owner, Admin, Analyst, Viewer), which the old "Analyst" label collided with.

## 2. Decision: hybrid

Deterministic rules and scanners are tools and evidence sources that agents call. Agents plan, read across files, propose candidates beyond the catalog, and reject weak ones. Rules alone cannot see a flaw spread across files or the absence of code (the missed DVWA cases). Agents alone produced false positives on fixed code and cannot be reproduced. The hybrid keeps rules as the baseline and as the validator's ground truth, and uses agents for coverage and judgment.

A finding is accepted only if it has evidence the validator can re-check without trusting the model: a file and line that exist in the pinned snapshot, or a captured request and response, plus either a rule id or a reproducible deterministic check. Everything else is rejected or sent to a human.

## 3. Roles

Each role has one job, a typed input and output, a tool allow-list, a step budget and a timeout. Roles exchange identifiers and schema-bound data, never free text that another role treats as instructions.

| Agent | Input | Output | Tools |
|---|---|---|---|
| Maestro | submission, policy, budget | `ScanPlan`: stages, per-agent budgets, stop conditions | envelope decode, router, budget ledger |
| Scout | normalized snapshot | `ProjectMap`: files and languages, entry points, routes, auth boundaries, dependencies, config, trust boundaries | list_files, read_file (bounded), manifest parsers |
| Hunter | `ProjectMap`, snapshot or captured evidence | `Candidate[]`: taxonomy id, location or request/response, evidence quote, hypothesis | rule catalog, gitleaks, osv, search_code, read_file, domain collector |
| Auditor | `Candidate[]`, snapshot | `Verdict[]`: accepted, rejected or needs_human, with the check that decided it | re-run rule, read_file, search_code, taint and context checks |
| Scribe | accepted findings only | report, bilingual summaries, per-finding remediation | remediation catalog, template |

Rules for the roles:

- The Auditor gets the candidate's evidence reference, not the Hunter's reasoning, and uses a separate prompt and context. It must re-derive the evidence itself.
- The Scribe can only describe accepted findings. It cannot create or promote one.
- The Maestro can repeat a stage or stop early inside the budget. It cannot widen scope, add tools, or open the network.

## 4. Schemas (summary)

- `ProjectMap`: `snapshot_sha256`, `files[{path, language, bytes}]`, `entrypoints[]`, `routes[{method, path, file, line, auth}]`, `dependencies[]`, `secrets_candidates[]` (locations only), `trust_boundaries[]`.
- `Candidate`: `id`, `taxonomy_id`, `rule_id?`, `location{path,line}` or `request_ref`, `evidence` (quoted text from the snapshot), `severity_proposed`, `hypothesis`.
- `Verdict`: `candidate_id`, `status`, `reason_code` (fixed enum), `checked_by` (tool id and version).
- `Finding`: an accepted candidate with its fingerprint, origins, and remediation.

All are pydantic models with `extra="forbid"`, as the gateway already does for advisor answers.

## 4a. Tool catalog

| Tool | Reads | Limit |
|---|---|---|
| rule catalog | normalized files | existing rule engine, versioned |
| gitleaks, osv-scanner | snapshot copy | fixed argv, no network, time and output caps (`backend/source_adapters.py`) |
| read_file | one file from the pinned snapshot | line window and byte cap |
| search_code | the snapshot | length-limited pattern, child process with a timeout (`search_lines`) |
| domain collector | DNS over HTTPS to one fixed resolver, TLS facts, a fixed set of well-known paths, certificate-transparency names | approved hosts and apex only, rate limited, public addresses only |
| remediation catalog | rule id and language | curated text |

An agent cannot call anything outside its allow-list. Every call is recorded as a task run with tool id, version, duration and result size.

## 5. Memory

| Kind | Content | Key |
|---|---|---|
| Working | the checkpoint of the current scan | scan id and lease |
| Project | `ProjectMap`, accepted and rejected candidate fingerprints with `reason_code` | org, project, snapshot digest |
| Episodic | earlier reports and review decisions | org, project, owner, 90 days |
| Procedural | rule catalog, tool registry, versions | global, read only |

Memory never crosses organizations or owners. A rejection reason is stored so the same false positive is not proposed again for an identical snapshot. Review decisions stay owner-scoped as they are today.

## 6. Validation loop

1. The Hunter emits candidates with evidence references.
2. The Auditor checks each: location exists, the quoted evidence is present at that location, the rule or deterministic check reproduces, and the context supports it (for example the value is user-controlled and reaches the sink, or the control is absent in the effective configuration).
3. Rejected candidates are counted and logged with a reason code. Needs-human candidates carry the assessment `review_required`, as in the current schema.
4. The Maestro may send rejected candidates back once, with the validator's reason code, if budget remains. Then it stops.

## 7. Budgets, failures, timeouts

- Each agent has a maximum number of tool calls, input and output tokens, and wall time. The Maestro holds the ledger.
- A model failure, an over-budget agent, or a schema-invalid answer drops that agent's output and the scan continues with the deterministic result. This is today's behavior and the floor: the hybrid can only add validated findings.
- A scan that cannot finish records which stage failed through the existing coverage statuses (`skipped`, `error`) with a fixed reason code, never a free-text model message.
- Background failures are logged with exception class and location only.

## 7a. Run modes

Every scan has one `analysis_mode`, chosen at scan creation. It is a closed enum, recorded on the scan and copied into the report contract, so a report always says how it was made.

| Mode | Value | What runs | Model needed | Reproducible |
|---|---|---|---|---|
| Rules only | `rules` | Today's deterministic path: rules, scanners and adapters, no model | No | Yes |
| Agents only | `agents` | Maestro, Scout, Hunter, Auditor and Scribe, with the rules not exposed as tools | Yes | No |
| Hybrid | `hybrid` | The same five roles, with the rules and scanners as the Hunter's tools and as the Auditor's ground truth | Yes | Rules part only |

Default is `hybrid`. If no model is configured or the model path fails, a hybrid scan completes as `rules` and the report says so in `mode_effective` and `fallback_reason` (a fixed code, never model text). An `agents` scan that cannot reach a model fails with a fixed error and does not silently fall back, because its result would then not be what the user asked for. A `rules` scan never calls a model. Scans created before this field read as `rules`.

Budgets are per mode and set by the Maestro: `rules` keeps today's limits; `agents` and `hybrid` carry maximum tool calls, input and output tokens and wall time per role. Over-budget output is dropped and the deterministic result stands (hybrid) or the stage is marked `error` (agents). The modes are also the benchmark configurations: `rules` is C1, `agents` is C2, `hybrid` is C4 in `docs/research/detection-experiment.md`.

Report contract fields: `analysis_mode` (requested), `mode_effective`, `fallback_reason` (nullable), `budget` (limits and use per role).

Selector copy (interface, Arabic and English, using the role names):

| Mode | English | Arabic |
|---|---|---|
| `rules` | Rules only. Fast and repeatable. No AI. | القواعد فقط. سريع وقابل للتكرار، بدون ذكاء اصطناعي. |
| `agents` | AI agents only. Maestro directs Scout, Hunter, Auditor and Scribe. Results can vary. | الوكلاء فقط. المايسترو يدير الكشّاف والصيّاد والمدقّق والكاتب. قد تختلف النتائج. |
| `hybrid` | Recommended. The agents use the rules as tools and Auditor checks every finding. Falls back to rules if the model is unavailable. | الموصى به. يستخدم الوكلاء القواعد كأدوات ويراجع المدقّق كل نتيجة. يعود إلى القواعد إذا تعذّر النموذج. |

### Phases and acceptance criteria

Each phase is one small PR. The DB agent owns migrations: the `analysis_mode` column, project and episodic memory tables, and agent run and step records, with row-level security and retention. This document owns the shapes below.

| Phase | Scope | Acceptance |
|---|---|---|
| P0 | This section | Docs test passes; names match `agent_roles.py` |
| P1 | `analysis_mode` setting, validation, contract fields, default `hybrid` with fallback to `rules` | Invalid value gives 422; old scans read as `rules`; hybrid without a model completes as `rules` with `fallback_reason`; contract round trip test |
| P2 (**done**, #148) | Deterministic `ProjectMap` (Scout): languages, entry points, routes, config files, dependency manifests, trust boundaries, keyed by snapshot digest | Same input gives the same map; map holds paths and counts only, no file bodies; unit tests on the sample projects |
| P3 (**done**, #150) | Auditor upgrade: location exists, quote present at the location, rule or deterministic check reproduces | Candidates with a missing file, line or quote are rejected with a reason code; the existing corpus recall does not drop |
| P4 | Bounded Hunter tool loop behind a flag, rules as tools | Mocked model only in tests; budget exhaustion keeps the deterministic result; injected text in a snapshot never changes tool calls |
| P5 | Interface selector and copy above | Both languages render; the selected mode shows in the report |
| P6 | Benchmark runner mapping modes to C1, C2, C4 using recorded responses | Reproduces the recorded scores without network |

`ProjectMap` shape (P2, data for the DB agent). This is the shape `backend/project_map.py` returns today; the fuller schema in section 4 is the target and gains fields as P3 and P4 land. Fields: `{digest, languages: {name: file_count}, entry_points: [path], routes: [{method, path, file}], config_files: [path], manifests: [path], boundaries: [{kind, file}]}`. Agent run record (P4): `{scan_id, role_id, status, steps, tokens_in, tokens_out, started_at, ended_at, reason_code}` where `role_id` is a stable id from section 1a.

## 8. Prompt-injection and output defenses

- Submitted code, comments, README text and captured responses are data. They are passed inside delimiters as bounded excerpts, redacted as today's evidence is, and the system prompt states that nothing inside them is an instruction. The existing test that places an "ignore the policy" note in a snapshot stays as a regression test and gains a model-backed case.
- Model output is parsed against schemas with enums and supplied evidence ids. Free text from a model never enters a report field that a person might trust as a rule title or remediation.
- Agents never receive keys, tokens, environment, or network access. Tools run in the existing isolated worker.
- The validator rejects any candidate whose location or quote is not in the pinned snapshot, whatever the model says.

## 9. Evaluation

A fixed benchmark scores every configuration on the same files:

- Targets: the pinned DVWA modules (vulnerable and fixed pairs), OWASP NodeGoat `app/` with labels added by a second reader, and clean samples from this repository.
- Configurations: C1 rules, C2 one agent, C3 team, C4 team with tools (existing harness), C5 the hybrid with a validator.
- Metrics: recall per taxonomy id, false positives on clean files, extra findings reviewed by a human, runtime, model calls, cost.
- Rule: a change ships only if C5 does not lower C1's recall or raise false positives on clean files. Labels from a single reader are marked as such. Quota limits (the free tier allows 50 requests a day) decide how fast C3 to C5 can be measured; paid usage needs the owner's approval.

## 10. Implementation order

1. Correct `docs/ARCHITECTURE.md` and land this design.
2. `ProjectMap` built deterministically, no model. Analysis consumes it for cross-file checks (include chains, route to handler, absent controls). Targets the cases the rules miss today.
3. Validator that re-checks context, not only structure, still deterministic. Adds reason codes.
4. Agent loop for the Hunter and the Auditor behind a flag, with the budget ledger and the deterministic fallback. Run C3, C4, C5 on the benchmark.
5. Domain collector as a tool for the site input, then per-subdomain findings, with the new rule groups and remediation text.
6. Report writer with per-finding remediation (before and after example and a verify step).
