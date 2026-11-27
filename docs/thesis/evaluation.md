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
| C1 | static checks only | 0 of 13 (0%) | 0 of 13 | 0 | run, 27 Nov 2026, 0.02 s |
| C2 | one agent, no tools | 8 of 13 (61.5%) | 5 of 13 | 26 | run, 27 Nov 2026, cost 0 |
| C3 | several agents, no tools | no result | no result | 6 of 26 cases completed | code written, run incomplete (daily cap) |
| C4 | several agents with tools | no result | no result | none | code written, not run |

Reading:

- C1 is zero because the 100 checks inspect HTML, headers, manifests and configuration, not PHP application code. This is expected and it is the measured proof of the gap that P19 targets.
- C2 finds most labeled issues but flags 5 of 13 fixed files. Some of those flags may be real residual issues rather than errors; the single labeler has not reviewed them. Precision and false-positive rate are therefore not yet established.
- C3 and C4 need about 130 and about 200 requests, more than the free daily quota. Options: several days, or credits, which the owner has not authorized.

Reproduce: `python -m backend.detection_experiment --config static` (downloads the pinned files and checks SHA-256 digests from `tests/fixtures/detection-targets/manifest.json`). C2 raw findings and request log: `docs/research/detection-runs/`.

## 4.2 Rule behavior on the synthetic corpus

`python -m backend.synthetic_evaluation` on `main` (27 November 2026, Python 3.13): 18 cases, 54 latency samples, p50 0.362 ms, p95 0.978 ms. Per-domain precision was 1.0 in every domain printed. The HTML domain shows recall 0.8 (4 true positives, 1 false negative): the case `two-insecure-assets` expects 2 `http-script` findings and gets 1. Acceptance notes in [RELEASE.md](../RELEASE.md) from an earlier run (20 November, 54 local samples, p50 0.84 ms, p95 2.28 ms) record no missed match, so this is a difference from that record and is being investigated, not hidden. Timings measure the analysis engine on small files, not a full scan with intake and database.

## 4.3 Tests

`npm test`: 284 passed, 1 skipped (27 November 2026). Browser suites (Playwright) exist for account, workspace, source intake, personal projects and release; only the personal-projects suite was re-run on 27 November in Arabic and English. Docker and Compose were not run.

## 4.4 What is not measured yet

| Item | Why it matters | Status |
|---|---|---|
| Precision and false-positive rate per configuration | detection rate alone rewards noisy tools | planned (P23) |
| 24 independent holdout cases (12 clean, 12 positive) | headline numbers must come from targets not written with the checks | not built |
| Second labeler | one reader is a validity threat | not done |
| C3, C4 | the progression from 1 to 4 is the core experiment | not run (P17) |
| Source-code checks for PHP, JavaScript, Python | closes the 0 of 13 gap | planned (P19) |
| Cost per scan with a model | a scan makes at most one request today | one request is the code limit; no cost measured |
| Usability with five users | research question 3 | protocol only |

## 4.5 Validity threats

Construct: scoring by (file, taxonomy subdomain) pair can credit a vague finding mapped to the right subdomain. Internal: single run, temperature 0, free model that can change or disappear (model ID, date and request log are stored with every run). External: DVWA is a teaching app, so results may not transfer to real projects. Conclusion: no statistics were computed because n = 13.
