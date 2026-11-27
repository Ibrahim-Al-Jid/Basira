# 2. Related work

Source: [research/competitors.md](../research/competitors.md), a snapshot taken on 27 November 2026 from three public listings, with raw rows in `research/competitors.json`. Nothing in it was run or tested by us. Benchmarks are in [research/benchmarks.md](../research/benchmarks.md).

## The field

The survey lists 72 tools: 20 open-source AI pentest agents, 46 commercial platforms and 6 classic free DAST tools. Findings from the listings:

- Almost all of it tests live targets with active probing and exploit attempts. 45 of 46 commercial platforms test web apps and 33 publish a price.
- Verification of findings ranges from a human reviewing every finding to none.
- Published benchmark scores are self-reported by each project. The listing's own source says none was independently reproduced.

Examples from the open-source list (stars and licence as listed on that date): Strix (74,375, Apache-2.0), Shannon (51,444, AGPL-3.0), PentAGI (33,688, MIT), PentestGPT (16,325, MIT). These are agents that attack running systems.

## Benchmarks and why most do not fit

OWASP Benchmark, XBOW validation benchmarks and CVE-Bench measure exploitation or synthetic scanner accuracy. The XBOW publisher itself says its set should no longer be used to measure offensive performance. Basira does a different job (passive review of supplied evidence), so exploit benchmarks measure the wrong thing. The fair measures are listed in `benchmarks.md`: per-check positive, negative and not-applicable cases (exists), a labeled corpus with independent ground truth (partly: DVWA), Juice Shop and WebGoat captures (not run), and with-and-without-model comparison (C1 vs C2 to C4, partly run).

## Where Basira differs

| Point | Typical AI pentest agent | Basira |
|---|---|---|
| Acts on | live target | files and captures the owner supplies |
| Exploits | yes | never |
| Finding backing | varies | redacted evidence, location, fix, check status |
| Without a model | usually no result | full deterministic scan |
| Languages | English | Arabic and English, RTL and LTR, PDF in both |

## Where Basira is weaker

- Narrower: classes needing live probing are gaps (41 of 75 taxonomy subdomains have no check).
- Detection on application source code is currently 0 of 13 on the DVWA PHP set.
- No independent benchmark result and no comparison with another system. If one is added it will use that system's own published numbers with source and version, marked not like-for-like unless the same target and scoring were used.
