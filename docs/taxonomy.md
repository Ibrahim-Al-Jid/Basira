# Vulnerability taxonomy

Generated from `backend/taxonomy.py` by `ops/build-taxonomy-docs.py`. Edit the module, not this file.

17 domains, 75 subdomains, 159 named problems. 34 subdomains are backed by at least one of the 100 shipped checks; 41 are documented gaps that need active probing or human review.

Reference sets: OWASP Top 10:2025, OWASP API Security Top 10 2023, OWASP WSTG 4.x chapters, CWE (2025 Top 25 informs ranking).

Modes: `artifact` reviews supplied files. `capture` reviews a supplied HAR or header capture. `active` needs authorized live probing and is not in the current scope policy. `manual` needs a person.

## D01 Access control and authorization

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D01.1 | Object-level authorization (IDOR/BOLA) | 639, 284, 862, 863 | A01, API1 | ATHZ | active, manual | gap |
| D01.2 | Function-level authorization and privilege escalation | 862, 863, 269 | A01, API5 | ATHZ | active, manual | gap |
| D01.3 | Cross-site request forgery | 352 | A01 | SESS | artifact, active | APP-11 |
| D01.4 | Cross-origin resource sharing policy | 942, 346 | A01, A02 | CLNT | capture, artifact | WEB-13, WEB-14, APP-10 |
| D01.5 | Tenant isolation | 284, 863 | A01 | ATHZ | artifact | INF-10 |
| D01.6 | Open redirect and unvalidated forwards | 601 | A01 | CLNT | active | gap |
| D01.7 | Mass assignment and object property exposure | 915, 213 | A01, API3 | INPV | active, manual | gap |

- **D01.1** Predictable object IDs; Cross-tenant record reads; Cross-account writes
- **D01.2** Admin routes reachable by users; Role parameter tampering; Forced browsing
- **D01.3** State-changing request without anti-CSRF token; CSRF protection disabled in framework
- **D01.4** Credentialed CORS with wildcard or reflected origin; Missing Vary on origin-varying responses
- **D01.5** Database row-level security absent or too broad
- **D01.6** Redirect target taken from a parameter
- **D01.7** Client sets server-owned fields; Responses include internal properties

## D02 Authentication and identity

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D02.1 | Credential entry and handling in forms | 598, 256, 549 | A07 | ATHN | artifact | HTML-17, HTML-18 |
| D02.2 | Authentication over cleartext channels | 319, 523 | A07, A04 | ATHN, CRYP | capture | WEB-22 |
| D02.3 | Brute force, lockout and credential stuffing | 307, 799 | A07, API2 | ATHN | active | gap |
| D02.4 | Password policy and default credentials | 521, 1392, 798 | A07 | ATHN, IDNT | active, manual | gap |
| D02.5 | Multi-factor authentication and recovery flows | 308, 640, 620 | A07 | ATHN | active, manual | gap |
| D02.6 | Account enumeration | 204 | A07 | IDNT | active | gap |
| D02.7 | Federated login and token flows (OAuth, OIDC, SAML, JWT) | 347, 290, 1390 | A07, A08, API2 | ATHN, SESS | active, manual | gap |

- **D02.1** Password submitted via GET; Password prefilled in markup
- **D02.2** Basic authentication challenged over HTTP
- **D02.3** No rate limit on login; No lockout or throttling
- **D02.4** Weak password rules; Vendor default accounts
- **D02.5** MFA bypass; Weak reset tokens; Password change without current password
- **D02.6** Different responses for known and unknown users
- **D02.7** Unsigned or weakly verified tokens; Redirect URI and state mistakes

## D03 Session management

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D03.1 | Session cookie attributes | 614, 1004, 1275 | A07, A02 | SESS | capture, artifact | WEB-09, WEB-10, WEB-11, WEB-12, APP-05, APP-08 |
| D03.2 | Session lifecycle: fixation, expiry, logout | 384, 613 | A07 | SESS | capture, active | WEB-19 |
| D03.3 | Session identifier strength | 330, 331 | A04, A07 | SESS | active | gap |

- **D03.1** Missing Secure; Missing HttpOnly; Missing or invalid SameSite; Domain scope too wide
- **D03.2** Session ID not renewed at login; Logout leaves state in the browser or server
- **D03.3** Predictable identifiers

