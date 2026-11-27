"""Read-only capture for exact HTTPS pages approved by the operator."""

from contextlib import closing
from hashlib import sha256
from html.parser import HTMLParser
from http.client import HTTPSConnection, HTTPException as HTTPProtocolError
from ipaddress import ip_address
import json
import os
import re
import socket
import ssl
from threading import Timer
from time import monotonic, sleep
from urllib.parse import urlsplit

from .artifact_review import InputError

MAX_BODY = 250_000
MAX_SECONDS = 10
MAX_PAGES = 3
SAFE_HEADERS = {
    "cache-control", "content-security-policy", "content-type", "cross-origin-embedder-policy",
    "cross-origin-opener-policy", "cross-origin-resource-policy", "permissions-policy",
    "referrer-policy", "strict-transport-security", "x-content-type-options", "x-frame-options",
}
CSP_KEYWORDS = {"'none'", "'self'", "'unsafe-inline'", "'unsafe-eval'", "'strict-dynamic'", "*"}
PUBLIC_HEADER_VALUE = re.compile(
    r"(?:deny|sameorigin|nosniff|no-referrer(?:-when-downgrade)?|same-origin(?:-allow-popups)?|"
    r"origin(?:-when-cross-origin)?|strict-origin(?:-when-cross-origin)?|unsafe-url|require-corp|"
    r"credentialless|cross-origin|same-site|unsafe-none|public|private|no-store|no-cache|"
    r"must-revalidate|immutable|max-age=[0-9]{1,12}|s-maxage=[0-9]{1,12}|includesubdomains|preload)",
    re.IGNORECASE,
)


def canonical_url(value):
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::443)?(?:/[A-Za-z0-9._~/-]*)?", value, re.ASCII):
        raise InputError("استخدم رابط HTTPS معتمد من غير معاملات أو بيانات تسجيل دخول.")
    parts = urlsplit(value)
    host = parts.hostname
    path = parts.path or "/"
    labels = host.split(".")
    if (len(labels) < 2 or not labels[-1].isalpha() or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
            or "//" in path or {".", ".."}.intersection(path.split("/"))):
        raise InputError("اسم النطاق أو مسار الصفحة غير صالح.")
    return f"https://{host}{path}"


def approved_pages(project_id):
    try:
        assignments = json.loads(os.environ.get("BASIRA_APPROVED_WEBSITE_PAGES", "{}"))
        approved = assignments.get(project_id, [])
    except (ValueError, AttributeError):
        approved = []
    return approved if isinstance(approved, list) else []


def approved_url(value, project_id):
    url = canonical_url(value)
    if url not in approved_pages(project_id):
        raise InputError("الصفحة خارج قائمة الصفحات المصرّح بها لجمع الأدلة.")
    return url


def capture_scope(url, project_id):
    # Every request has an explicit operator approval. Links in responses are observations only.
    pages = [url]
    origin = urlsplit(url).netloc
    for candidate in approved_pages(project_id):
        if not isinstance(candidate, str):
            continue
        try:
            page = canonical_url(candidate)
        except InputError:
            continue
        if page == candidate and urlsplit(page).netloc == origin and page not in pages:
            pages.append(page)
        if len(pages) == MAX_PAGES:
            break
    raw, facts = capture(url)
    if len(pages) == 1:
        return raw, facts
    entries = json.loads(raw)["log"]["entries"]
    fingerprints = [facts["page_sha256"]]
    for page in pages[1:]:
        sleep(0.3)
        raw, next_facts = capture(page)
        entries.extend(json.loads(raw)["log"]["entries"])
        for field in ("forms", "links_observed", "page_bytes"):
            facts[field] += next_facts[field]
        if facts["tls_version"] != next_facts["tls_version"]:
            facts["tls_version"] = None
        fingerprints.append(next_facts["page_sha256"])
    facts.update(pages=len(pages), requests=len(entries),
                 page_sha256=sha256("".join(fingerprints).encode("ascii")).hexdigest())
    return json.dumps({"log": {"entries": entries}}).encode(), facts


def validated_address(host):
    records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    addresses = [ip_address(record[4][0]) for record in records]
    if not addresses or any(
        not address.is_global or address.is_multicast or address.is_reserved
        or getattr(address, "ipv4_mapped", None) is not None
        or getattr(address, "sixtofour", None) is not None
        or getattr(address, "teredo", None) is not None
        or address.version == 6 and not str(address).startswith(("2", "3"))
        for address in addresses
    ):
        raise InputError("عنوان الشبكة خارج النطاق العام المصرّح به.")
    return str(addresses[0])


