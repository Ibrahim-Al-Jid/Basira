# 5. Ethics and authorization rules for scanning

## Rules

1. **Evidence the owner supplies.** Basira reviews files, captures and approved pages. It does not exploit anything.
2. **Active probing only for owner-proven targets.** The planned verification tier (P14, decided but not built) runs only when the owner proves control by a DNS TXT record or a file token. Probes are rate limited, non-destructive and allowlisted per probe, with a kill switch and full audit. It is opt-in and off by default.
3. **No scanning of third parties.** A scan of someone else's site without permission can be illegal in many jurisdictions. Today's passive intake only reads what the owner supplies or approves; any active probing will require ownership proof first (rule 2).
4. **Website collection is narrow.** One GET per approved public HTTPS page, at most three pages of one origin, redirects refused, internal addresses refused.

## Data handling

- Evidence in reports is redacted. Secrets found by Gitleaks are redacted fully.
- Uploaded sources are quarantined, checked by SHA-256, and the quarantine copy is deleted after verification. Retention is project policy.
- Provider keys are encrypted at rest and never shown back.

## Model use

- The model receives rule IDs, counts and reference labels, not file content, paths, secrets or account IDs.
- Before any non-free or unknown-price model is saved, the user must acknowledge the cost. Custom models are always treated as cost-unknown.
- The model is advisory and cannot add, remove or rewrite findings.

## Evaluation ethics

DVWA is intentionally vulnerable and licensed GPL-3.0, so its files are downloaded at run time and not committed. The usability check needs informed consent, no personal data beyond what the protocol lists, and the right to stop at any time ([usability_check.md](usability_check.md)).

## Honest reporting

Weak results are published: 0 of 13 for static checks, 5 of 13 clean files flagged by the one-agent run, C3 and C4 not run. A result is not rounded up, and a missing result is not replaced with an estimate.