## D04 Injection

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D04.1 | SQL and NoSQL injection | 89, 943 | A05 | INPV | active | gap |
| D04.2 | OS command and code injection | 78, 77, 94, 95 | A05 | INPV | active, manual | gap |
| D04.3 | Template and expression language injection | 1336, 917 | A05 | INPV | active | gap |
| D04.4 | XML and parser attacks (XXE, XPath, LDAP) | 611, 643, 90 | A05 | INPV | active | gap |
| D04.5 | HTTP header and log injection | 113, 117 | A05 | INPV | active | gap |

- **D04.1** Unparameterized queries; Operator injection in document queries
- **D04.2** Shell metacharacters reach a command; Eval of user input
- **D04.3** Server-side template injection
- **D04.4** External entities enabled
- **D04.5** CRLF in headers; Forged log lines

## D05 Client-side security

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D05.1 | Cross-site scripting | 79 | A05 | INPV, CLNT | active, manual | gap |
| D05.2 | Content Security Policy | 693, 1021 | A02 | CONF, CLNT | capture | WEB-02, WEB-03, WEB-04 |
| D05.3 | Framing and clickjacking | 1021 | A02 | CLNT | capture | WEB-05 |
| D05.4 | Frame, window and sandbox isolation | 1022, 1021, 749 | A02, A06 | CLNT | artifact | HTML-10, HTML-12, HTML-13, HTML-20 |
| D05.5 | Document base and resource origin control | 829, 610 | A02, A03 | CLNT | artifact | HTML-15, HTML-19 |
| D05.6 | Cross-origin isolation policies | 346, 653 | A02 | CLNT | capture | WEB-15, WEB-16, WEB-17 |
| D05.7 | Browser feature delegation | 250 | A02 | CLNT | capture | WEB-18 |
| D05.8 | Service workers and prototype pollution | 1321, 346 | A06, A08 | CLNT | capture, active | WEB-24 |
| D05.9 | Cross-window messaging and storage | 345, 922 | A06 | CLNT | active, manual | gap |

- **D05.1** Reflected; Stored; DOM-based
- **D05.2** No enforcing policy; unsafe-inline; unsafe-eval
- **D05.3** No frame-ancestors or X-Frame-Options
- **D05.4** Unsandboxed third-party iframe; Opener retained; Permissive sandbox; Delegated sensitive features
- **D05.5** base element redirects relative URLs; Connection hints to third parties
- **D05.6** COOP, COEP, CORP gaps
- **D05.7** Permissions-Policy grants features to any origin
- **D05.8** Service worker scope too broad; Prototype pollution gadgets
- **D05.9** postMessage without origin check; Secrets in web storage

## D06 Server-side requests and HTTP handling

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D06.1 | Server-side request forgery | 918 | A01, API7 | INPV | active | gap |
| D06.2 | Host header and routing trust | 644 | A02 | INPV, CONF | artifact, active | APP-09 |
| D06.3 | Request smuggling and desync | 444 | A02 | INPV | active | gap |
| D06.4 | Web cache poisoning and deception | 524, 525 | A02 | CONF | active | gap |
| D06.5 | Shared caching of private responses | 524, 525 | A02, A01 | CONF | capture | WEB-08 |

- **D06.1** Fetch of user-supplied URL reaches internal hosts
- **D06.2** Host allowlist admits all hosts; Password reset poisoning
- **D06.3** Front-end and back-end disagree on message length
- **D06.4** Unkeyed input in cached responses
- **D06.5** Private response with public cache directives

## D07 Cryptography and transport security

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D07.1 | Mixed content and cleartext submission | 319, 311 | A04 | CRYP | artifact | http-script, http-form, HTML-06, HTML-07, HTML-08, HTML-09, HTML-14 |
| D07.2 | HSTS and HTTPS redirects | 319, 523 | A04, A02 | CRYP, CONF | capture | WEB-01, WEB-23 |
| D07.3 | Certificate and TLS validation settings | 295, 297 | A04 | CRYP | artifact | APP-07 |
| D07.4 | Protocol versions, ciphers and certificates on a live host | 326, 327, 295 | A04 | CRYP | active | gap |
| D07.5 | Password hashing and key handling | 328, 916, 321, 330 | A04 | CRYP | manual | gap |

