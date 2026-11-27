# Detection experiment

Question: what share of known vulnerabilities does each Basira configuration find on the same fixed targets? Method and status only; numbers appear here only after a recorded run. Code: `backend/detection_experiment.py`. Plan: P17 in [PLAN.md](../PLAN.md).

## Target

DVWA (Damn Vulnerable Web Application), pinned to commit `502ac150ce37c20ca6e04cab7c5ca959f315f2d0` (17 November 2026). Files are downloaded at run time and checked against the SHA-256 digests in `tests/fixtures/detection-targets/manifest.json`; they are not committed (GPL-3.0). 13 modules, each with two files: `low.php` (intentionally vulnerable, labeled with one taxonomy subdomain) and `impossible.php` (the project's fixed version, expected clean). 13 labeled vulnerabilities and 13 clean files.

Labeling limit: one reader. A second reader must confirm the labels before any headline use.

## Configurations

| Id | Configuration | Status |
|---|---|---|
| C1 | Static checks only (Basira's deterministic checks, real ZIP path) | run: 100 checks, then 114 with source-code checks |
| C2 | One agent, no tools | run |
| C3 | Several agents, no tools | code written, run incomplete (daily request cap) |
| C4 | Several agents with tools | code written, not run |

C2 to C4 use one free OpenRouter model, `nvidia/nemotron-3-ultra-550b-a55b:free`, with identical prompts and limits.

## Scoring

A vulnerability is found when a finding on its file maps through the taxonomy to the labeled subdomain. Clean files with any finding are false positives. Also recorded: runtime, extra findings on vulnerable files, number of requests.

## Results

C1, run 27 November 2026: 0 of 13 vulnerabilities found (0%), 0 findings in total, 0 of 13 clean files flagged, 0.02 s. This is expected: the 100 checks inspect HTML, headers, manifests and configuration, not PHP application code. It confirms the gap that [taxonomy](../taxonomy.md) lists for injection, XSS and access control, and is the baseline the agent configurations must beat.

C1 after P19 (114 checks, 14 of them source-code checks), run 27 November 2026 offline on the same 26 pinned files (digests verified, harness `run_static` unchanged): 8 of 13 vulnerabilities found (61.5%, was 0 of 13), 1 of 13 clean files flagged, 19 findings, 0.15 s. Found: exec, csrf, upload, sqli, sqli_blind, weak_id, xss_r, open_redirect. Missed: brute (D02.3, lockout is absence of code), fi (low.php only assigns `$_GET['page']`, the include is in another file), xss_d and authbypass (the vulnerable files contain only a comment, the flaw is elsewhere), xss_s (the unsafe output is in a different file). The one flag on a fixed file is `brute/impossible.php` line 67: `$user` is SQL-escaped and then written into HTML without encoding, which looks like a real residual XSS; the single labeler has not reviewed it. Caveat that matters: the rules were written after reading these same 26 files, so this is a development score, not an unseen-data score. Two checks outside DVWA: the 87 non-test source files of this repository raise 0 findings (not a proof of absence), and the 25 files of OWASP NodeGoat `app/` (commit `c5cb68a7084e4ae7dcc60e6a98768720a81841e8`, not used during development except to read it afterwards) raise 5 findings, all confirmed by reading the lines: three `eval(req.body...)`, one redirect from `req.query.url`, one request URL from `req.query.url`. NodeGoat's NoSQL `$where` injection is missed. No labels were made for NodeGoat, so no recall number is claimed for it.

C2, one agent without tools, run 27 November 2026 with `nvidia/nemotron-3-ultra-550b-a55b:free` (temperature 0, 3000 token limit): 8 of 13 vulnerabilities found (61.5%), 5 of 13 clean `impossible.php` files flagged. 26 requests, no errors, cost 0. Raw findings and the request log are in `detection-runs/`. Caveats: one run, one model, one reader for labels, so no confidence interval; some flags on `impossible.php` may be real residual issues rather than errors, which the single labeler has not reviewed. Runtime per case was tens of seconds because the model reasons before answering; no clean total was recorded because the run was resumed in pieces.

C3 and C4: the code exists (`backend/detection_agents.py`; three specialist agents plus a verification agent, with `search_code` and `static_review` tools in C4) but there is no result. The free tier allows 50 requests per day; the C2 run used 26 and failed retries of the C3 run used the rest. C3 completed 6 of 26 cases and its partial data is not reported. To finish: run `python -m backend.detection_experiment --config team` and `--config team-tools` with `OPENROUTER_API_KEY` set on a day with a fresh quota (about 130 and 200 requests are needed, so the free quota is not enough in one day; the options are several days, or the user deciding to add credits, which is not authorized).

## Other systems

No comparison is shown. When one is added it uses the other system's own published numbers, with source and benchmark version, and is marked not like-for-like unless the same target and scoring were used.
