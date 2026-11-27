# 8. Likely professor questions

Each answer cites where the evidence is. Answer with the number and its limit, never only the number. If a question touches something not run, say "not run" and what would run it.

**1. Why did your static checks find 0 of 13?**
They inspect HTML, headers, manifests and configuration, not PHP application code. Injection, XSS and access control in source need source analysis. We ran it to measure the gap, and it is the largest one. Evidence: `research/detection-experiment.md` (C1). Next step: P19.

**2. What is your accuracy?**
No general accuracy exists and we do not claim one. On one pinned target (DVWA, 13 labeled files) the one-agent configuration found 8 of 13 and flagged 5 of 13 fixed files. n = 13, one run, one model, one labeler. Evidence: `evaluation.md` 4.1.

**3. Why do the multi-agent configurations have no result?**
The free tier allows 50 requests a day. C2 used 26 and a failed C3 attempt used the rest; C3 needs about 130 requests and C4 about 200. The code exists (`backend/detection_agents.py`). No paid spend is authorized. We report them as not run rather than estimating.

**4. Is this just a wrapper around an LLM?**
No. The deterministic engine (100 checks, evidence contract, validation) produces the findings and finishes without any model. The model is advisory: its reply is accepted whole or rejected whole and cannot add, remove or rewrite findings. A scan makes at most one model request (`MAX_MODEL_CALLS = 1`, `backend/model_connections.py`).

**5. What is "multi-agent" here, concretely?**
Five LangGraph nodes with role-limited tools and recorded runs: coordinator, planning, analysis, verification, reporting; analysis can branch in parallel and merge before verification. Whether more agents improve detection is exactly what C1 to C4 are meant to measure, and C3 and C4 are not yet run, so we do not claim that they do.

**6. How do you know the findings are real and not hallucinated?**
Findings come from the rule catalog with redacted evidence, line number and location; verification re-checks rule version, applicability, evidence and location. The model cannot create a finding. In the DVWA experiment, model findings are scored against labels, and the 5 flagged fixed files are exactly where this is unresolved.

**7. How do you handle prompt injection from scanned files?**
Design: scanned content is untrusted data, the model gets IDs and counts rather than file content, and the reply is validated whole. `backend/test_self_security.py` (56 offline tests) checks that injected instructions in file text, paths and evidence never reach the model request, and that a model that obeys an injection (unapproved tool, extra field, prose) is rejected and the report stays deterministic. Limit: tested with a fake model, not live models; CI wiring of the gate is P23.

**8. Why not use an existing tool such as Semgrep or an AI pentest agent?**
Semgrep and OSV-Scanner are in the design as pinned tools. The AI pentest agents in the survey act on live targets with exploit attempts, which is a different job and a different trust level. We do not claim to beat them. Evidence: `related_work.md`.

**9. Is it legal and ethical to scan?**
Basira reviews what the owner supplies and does not exploit. Active probing is planned only for targets the owner proves with DNS TXT or a file token, opt-in, rate limited, with a kill switch and audit. See `ethics.md`.

**10. What happens when the model provider fails during the demo?**
The scan completes with local analysis and says so. The runbook has a pre-run report and saved exports as fallback. A replay mode and a budget check are not built yet (P20). Evidence: `DEMO.md`.

**11. How does it cost? What if a student uses a paid model?**
Free OpenRouter models are the default. Saving a non-free or unknown-price model requires an explicit cost acknowledgement; custom models are always cost-unknown with a warning. No scan-level cost measurement exists yet; the cap is one request per scan.

**12. How do you protect API keys?**
Encrypted server-side, masked in the UI, never shown back. A stored key is refused for a different provider or address. Custom provider URLs must be https, public IPs only, checked again at request time. Offline tests cover URL checks (29 SSRF forms, DNS rebinding at every request, no followed redirects) and key handling (`backend/test_self_security.py`).

**13. What happens on a crash or duplicate job?**
Idempotency key per job, an outbox row in the same transaction as the job, a lease per attempt, and checkpoint writes only by the current lease holder. Failure-injection acceptance (P18) is planned and not run; do not claim it.

**14. Did Docker deployment work?**
Not verified. The same stack (PostgreSQL 17, Redis, API, dispatcher, worker, Chromium) ran without containers and passed the browser acceptance in Arabic and English. Docker has not been run in the review environment.

**15. Did real users test it?**
Not yet. A protocol with six tasks and SUS exists (`usability_check.md`). We will present results only from real sessions.

**16. What would you do with six more months?**
In order: source-code checks for PHP, JavaScript and Python (P19), precision and false-positive measurement with a CI gate (P23), independent holdout of 24 cases with a second labeler, run C3 and C4, recheck of a fix (P11), then owner-verified active probes (P14).

**17. Why Arabic?**
The reports and UI are bilingual (RTL and LTR, PDF in both), because the review output should be readable by the people who own the project. Most surveyed tools are English only according to our reading of the listings; this is a design choice, not a detection claim.

**18. What is the single result you want us to remember?**
A traceable review pipeline that works without a model, and an evaluation that reports its weak numbers honestly: static 0 of 13, one agent 8 of 13 with 5 of 13 false flags, multi-agent not yet run.