- **D07.1** HTTP scripts, styles, frames, media; Forms posting to HTTP; Meta refresh to HTTP
- **D07.2** HSTS absent or zero; HTTPS redirect ends on HTTP
- **D07.3** Certificate verification disabled in code or config
- **D07.4** Legacy TLS; Weak ciphers; Expired certificates
- **D07.5** Fast unsalted hashes; Hardcoded keys; Weak randomness

## D08 Security misconfiguration and hardening

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D08.1 | Hardening headers | 693, 16 | A02 | CONF | capture | WEB-06 |
| D08.2 | Version and technology disclosure | 200, 497 | A02 | INFO | capture | WEB-21 |
| D08.3 | Debug and development settings in production | 489, 215 | A02 | CONF | artifact | APP-04 |
| D08.4 | Exposed files, directories and admin interfaces | 548, 538, 527, 530 | A02 | CONF, INFO | active | gap |
| D08.5 | HTTP methods and default content | 749 | A02 | CONF | active | gap |

- **D08.1** No nosniff
- **D08.2** Server header exposes versions
- **D08.3** Debug mode enabled
- **D08.4** Directory listing; Exposed .git or backups; Open admin consoles
- **D08.5** TRACE, PUT enabled; Sample apps left installed

## D09 Sensitive data exposure and secrets

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D09.1 | Hardcoded secrets and credentials | 798, 321, 259 | A02, A04 | CONF | artifact | APP-01, APP-02, APP-03, APP-06 |
| D09.2 | Leakage through referrers and third-party requests | 200, 359 | A01, A02 | INFO | capture, artifact | WEB-07, HTML-16 |
| D09.3 | Data in URLs, logs, comments and source maps | 598, 532, 615 | A04, A09 | INFO | active, manual | gap |
| D09.4 | Excessive data exposure in APIs and error output | 213, 209, 200 | A01, A10, API3 | ERRH, INFO | active, manual | gap |

- **D09.1** Private key markers; Provider token signatures; Credentials in connection URLs; Keystore passwords in clear text
- **D09.2** unsafe-url referrer policy; Hyperlink auditing pings
- **D09.3** Tokens in query strings; Secrets in logs; Source maps in production
- **D09.4** Responses return more fields than the client uses; Stack traces

## D10 Software supply chain and dependencies

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D10.1 | Known-vulnerable components | 1395, 1104 | A03 | CONF | artifact | DEP-01, DEP-02, DEP-16 |
| D10.2 | Lockfile, version pinning and integrity | 494, 829, 1357 | A03, A08 | CONF | artifact | DEP-03, DEP-05, DEP-06, DEP-08, DEP-12, DEP-14, DEP-15 |
| D10.3 | Registry trust, credentials and publishing | 295, 522, 494 | A03, A07 | CONF | artifact | DEP-04, DEP-07, DEP-09, DEP-10, DEP-11, DEP-13 |
| D10.4 | Subresource integrity for third-party assets | 353, 829 | A03, A08 | CLNT | artifact | cdn-integrity, HTML-04, HTML-05, HTML-11 |
| D10.5 | Dependency confusion and typosquatting | 427, 1357 | A03 | CONF | manual | gap |

- **D10.1** Direct match to a published advisory; Transitive match; Deprecated package
- **D10.2** No lockfile; Floating versions; Git dependency without commit; SHA-1 only integrity; Local path outside repo
- **D10.3** HTTP registry; Registry outside allowlist; Certificate validation off; Credentials in config or URLs; Public publish allowed
- **D10.4** CDN script or stylesheet without SRI; Invalid digest; Cross-origin SRI without CORS mode
- **D10.5** Internal package names resolvable from public registries

## D11 Business logic and abuse

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D11.1 | Workflow and state bypass | 841, 840 | A06, API6 | BUSL | manual | gap |
| D11.2 | Race conditions and replay | 362, 367 | A06 | BUSL | active, manual | gap |
| D11.3 | Resource consumption and anti-automation | 770, 799, 400 | A06, API4 | BUSL | active | gap |

