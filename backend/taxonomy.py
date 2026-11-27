"""Vulnerability taxonomy: domain > subdomain > problem, mapped to CWE, OWASP and Marsad rules.

Sources for the reference lists: OWASP Top 10:2025 (owasp.org/Top10/2025), OWASP API Security
Top 10 2023, OWASP WSTG 4.x chapters, and the 2025 CWE Top 25 (cwe.mitre.org).
`modes` says how Marsad can observe a problem today:
  artifact  - static review of files the user supplied (config, lockfiles, HTML, IaC, CI)
  capture   - passive review of a supplied HAR or header capture
  active    - needs authorized live probing; not implemented, not in the current scope policy
  manual    - needs human judgement
A subdomain with no `rules` is a documented gap, not coverage.
"""
OWASP_2025 = {
    "A01": "Broken Access Control", "A02": "Security Misconfiguration",
    "A03": "Software Supply Chain Failures", "A04": "Cryptographic Failures", "A05": "Injection",
    "A06": "Insecure Design", "A07": "Authentication Failures",
    "A08": "Software or Data Integrity Failures", "A09": "Security Logging and Alerting Failures",
    "A10": "Mishandling of Exceptional Conditions",
}
OWASP_API_2023 = {
    "API1": "Broken Object Level Authorization", "API2": "Broken Authentication",
    "API3": "Broken Object Property Level Authorization", "API4": "Unrestricted Resource Consumption",
    "API5": "Broken Function Level Authorization", "API6": "Unrestricted Access to Sensitive Business Flows",
    "API7": "Server Side Request Forgery", "API8": "Security Misconfiguration",
    "API9": "Improper Inventory Management", "API10": "Unsafe Consumption of APIs",
}
WSTG = {
    "INFO": "4.1 Information Gathering", "CONF": "4.2 Configuration and Deployment Management Testing",
    "IDNT": "4.3 Identity Management Testing", "ATHN": "4.4 Authentication Testing",
    "ATHZ": "4.5 Authorization Testing", "SESS": "4.6 Session Management Testing",
    "INPV": "4.7 Input Validation Testing", "ERRH": "4.8 Testing for Error Handling",
    "CRYP": "4.9 Testing for Weak Cryptography", "BUSL": "4.10 Business Logic Testing",
    "CLNT": "4.11 Client-side Testing",
}


def sub(id, name, cwe, owasp, wstg, modes, rules=(), api=(), problems=()):
    return {"id": id, "name": name, "cwe": list(cwe), "owasp_2025": list(owasp), "owasp_api_2023": list(api),
            "wstg": list(wstg), "modes": list(modes), "rules": list(rules), "problems": list(problems)}


