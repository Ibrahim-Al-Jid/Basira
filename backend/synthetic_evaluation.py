"""Small, separately authored synthetic acceptance corpus for the released ruleset."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json
import math
import time

from .artifact_review import DOMAINS, catalog, defensive_review
from .model_gateway import apply_order


@dataclass(frozen=True)
class Case:
    name: str
    kind: str
    artifact: bytes
    expected: dict[str, int] = field(default_factory=dict)
    policy: dict = field(default_factory=dict)


def config(**files):
    return json.dumps({"files": files}).encode()


def har(headers, *, url="https://portal.example.test/login", mime="text/plain"):
    return json.dumps({"log": {"entries": [{
        "request": {"url": url, "method": "GET", "headers": []},
        "response": {"status": 200, "headers": [{"name": key, "value": value} for key, value in headers],
                     "content": {"mimeType": mime, "text": "acceptance fixture"}},
    }]}}).encode()


CASES = (
    Case("small-landing-page", "html", b"<main><h1>Support desk</h1></main>"),
    Case("plain-http-signin", "html",
         b'<form action="http://accounts.example.test/session"><label>Access<input name="pw" type="password"></label></form>',
         {"http-form": 1, "HTML-17": 1}),
    Case("aligned-signin", "html",
         b'<form method="post" action="https://accounts.example.test/session"><input name="pw" type="password"></form>'),
    Case("two-insecure-assets", "html",
         b'<main><script src="http://one.example.test/a"></script><script src="http://two.example.test/b"></script></main>',
         {"http-script": 2}),
    Case("quoted-settings-as-text", "html",
         b'<textarea><form action="http://other.example.test/"><input type="password"></form></textarea>'),
    Case("embedded-notes", "html", b'<iframe src="http://notes.example.test/show" sandbox></iframe>',
         {"HTML-07": 1}, {"base_url": "https://portal.example.test"}),
    Case("cookie-metadata-only", "har",
         har([("Set-Cookie", "qaid=har-fixture-value; Path=/")]),
         {"WEB-09": 1, "WEB-10": 1, "WEB-11": 1}, {"session_cookie_names": ["qaid"], "require_explicit_samesite": True}),
    Case("protected-cookie", "har",
         har([("Set-Cookie", "qaid=other-fixture-value; Secure; HttpOnly; SameSite=Lax; Path=/")]),
         policy={"session_cookie_names": ["qaid"], "require_explicit_samesite": True}),
    Case("custom-unsafe-referrer", "har", har([("Referrer-Policy", "unsafe-url")], mime="text/html"),
         {"WEB-07": 1}, {"har_headers_complete": True}),
    Case("npm-trust-strict", "config", config(**{".npmrc": "strict-ssl=true\n"})),
    Case("npm-trust-disabled", "config", config(**{".npmrc": "strict-ssl=false\n"}), {"DEP-09": 1}),
    Case("frozen-container-root", "config",
         config(Dockerfile="FROM python@sha256:" + "1" * 64 + "\nUSER 0\n"), {"INF-01": 1}),
    Case("frozen-container-user", "config", config(Dockerfile="FROM python@sha256:" + "2" * 64 + "\nUSER 1001\n")),
    Case("privileged-workload", "config",
         config(**{"deploy/pod.yaml": "apiVersion: v1\nkind: Pod\nspec:\n  containers:\n"
                 "  - name: service\n    image: example\n    securityContext:\n      privileged: true\n"}),
         {"INF-03": 1}),
    Case("pipeline-permissions", "config",
         config(**{".github/workflows/accept.yml":
                   "name: Acceptance\non: push\npermissions: write-all\njobs:\n  check:\n"
                   "    runs-on: ubuntu-latest\n    timeout-minutes: 90\n    steps: []\n"}),
         {"CI-02": 1, "CI-09": 1}, {"ci_max_job_timeout_minutes": 30}),
    Case("pipeline-bounded", "config",
         config(**{".github/workflows/accept.yml":
                   "name: Acceptance\non: push\npermissions: read-all\njobs:\n  check:\n"
                   "    runs-on: ubuntu-latest\n    timeout-minutes: 10\n    steps: []\n"}),
         policy={"ci_max_job_timeout_minutes": 30}),
    Case("application-settings", "config",
         config(**{".env.production": "DEBUG=true\nNODE_TLS_REJECT_UNAUTHORIZED=0\n"}),
         {"APP-04": 1, "APP-07": 1}),
    Case("minimal-settings", "config",
         config(**{".env.production": "DEBUG=false\nNODE_TLS_REJECT_UNAUTHORIZED=1\n"})),
)


def percentile(samples, p):
    return round(sorted(samples)[max(0, math.ceil(len(samples) * p) - 1)], 3)


def evaluate():
    index = catalog()
    domains = {row["id"]: row["domain"] for row in index["rules"]}
    per_domain = defaultdict(Counter)
    durations = []
    coverage = Counter()
    eligible = set()
    differences = []
    parity = True
    for case in CASES:
        report = None
        for _ in range(3):
            started = time.perf_counter()
            report = defensive_review(case.kind, f"fixture.{case.kind}", case.artifact, case.policy)
            durations.append((time.perf_counter() - started) * 1000)
        actual = Counter(row["rule"] for row in report["findings"])
        if dict(actual) != case.expected:
            differences.append({"case": case.name, "expected": case.expected, "actual": dict(actual)})
        for rule in set(actual) | set(case.expected):
            expected, matched = case.expected.get(rule, 0), actual[rule]
            domain = per_domain[domains[rule]]
            domain.update(tp=min(expected, matched), fp=max(0, matched - expected), fn=max(0, expected - matched))
        coverage.update(row["status"] for row in report["coverage"])
        eligible.update(row["rule"] for row in report["coverage"] if row["status"] in {"clear", "matched"})
        before = sorted((item["rule"], item["path"], item["line"], item["evidence"]) for item in report["findings"])
        apply_order(report, {"priority": list(reversed(actual))}, actual)
        after = sorted((item["rule"], item["path"], item["line"], item["evidence"]) for item in report["findings"])
        parity &= before == after
    summary = {}
    for domain in DOMAINS.values():
        tp, fp, fn = (per_domain[domain][metric] for metric in ("tp", "fp", "fn"))
        summary[domain] = {"tp": tp, "fp": fp, "fn": fn,
                           "precision": tp / (tp + fp) if tp + fp else None,
                           "recall": tp / (tp + fn) if tp + fn else None}
    return {"cases": len(CASES), "metric_unit": "finding counts per rule and fixture",
            "latency_samples": len(durations), "latency_ms": {
        "p50": percentile(durations, .50), "p95": percentile(durations, .95),
    }, "domains": summary, "eligible_rules": len(eligible), "coverage": dict(coverage),
        "evidence_parity_mock_priority": parity, "differences": differences}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