- **D11.1** Steps skipped; Price or quantity tampering
- **D11.2** Double spend; Coupon reuse
- **D11.3** No quotas or throttling; Expensive queries unbounded

## D12 File handling

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D12.1 | Unrestricted upload | 434, 409 | A06, A05 | BUSL | active, manual | gap |
| D12.2 | Path traversal and archive extraction | 22, 59 | A01 | ATHZ | active | gap |
| D12.3 | Download type handling | 430, 79 | A02 | CONF | capture | WEB-20 |

- **D12.1** Dangerous file types; Archive bombs
- **D12.2** ../ sequences; Zip slip; Symlink escape
- **D12.3** Untrusted download without attachment disposition

## D13 API-specific security

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D13.1 | Content type and schema discipline | 20, 436 | A05, A02, API8 | INPV | capture | WEB-25 |
| D13.2 | Inventory, versions and shadow endpoints | 1059 | A02, API9 | INFO | manual | gap |
| D13.3 | Unsafe consumption of upstream APIs | 20, 346 | A06, API10 | INPV | manual | gap |
| D13.4 | GraphQL-specific exposure | 200, 770 | A02, API4, API8 | INFO | active | gap |

- **D13.1** JSON endpoint returns another media type
- **D13.2** Old API versions still live; Undocumented endpoints
- **D13.3** Third-party responses trusted without validation
- **D13.4** Introspection in production; No depth or cost limits

## D14 Deserialization and data integrity

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D14.1 | Insecure deserialization | 502 | A08 | INPV | active, manual | gap |
| D14.2 | Unsigned code, updates and data | 494, 345 | A08 | CONF | manual | gap |

- **D14.1** Untrusted object streams
- **D14.2** Updates or plugins without signature checks

## D15 Infrastructure, containers and delivery pipelines

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D15.1 | Container image build | 250, 1188 | A02, A03 | CONF | artifact | INF-01, INF-02, INF-16 |
| D15.2 | Kubernetes workload hardening | 250, 266, 1188 | A02 | CONF | artifact | INF-03, INF-04, INF-05, INF-06, INF-07, INF-08, INF-11, INF-12, INF-13, INF-14, INF-15, INF-17, INF-18 |
| D15.3 | Cloud storage exposure | 732, 284 | A02, A01 | CONF | artifact | INF-09 |
| D15.4 | CI/CD workflow security | 1357, 732, 829 | A03, A08 | CONF | artifact | CI-01, CI-02, CI-03, CI-04, CI-05, CI-06, CI-07, CI-08, CI-09, CI-10 |

- **D15.1** Final stage runs as root; Unpinned base image
- **D15.2** Privileged containers; Host namespaces; Host paths; Capabilities; Seccomp; Service account mounts; Sysctls
- **D15.3** Public access block missing
- **D15.4** Unpinned actions; write-all tokens; Persisted checkout credentials; Weak branch protection; Inherited secrets; Self-hosted runners on PRs

## D16 Logging, monitoring and exceptional conditions

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D16.1 | Insufficient logging and alerting | 778 | A09 | ERRH | manual | gap |
| D16.2 | Error handling and fail-open behavior | 755, 636, 209 | A10 | ERRH | active, manual | gap |

- **D16.1** Security events not logged; No alerting
- **D16.2** Verbose errors; Failures grant access; Unhandled exceptions

## D17 LLM-backed application risks

| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Basira checks |
|---|---|---|---|---|---|---|
| D17.1 | Prompt injection and tool abuse | 1427 | A05, A06 | INPV | manual | gap |
| D17.2 | Unsafe handling of model output | 79, 94 | A05 | INPV | manual | gap |

- **D17.1** Untrusted content steers an agent; Excessive agency
- **D17.2** Model output rendered or executed without validation

## Out of scope

Memory-safety weaknesses from the CWE Top 25 are native-code problems, not website problems: CWE-787 Out-of-bounds Write, CWE-416 Use After Free, CWE-125 Out-of-bounds Read, CWE-120 Classic Buffer Overflow, CWE-476 NULL Pointer Dereference, CWE-121 Stack-based Buffer Overflow, CWE-122 Heap-based Buffer Overflow.
