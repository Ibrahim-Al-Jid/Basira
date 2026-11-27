# 4. Evaluation

Every number below was recorded in this repository. Source files are named for each one. Limits come first because they decide what the numbers can support.

## Limits that apply to everything

- One labeler for the DVWA labels. A second reader must confirm them before any headline use.
- One model (`nvidia/nemotron-3-ultra-550b-a55b:free`, temperature 0, 3000-token limit), one run per configuration, so no confidence interval.
- Free tier: 50 requests per day without credit. No paid spend is used.
- The 12-case reference corpus and the 18-case synthetic corpus were written together with the checks. They prove rule behavior, not real-world detection.
- No real-world accuracy figure exists.

## 4.1 Detection on DVWA (the independent target)

Target: DVWA pinned to commit `502ac150ce37c20ca6e04cab7c5ca959f315f2d0`. 13 modules, each with `low.php` (vulnerable, labeled with one taxonomy subdomain) and `impossible.php` (the project's fixed version, expected clean): 13 labeled vulnerabilities, 13 clean files. A vulnerability counts as found when a finding on its file maps through the taxonomy to the labeled subdomain. Source: [research/detection-experiment.md](../research/detection-experiment.md).

| Config | Description | Found | Clean files flagged | Requests | Status |
|---|---|---|---|---|---|
| C1 | static checks only, before source-code checks (100 checks) | 0 of 13 (0%) | 0 of 13 | 0 | run, 27 Nov 2026, 0.02 s |
| C1 | static checks only, after P19 (114 checks, 14 source-code) | 8 of 13 (61.5%) | 1 of 13 | 0 | run offline, 27 Nov 2026, 19 findings, 0.15 s; development score |
| C2 | one agent, no tools | 8 of 13 (61.5%) | 5 of 13 | 26 | run, 27 Nov 2026, cost 0 |
| C3 | several agents, no tools | no result | no result | 6 of 26 cases completed | code written, run incomplete (daily cap) |
| C4 | several agents with tools | no result | no result | none | code written, not run |

Reading:

- C1 was zero at first because the original 100 checks inspect HTML, headers, manifests and configuration, not PHP application code. That measured the gap. After 14 source-code checks (P19) it finds 8 of 13: exec, csrf, upload, sqli, sqli_blind, weak_id, xss_r, open_redirect. Missed: brute (lockout is absence of code), fi (the include is in another file), xss_d and authbypass (the vulnerable file holds only a comment, the flaw is elsewhere), xss_s (the unsafe output is in another file).
- **The rules were written after reading these same 26 files, so 8 of 13 is a development score, not an unseen-data score.** Treat it as proof that the gap closed on known cases, not as a detection rate.
- The one flag on a fixed file is `brute/impossible.php` line 67: `$user` is SQL-escaped and then written into HTML without encoding, which looks like a real residual XSS. The single labeler has not reviewed it.
- Outside DVWA: the 25 files of OWASP NodeGoat `app/` (commit `c5cb68a7084e4ae7dcc60e6a98768720a81841e8`, only read after development) raise 5 findings, all confirmed by reading the lines (three `eval(req.body...)`, one redirect and one request URL from `req.query.url`). NodeGoat's NoSQL `$where` injection is missed. No labels exist for NodeGoat, so no recall is claimed. The 87 non-test source files of this repository raise 0 findings, which is not a proof of absence.
- C2 finds most labeled issues but flags 5 of 13 fixed files. Some of those flags may be real residual issues rather than errors; the single labeler has not reviewed them. Precision and false-positive rate are therefore not yet established.
- C3 and C4 need about 130 and about 200 requests, more than the free daily quota. Options: several days, or credits, which the owner has not authorized.

Reproduce: `python -m backend.detection_experiment --config static` (current main gives the after-P19 row) (downloads the pinned files and checks SHA-256 digests from `tests/fixtures/detection-targets/manifest.json`). C2 raw findings and request log: `docs/research/detection-runs/`.

## 4.2 Rule behavior on the synthetic corpus

`python -m backend.synthetic_evaluation` on `main` after PR #28 (27 November 2026, Python 3.13): 18 cases, 54 latency samples, p50 0.404 ms, p95 1.029 ms (timings vary by machine and run). Precision and recall are 1.0 in every domain, and the matched, extra, missed counts are HTML 5/0/0, web 4/0/0, dependencies 1/0/0, infrastructure 2/0/0, CI 2/0/0, application config 2/0/0. The source-code domain is listed but has no cases in this corpus, so its metrics are empty.

History, kept because it is part of the evidence: before #28 the HTML domain showed 4 matched and 1 missed (recall 0.8). The case `two-insecure-assets` expects 2 `http-script` findings and got 1, because two scripts on the same line were merged into one finding (findings were de-duplicated by rule, file and line). It was the same on every run back to 21 November 2026, and the earlier acceptance table in [RELEASE.md](../RELEASE.md) (HTML 5 matched, 0 missed) had never matched the script output. #28 counts same-line findings from one tool separately and the RELEASE.md table is corrected. This corpus was written together with the checks, so a clean score here proves rule behavior, not real-world detection. Timings measure the analysis engine on small files, not a full scan.

## 4.3 Tests

`npm test`: 284 passed, 1 skipped (27 November 2026, earlier run; the later CI and agent-reported counts are in `docs/RELEASE.md`). Browser suites (Playwright) exist for account, workspace, source intake, personal projects and release; only the personal-projects suite was re-run on 27 November in Arabic and English. Docker and Compose were not run.

## 4.4 What is not measured yet

| Item | Why it matters | Status |
|---|---|---|
| Precision and false-positive rate per configuration | detection rate alone rewards noisy tools | planned (P23) |
| 24 independent holdout cases (12 clean, 12 positive) | headline numbers must come from targets not written with the checks | not built |
| Second labeler | one reader is a validity threat | not done |
| C3, C4 | the progression from 1 to 4 is the core experiment | not run (P17) |
| Source-code detection on unseen targets | the 8 of 13 was tuned on the files it is scored on | built and measured on DVWA and NodeGoat; no independent labeled set yet (P17, P19) |
| Cost per scan with a model | a scan makes at most one request today | one request is the code limit; no cost measured |
| Usability with five users | research question 3 | protocol only |

## 4.5 Validity threats

Construct: scoring by (file, taxonomy subdomain) pair can credit a vague finding mapped to the right subdomain. Internal: single run, temperature 0, free model that can change or disappear (model ID, date and request log are stored with every run). External: DVWA is a teaching app, so results may not transfer to real projects. Conclusion: no statistics were computed because n = 13.