DOMAINS = [
    {"id": "D01", "name": "Access control and authorization", "subdomains": [
        sub("D01.1", "Object-level authorization (IDOR/BOLA)", [639, 284, 862, 863], ["A01"], ["ATHZ"], ["active", "manual"], api=["API1"],
            problems=["Predictable object IDs", "Cross-tenant record reads", "Cross-account writes"]),
        sub("D01.2", "Function-level authorization and privilege escalation", [862, 863, 269], ["A01"], ["ATHZ"], ["active", "manual"], api=["API5"],
            problems=["Admin routes reachable by users", "Role parameter tampering", "Forced browsing"]),
        sub("D01.3", "Cross-site request forgery", [352], ["A01"], ["SESS"], ["artifact", "active"], ["APP-11"],
            problems=["State-changing request without anti-CSRF token", "CSRF protection disabled in framework"]),
        sub("D01.4", "Cross-origin resource sharing policy", [942, 346], ["A01", "A02"], ["CLNT"], ["capture", "artifact"],
            ["WEB-13", "WEB-14", "APP-10"], problems=["Credentialed CORS with wildcard or reflected origin", "Missing Vary on origin-varying responses"]),
        sub("D01.5", "Tenant isolation", [284, 863], ["A01"], ["ATHZ"], ["artifact"], ["INF-10"],
            problems=["Database row-level security absent or too broad"]),
        sub("D01.6", "Open redirect and unvalidated forwards", [601], ["A01"], ["CLNT"], ["active"],
            problems=["Redirect target taken from a parameter"]),
        sub("D01.7", "Mass assignment and object property exposure", [915, 213], ["A01"], ["INPV"], ["active", "manual"], api=["API3"],
            problems=["Client sets server-owned fields", "Responses include internal properties"]),
    ]},
    {"id": "D02", "name": "Authentication and identity", "subdomains": [
        sub("D02.1", "Credential entry and handling in forms", [598, 256, 549], ["A07"], ["ATHN"], ["artifact"], ["HTML-17", "HTML-18"],
            problems=["Password submitted via GET", "Password prefilled in markup"]),
        sub("D02.2", "Authentication over cleartext channels", [319, 523], ["A07", "A04"], ["ATHN", "CRYP"], ["capture"], ["WEB-22"],
            problems=["Basic authentication challenged over HTTP"]),
        sub("D02.3", "Brute force, lockout and credential stuffing", [307, 799], ["A07"], ["ATHN"], ["active"], api=["API2"],
            problems=["No rate limit on login", "No lockout or throttling"]),
        sub("D02.4", "Password policy and default credentials", [521, 1392, 798], ["A07"], ["ATHN", "IDNT"], ["active", "manual"],
            problems=["Weak password rules", "Vendor default accounts"]),
        sub("D02.5", "Multi-factor authentication and recovery flows", [308, 640, 620], ["A07"], ["ATHN"], ["active", "manual"],
            problems=["MFA bypass", "Weak reset tokens", "Password change without current password"]),
        sub("D02.6", "Account enumeration", [204], ["A07"], ["IDNT"], ["active"],
            problems=["Different responses for known and unknown users"]),
        sub("D02.7", "Federated login and token flows (OAuth, OIDC, SAML, JWT)", [347, 290, 1390], ["A07", "A08"], ["ATHN", "SESS"], ["active", "manual"], api=["API2"],
            problems=["Unsigned or weakly verified tokens", "Redirect URI and state mistakes"]),
    ]},
    {"id": "D03", "name": "Session management", "subdomains": [
        sub("D03.1", "Session cookie attributes", [614, 1004, 1275], ["A07", "A02"], ["SESS"], ["capture", "artifact"],
            ["WEB-09", "WEB-10", "WEB-11", "WEB-12", "APP-05", "APP-08"], problems=["Missing Secure", "Missing HttpOnly", "Missing or invalid SameSite", "Domain scope too wide"]),
        sub("D03.2", "Session lifecycle: fixation, expiry, logout", [384, 613], ["A07"], ["SESS"], ["capture", "active"], ["WEB-19"],
            problems=["Session ID not renewed at login", "Logout leaves state in the browser or server"]),
        sub("D03.3", "Session identifier strength", [330, 331], ["A04", "A07"], ["SESS"], ["active"], problems=["Predictable identifiers"]),
    ]},
    {"id": "D04", "name": "Injection", "subdomains": [
        sub("D04.1", "SQL and NoSQL injection", [89, 943], ["A05"], ["INPV"], ["active"], problems=["Unparameterized queries", "Operator injection in document queries"]),
        sub("D04.2", "OS command and code injection", [78, 77, 94, 95], ["A05"], ["INPV"], ["active", "manual"], problems=["Shell metacharacters reach a command", "Eval of user input"]),
        sub("D04.3", "Template and expression language injection", [1336, 917], ["A05"], ["INPV"], ["active"], problems=["Server-side template injection"]),
        sub("D04.4", "XML and parser attacks (XXE, XPath, LDAP)", [611, 643, 90], ["A05"], ["INPV"], ["active"], problems=["External entities enabled"]),
        sub("D04.5", "HTTP header and log injection", [113, 117], ["A05"], ["INPV"], ["active"], problems=["CRLF in headers", "Forged log lines"]),
    ]},
    {"id": "D05", "name": "Client-side security", "subdomains": [
        sub("D05.1", "Cross-site scripting", [79], ["A05"], ["INPV", "CLNT"], ["active", "manual"], problems=["Reflected", "Stored", "DOM-based"]),
        sub("D05.2", "Content Security Policy", [693, 1021], ["A02"], ["CONF", "CLNT"], ["capture"], ["WEB-02", "WEB-03", "WEB-04"],
            problems=["No enforcing policy", "unsafe-inline", "unsafe-eval"]),
        sub("D05.3", "Framing and clickjacking", [1021], ["A02"], ["CLNT"], ["capture"], ["WEB-05"], problems=["No frame-ancestors or X-Frame-Options"]),
        sub("D05.4", "Frame, window and sandbox isolation", [1022, 1021, 749], ["A02", "A06"], ["CLNT"], ["artifact"],
            ["HTML-10", "HTML-12", "HTML-13", "HTML-20"], problems=["Unsandboxed third-party iframe", "Opener retained", "Permissive sandbox", "Delegated sensitive features"]),
        sub("D05.5", "Document base and resource origin control", [829, 610], ["A02", "A03"], ["CLNT"], ["artifact"], ["HTML-15", "HTML-19"],
            problems=["base element redirects relative URLs", "Connection hints to third parties"]),
        sub("D05.6", "Cross-origin isolation policies", [346, 653], ["A02"], ["CLNT"], ["capture"], ["WEB-15", "WEB-16", "WEB-17"], problems=["COOP, COEP, CORP gaps"]),
        sub("D05.7", "Browser feature delegation", [250], ["A02"], ["CLNT"], ["capture"], ["WEB-18"], problems=["Permissions-Policy grants features to any origin"]),
        sub("D05.8", "Service workers and prototype pollution", [1321, 346], ["A06", "A08"], ["CLNT"], ["capture", "active"], ["WEB-24"],
            problems=["Service worker scope too broad", "Prototype pollution gadgets"]),
        sub("D05.9", "Cross-window messaging and storage", [345, 922], ["A06"], ["CLNT"], ["active", "manual"], problems=["postMessage without origin check", "Secrets in web storage"]),
    ]},
    {"id": "D06", "name": "Server-side requests and HTTP handling", "subdomains": [
        sub("D06.1", "Server-side request forgery", [918], ["A01"], ["INPV"], ["active"], api=["API7"], problems=["Fetch of user-supplied URL reaches internal hosts"]),
        sub("D06.2", "Host header and routing trust", [644], ["A02"], ["INPV", "CONF"], ["artifact", "active"], ["APP-09"], problems=["Host allowlist admits all hosts", "Password reset poisoning"]),
        sub("D06.3", "Request smuggling and desync", [444], ["A02"], ["INPV"], ["active"], problems=["Front-end and back-end disagree on message length"]),
        sub("D06.4", "Web cache poisoning and deception", [524, 525], ["A02"], ["CONF"], ["active"], problems=["Unkeyed input in cached responses"]),
        sub("D06.5", "Shared caching of private responses", [524, 525], ["A02", "A01"], ["CONF"], ["capture"], ["WEB-08"], problems=["Private response with public cache directives"]),
    ]},
    {"id": "D07", "name": "Cryptography and transport security", "subdomains": [
        sub("D07.1", "Mixed content and cleartext submission", [319, 311], ["A04"], ["CRYP"], ["artifact"],
            ["http-script", "http-form", "HTML-06", "HTML-07", "HTML-08", "HTML-09", "HTML-14"], problems=["HTTP scripts, styles, frames, media", "Forms posting to HTTP", "Meta refresh to HTTP"]),
        sub("D07.2", "HSTS and HTTPS redirects", [319, 523], ["A04", "A02"], ["CRYP", "CONF"], ["capture"], ["WEB-01", "WEB-23"], problems=["HSTS absent or zero", "HTTPS redirect ends on HTTP"]),
        sub("D07.3", "Certificate and TLS validation settings", [295, 297], ["A04"], ["CRYP"], ["artifact"], ["APP-07"], problems=["Certificate verification disabled in code or config"]),
        sub("D07.4", "Protocol versions, ciphers and certificates on a live host", [326, 327, 295], ["A04"], ["CRYP"], ["active"], problems=["Legacy TLS", "Weak ciphers", "Expired certificates"]),
        sub("D07.5", "Password hashing and key handling", [328, 916, 321, 330], ["A04"], ["CRYP"], ["manual"], problems=["Fast unsalted hashes", "Hardcoded keys", "Weak randomness"]),
    ]},
    {"id": "D08", "name": "Security misconfiguration and hardening", "subdomains": [
        sub("D08.1", "Hardening headers", [693, 16], ["A02"], ["CONF"], ["capture"], ["WEB-06"], problems=["No nosniff"]),
        sub("D08.2", "Version and technology disclosure", [200, 497], ["A02"], ["INFO"], ["capture"], ["WEB-21"], problems=["Server header exposes versions"]),
        sub("D08.3", "Debug and development settings in production", [489, 215], ["A02"], ["CONF"], ["artifact"], ["APP-04"], problems=["Debug mode enabled"]),
        sub("D08.4", "Exposed files, directories and admin interfaces", [548, 538, 527, 530], ["A02"], ["CONF", "INFO"], ["active"], problems=["Directory listing", "Exposed .git or backups", "Open admin consoles"]),
        sub("D08.5", "HTTP methods and default content", [749], ["A02"], ["CONF"], ["active"], problems=["TRACE, PUT enabled", "Sample apps left installed"]),
    ]},
    {"id": "D09", "name": "Sensitive data exposure and secrets", "subdomains": [
        sub("D09.1", "Hardcoded secrets and credentials", [798, 321, 259], ["A02", "A04"], ["CONF"], ["artifact"], ["APP-01", "APP-02", "APP-03", "APP-06"],
            problems=["Private key markers", "Provider token signatures", "Credentials in connection URLs", "Keystore passwords in clear text"]),
        sub("D09.2", "Leakage through referrers and third-party requests", [200, 359], ["A01", "A02"], ["INFO"], ["capture", "artifact"], ["WEB-07", "HTML-16"],
            problems=["unsafe-url referrer policy", "Hyperlink auditing pings"]),
        sub("D09.3", "Data in URLs, logs, comments and source maps", [598, 532, 615], ["A04", "A09"], ["INFO"], ["active", "manual"], problems=["Tokens in query strings", "Secrets in logs", "Source maps in production"]),
        sub("D09.4", "Excessive data exposure in APIs and error output", [213, 209, 200], ["A01", "A10"], ["ERRH", "INFO"], ["active", "manual"], api=["API3"], problems=["Responses return more fields than the client uses", "Stack traces"]),
    ]},
    {"id": "D10", "name": "Software supply chain and dependencies", "subdomains": [
        sub("D10.1", "Known-vulnerable components", [1395, 1104], ["A03"], ["CONF"], ["artifact"], ["DEP-01", "DEP-02", "DEP-16"], problems=["Direct match to a published advisory", "Transitive match", "Deprecated package"]),
        sub("D10.2", "Lockfile, version pinning and integrity", [494, 829, 1357], ["A03", "A08"], ["CONF"], ["artifact"],
            ["DEP-03", "DEP-05", "DEP-06", "DEP-08", "DEP-12", "DEP-14", "DEP-15"], problems=["No lockfile", "Floating versions", "Git dependency without commit", "SHA-1 only integrity", "Local path outside repo"]),
        sub("D10.3", "Registry trust, credentials and publishing", [295, 522, 494], ["A03", "A07"], ["CONF"], ["artifact"],
            ["DEP-04", "DEP-07", "DEP-09", "DEP-10", "DEP-11", "DEP-13"], problems=["HTTP registry", "Registry outside allowlist", "Certificate validation off", "Credentials in config or URLs", "Public publish allowed"]),
        sub("D10.4", "Subresource integrity for third-party assets", [353, 829], ["A03", "A08"], ["CLNT"], ["artifact"],
            ["cdn-integrity", "HTML-04", "HTML-05", "HTML-11"], problems=["CDN script or stylesheet without SRI", "Invalid digest", "Cross-origin SRI without CORS mode"]),
        sub("D10.5", "Dependency confusion and typosquatting", [427, 1357], ["A03"], ["CONF"], ["manual"], problems=["Internal package names resolvable from public registries"]),
    ]},
    {"id": "D11", "name": "Business logic and abuse", "subdomains": [
        sub("D11.1", "Workflow and state bypass", [841, 840], ["A06"], ["BUSL"], ["manual"], api=["API6"], problems=["Steps skipped", "Price or quantity tampering"]),
        sub("D11.2", "Race conditions and replay", [362, 367], ["A06"], ["BUSL"], ["active", "manual"], problems=["Double spend", "Coupon reuse"]),
        sub("D11.3", "Resource consumption and anti-automation", [770, 799, 400], ["A06"], ["BUSL"], ["active"], api=["API4"], problems=["No quotas or throttling", "Expensive queries unbounded"]),
    ]},
    {"id": "D12", "name": "File handling", "subdomains": [
        sub("D12.1", "Unrestricted upload", [434, 409], ["A06", "A05"], ["BUSL"], ["active", "manual"], problems=["Dangerous file types", "Archive bombs"]),
        sub("D12.2", "Path traversal and archive extraction", [22, 59], ["A01"], ["ATHZ"], ["active"], problems=["../ sequences", "Zip slip", "Symlink escape"]),
        sub("D12.3", "Download type handling", [430, 79], ["A02"], ["CONF"], ["capture"], ["WEB-20"], problems=["Untrusted download without attachment disposition"]),
    ]},
    {"id": "D13", "name": "API-specific security", "subdomains": [
        sub("D13.1", "Content type and schema discipline", [20, 436], ["A05", "A02"], ["INPV"], ["capture"], ["WEB-25"], api=["API8"], problems=["JSON endpoint returns another media type"]),
        sub("D13.2", "Inventory, versions and shadow endpoints", [1059], ["A02"], ["INFO"], ["manual"], api=["API9"], problems=["Old API versions still live", "Undocumented endpoints"]),
        sub("D13.3", "Unsafe consumption of upstream APIs", [20, 346], ["A06"], ["INPV"], ["manual"], api=["API10"], problems=["Third-party responses trusted without validation"]),
        sub("D13.4", "GraphQL-specific exposure", [200, 770], ["A02"], ["INFO"], ["active"], api=["API4", "API8"], problems=["Introspection in production", "No depth or cost limits"]),
    ]},
    {"id": "D14", "name": "Deserialization and data integrity", "subdomains": [
        sub("D14.1", "Insecure deserialization", [502], ["A08"], ["INPV"], ["active", "manual"], problems=["Untrusted object streams"]),
        sub("D14.2", "Unsigned code, updates and data", [494, 345], ["A08"], ["CONF"], ["manual"], problems=["Updates or plugins without signature checks"]),
    ]},
    {"id": "D15", "name": "Infrastructure, containers and delivery pipelines", "subdomains": [
        sub("D15.1", "Container image build", [250, 1188], ["A02", "A03"], ["CONF"], ["artifact"], ["INF-01", "INF-02", "INF-16"], problems=["Final stage runs as root", "Unpinned base image"]),
        sub("D15.2", "Kubernetes workload hardening", [250, 266, 1188], ["A02"], ["CONF"], ["artifact"],
            ["INF-03", "INF-04", "INF-05", "INF-06", "INF-07", "INF-08", "INF-11", "INF-12", "INF-13", "INF-14", "INF-15", "INF-17", "INF-18"],
            problems=["Privileged containers", "Host namespaces", "Host paths", "Capabilities", "Seccomp", "Service account mounts", "Sysctls"]),
        sub("D15.3", "Cloud storage exposure", [732, 284], ["A02", "A01"], ["CONF"], ["artifact"], ["INF-09"], problems=["Public access block missing"]),
        sub("D15.4", "CI/CD workflow security", [1357, 732, 829], ["A03", "A08"], ["CONF"], ["artifact"],
            ["CI-01", "CI-02", "CI-03", "CI-04", "CI-05", "CI-06", "CI-07", "CI-08", "CI-09", "CI-10"],
            problems=["Unpinned actions", "write-all tokens", "Persisted checkout credentials", "Weak branch protection", "Inherited secrets", "Self-hosted runners on PRs"]),
    ]},
    {"id": "D16", "name": "Logging, monitoring and exceptional conditions", "subdomains": [
        sub("D16.1", "Insufficient logging and alerting", [778], ["A09"], ["ERRH"], ["manual"], problems=["Security events not logged", "No alerting"]),
        sub("D16.2", "Error handling and fail-open behavior", [755, 636, 209], ["A10"], ["ERRH"], ["active", "manual"], problems=["Verbose errors", "Failures grant access", "Unhandled exceptions"]),
    ]},
    {"id": "D17", "name": "LLM-backed application risks", "subdomains": [
        sub("D17.1", "Prompt injection and tool abuse", [1427], ["A05", "A06"], ["INPV"], ["manual"], problems=["Untrusted content steers an agent", "Excessive agency"]),
        sub("D17.2", "Unsafe handling of model output", [79, 94], ["A05"], ["INPV"], ["manual"], problems=["Model output rendered or executed without validation"]),
    ]},
]

