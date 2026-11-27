# 1. Problem and scope

## Problem

A developer who wants a security review of a project today has three poor options. Manual review by an expert is slow and costly. Classic scanners produce long lists with little context and mostly test live targets. The newer AI pentest agents act on live systems with active probing and exploit attempts, which needs trust and authorization that a student or small team often cannot give. Most output is also English only.

Basira takes a narrower job: review **evidence the owner supplies** (a ZIP of the project, a GitHub snapshot, a HAR capture, configuration, a page the owner approved) and return findings a person can act on: redacted evidence, line number, severity, and a fix, in Arabic or English.

## Research questions

1. Can a set of cooperating agent roles around a deterministic rule engine give reviews that are traceable (every finding backed by evidence) and still useful when the model fails?
2. What share of known vulnerabilities does each configuration find on the same fixed targets: static checks only, one agent, several agents, several agents with tools? What does each cost in false positives and requests?
3. Can a person who did not build the system complete a scan and read the report without help? (Protocol in [usability_check.md](usability_check.md); not yet answered.)

## Scope (built)

- Intake: ZIP, GitHub App snapshot, approved website pages, HAR, ZAP and OpenAPI import.
- 100 defensive checks in six families (HTML, web headers and cookies, dependencies, infrastructure, CI, app configuration), reported as matched, clear, not applicable, skipped or error.
- Five LangGraph roles: Coordinator, Planning, Analysis, Verification, Reporting.
- Optional model enrichment, one request per scan at most (`MAX_MODEL_CALLS = 1`). The model is advisory: it cannot add, remove or rewrite findings.
- Reports in Arabic and English with HTML, JSON, PDF and SARIF export; scan comparison, comments, finding statuses.
- Taxonomy of 17 domains, 75 subdomains, 159 named problems, mapped to CWE, OWASP Top 10:2025, OWASP API Top 10 2023 and WSTG. 34 subdomains are backed by at least one shipped check; 41 are documented gaps.

## Out of scope, stated plainly

- No exploitation. No probing of systems the owner has not proven they control.
- Injection, XSS, IDOR and SSRF are gaps for passive checks. The measured proof is in [evaluation.md](evaluation.md): 0 of 13 on DVWA PHP source. Source-code checks (P19) and owner-verified active probes (P14) are planned, not built.
- No claim of better detection than any other tool. No head-to-head result exists.
- No real-world accuracy figure. Real-world data does not exist yet.
- Hosted or team use needs its own design (tenant access, storage, cost, support).

## Contribution, honestly sized

The contribution is the combination: an evidence contract that keeps findings traceable, a deterministic path that finishes without a model, bilingual reports, and a measured evaluation that reports its own weak result (0 of 13) instead of hiding it. It is not a new detection technique.
