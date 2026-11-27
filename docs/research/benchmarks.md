# Benchmarks for web vulnerability detection

Snapshot from public pages read on 27 November 2026. Each entry says what it is good for and what limits it.

| Benchmark | What it measures | Limits | Source |
|---|---|---|---|
| OWASP Benchmark (Java and Python, latest release v1.2) | Speed and accuracy of SAST, DAST and IAST tools on deliberately vulnerable, exploitable test cases, with scorecard generators | Synthetic. Java first. Does not show generalization to real applications | https://owasp.org/projects/benchmark |
| XBOW validation benchmarks (104 challenges, published 2024) | Black-box exploitation of web challenges from SQL injection to IDOR and SSRF | The publisher states the set is outdated and should no longer be used to measure offensive performance. Scores are CTF flags, not real findings | https://xbow.com/blog/benchmarks |
| CVE-Bench (40 critical-severity real CVEs, released 2025-03-31) | Whether an agent can exploit real web application CVEs | Exploitation, not detection. Per its paper the best framework resolved up to 13 percent in March 2025 | https://github.com/uiuc-kang-lab/cve-bench |
| Reinforced WAVSEP, SecurityShepherd and similar academic suites | Scanner true and false positives by vulnerability class, Youden index | Older targets. Results vary by scanner version | https://norma.ncirl.ie/9832/1/chetanyasharma.pdf , https://www.mdpi.com/2079-9292/11/19/2991 |
| SCAnME (2025) | Scanner comparison metrics and method | Method paper, not a dataset to run | https://link.springer.com/article/10.1007/s10207-025-01054-8 |
| Vulnerable apps: Juice Shop, WebGoat, VulnerableApp, crAPI, VAmPI | Realistic targets for authorized live runs | Teaching apps. No ready ground truth per finding, needs manual mapping | https://vwad.owasp.org/ , https://github.com/vavkamil/awesome-vulnerable-apps |
| OWASP ASVS and WSTG | Coverage requirements and test methodology | Standards, not scorecards | https://asvs.owasp.org/ , https://wstg.owasp.org/ |

Found in search but not yet read: CTFExplorer (multi-target web CTF, arXiv 2602.08023), BountyBench, Red-MIRROR and AWE (agentic pentest papers).

## What fits Marsad

Marsad is a passive, evidence-based reviewer, so exploit benchmarks (XBOW, CVE-Bench) measure a different job. Fair measures for it:

1. Per-check positive, negative and not-applicable cases, which the test suite already holds for the 100 shipped checks.
2. A labeled corpus of real repositories and HAR captures with independent ground truth, split by language and CWE, scored with precision, recall, F1 and false-positive density.
3. Juice Shop and WebGoat captured as HAR plus source, only for the configuration and header classes Marsad claims.
4. Agent value: same checks with and without the model layer, same snapshots, same budget, with tokens, cost and p50 and p95 time.

Status: item 1 exists. Items 2 to 4 are not run. No accuracy number should be published until they are.