# Native-code weaknesses in the CWE Top 25 that a website scanner does not target.
OUT_OF_SCOPE_CWE = {787: "Out-of-bounds Write", 416: "Use After Free", 125: "Out-of-bounds Read", 120: "Classic Buffer Overflow",
                    476: "NULL Pointer Dereference", 121: "Stack-based Buffer Overflow", 122: "Heap-based Buffer Overflow"}


def subdomains():
    return [(d, s) for d in DOMAINS for s in d["subdomains"]]


def rule_index():
    index = {}
    for domain, subdomain in subdomains():
        for rule in subdomain["rules"]:
            index.setdefault(rule, []).append(subdomain["id"])
    return index


def summary():
    total = len(subdomains())
    covered = sum(1 for _, s in subdomains() if s["rules"])
    return {"domains": len(DOMAINS), "subdomains": total, "problems": sum(len(s["problems"]) for _, s in subdomains()),
            "subdomains_with_rules": covered, "subdomains_gap": total - covered}


def public():
    return {"version": "marsad-taxonomy-1", "summary": summary(), "domains": DOMAINS,
            "references": {"owasp_2025": OWASP_2025, "owasp_api_2023": OWASP_API_2023, "wstg": WSTG},
            "out_of_scope_cwe": {str(k): v for k, v in OUT_OF_SCOPE_CWE.items()}}