class PageProfile(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = 0
        self.references = 0

    def handle_starttag(self, tag, attrs):
        self.forms += tag == "form"
        self.references += tag == "a" and any(key == "href" for key, _ in attrs)


def safe_headers(headers):
    saved = []
    for key, value in headers:
        name = key.lower()
        if name == "set-cookie":
            # Preserve security attributes and omit names, values, paths and domains.
            flags = []
            for field in value.split(";")[1:]:
                flag = field.strip().lower()
                if flag in {"secure", "httponly", "samesite=lax", "samesite=strict", "samesite=none"}:
                    flags.append(flag)
            saved.append({"name": name, "value": "; ".join(["redacted=redacted", *flags])})
        elif name in SAFE_HEADERS and len(value) <= 2048:
            if name == "content-security-policy":
                directives = []
                for part in value.split(";"):
                    bits = part.split()
                    if bits and re.fullmatch(
                        r"(?:(?:[a-z-]+-)?src(?:-elem|-attr)?|base-uri|form-action|frame-ancestors|"
                        r"upgrade-insecure-requests|block-all-mixed-content)", bits[0]
                    ):
                        sources = [token if token in CSP_KEYWORDS else "redacted.invalid" for token in bits[1:]]
                        directives.append(" ".join([bits[0], *sources]))
                value = "; ".join(directives)
            elif name == "content-type":
                value = value.split(";", 1)[0].strip().lower()
            else:
                value = re.sub(r"[^,;]+", lambda match: match[0] if PUBLIC_HEADER_VALUE.fullmatch(match[0].strip())
                               else "redacted", value)
            saved.append({"name": name, "value": value})
    return saved


def capture(url):
    # Only call after checking project ownership, quotas and exact URL approval.
    target = urlsplit(url)
    deadline = monotonic() + MAX_SECONDS
    try:
        address = validated_address(target.hostname)
        with closing(HTTPSConnection(target.hostname, timeout=4, context=ssl.create_default_context())) as conn:
            # HTTPSConnection still performs TLS hostname verification and SNI for the approved hostname.
            conn._create_connection = lambda _destination, timeout, source: socket.create_connection(
                (address, 443), timeout, source
            )
            conn.connect()
            transport = conn.sock
            tls_version = transport.version()
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise InputError("انتهت مهلة جمع أدلة الصفحة.")
            watchdog = Timer(remaining, end_connection, args=(transport,))
            watchdog.daemon = True
            watchdog.start()
            try:
                return capture_response(conn, target, url, deadline, tls_version)
            finally:
                watchdog.cancel()
    except (OSError, HTTPProtocolError, ValueError, RecursionError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("تعذّر جمع أدلة الصفحة عبر HTTPS.") from None


def end_connection(transport):
    try:
        transport.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def capture_response(conn, target, url, deadline, tls_version):
    conn.request("GET", target.path, headers={
        "Accept": "text/html, application/xhtml+xml", "Accept-Encoding": "identity",
        "User-Agent": "Basira-Passive-Evidence/1.0", "Connection": "close",
    })
    with conn.getresponse() as response:
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if response.status != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
            raise InputError("جمع الأدلة يحتاج صفحة HTML عامة بترجع HTTP 200 مباشرة.")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise InputError("الصفحة بترجع ترميز ضغط غير مدعوم.")
        body = bytearray()
        while chunk := response.read1(16_384):
            body.extend(chunk)
            if len(body) > MAX_BODY or monotonic() >= deadline:
                raise InputError("الصفحة تجاوزت حد حجم أو وقت جمع الأدلة.")
        if monotonic() >= deadline:
            raise InputError("انتهت مهلة جمع أدلة الصفحة.")
        profile = PageProfile()
        profile.feed(body.decode("utf-8", errors="replace"))
        result = {"log": {"entries": [{"request": {"url": url, "method": "GET"}, "response": {
            "status": 200, "headers": safe_headers(response.getheaders()),
            "content": {"mimeType": content_type, "size": len(body)},
        }}]}}
        return json.dumps(result).encode(), {
            "pages": 1, "requests": 1, "forms": profile.forms, "links_observed": profile.references,
            "page_bytes": len(body), "page_sha256": sha256(body).hexdigest(), "tls_version": tls_version,
        }
