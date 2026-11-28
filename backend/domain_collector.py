"""Passive domain evidence for operator-approved sites: the domain collector tool.

For one approved page URL this collects DNS-over-HTTPS answers from one fixed resolver,
TLS facts, a fixed set of well-known files and certificate-transparency names. Scope is
the exact hosts of the approved pages plus the subdomains of their apex, derived by
walking SOA records so multi-label suffixes (example.co.uk) need no public-suffix list.
Public addresses only, rate limited, no model, no stored bodies beyond digests.

Design: docs/ARCHITECTURE-agents.md section 4a. Wiring into a role tool allow-list is a
separate phase; this module is the tool itself. All network seams are module-level
functions so tests can run with a fully mocked network.
"""

from contextlib import closing
from hashlib import sha256
from http.client import HTTPSConnection, HTTPException as HTTPProtocolError
from ipaddress import ip_address
import json
import re
import socket
import ssl
from time import monotonic, sleep
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from .artifact_review import InputError
from .intake_website import approved_pages, approved_url, canonical_url, validated_address

TOOL_ID = "domain-collector"
TOOL_VERSION = "1.0.0"

DOH_RESOLVER = "dns.google"  # The one fixed DNS-over-HTTPS resolver (JSON API).
DOH_PATH = "/resolve"
CT_HOST = "crt.sh"  # The fixed certificate-transparency name search.
WELL_KNOWN_PATHS = ("/.well-known/security.txt", "/robots.txt")

MAX_SUBDOMAINS = 10
MAX_CT_NAMES = 200
MAX_CT_BYTES = 1_000_000
MAX_DNS_BYTES = 100_000
MAX_FILE_BYTES = 64_000
MAX_REQUESTS = 30
MAX_CERT_NAMES = 20
MAX_LABELS = 12
REQUEST_DELAY = 0.3
REQUEST_TIMEOUT = 5
RECORD_TYPES = {"A": 1, "AAAA": 28, "SOA": 6}
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
USER_AGENT = "Basira-Passive-Evidence/1.0"

REASONS = frozenset({
    "over_budget", "dns_error", "nxdomain", "no_public_address", "timeout",
    "connect_error", "tls_error", "http_error", "ct_error",
})


class FetchError(Exception):
    """A failed outbound step, carrying only a fixed reason code."""

    def __init__(self, reason):
        if reason not in REASONS:
            raise ValueError("unknown reason code")
        super().__init__(reason)
        self.reason = reason


class TlsEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    reason: str | None = None
    version: str | None = None
    cipher: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    issuer: str | None = None
    subject: str | None = None
    names: list[str] = Field(default_factory=list)


class WellKnownFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    status: Literal["ok", "error"]
    reason: str | None = None
    http_status: int | None = None
    bytes: int = 0
    sha256: str | None = None


class NameEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    origin: Literal["approved_host", "apex", "certificate_transparency"]
    dns_status: Literal["ok", "nxdomain", "error", "skipped"]
    reason: str | None = None
    addresses: list[str] = Field(default_factory=list)
    non_public_addresses: int = 0
    tls: TlsEvidence | None = None
    files: list[WellKnownFile] = Field(default_factory=list)


class DomainEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = TOOL_ID
    version: str = TOOL_VERSION
    resolver: str = DOH_RESOLVER
    approved_hosts: list[str]
    apex: str
    ct_names: int = 0
    names: list[NameEvidence]
    requests: int = 0
    status: Literal["ok", "partial", "error"]
    reason: str | None = None


class _Budget:
    """One collection run's outbound request allowance and pace."""

    def __init__(self):
        self.requests = 0

    def spend(self):
        if self.requests >= MAX_REQUESTS:
            raise FetchError("over_budget")
        if self.requests:
            sleep(REQUEST_DELAY)
        self.requests += 1


# ---- network seams (mocked in tests) ----


def _https_get(host, path, max_bytes):
    """One pinned, read-only HTTPS GET to a fixed host. Returns (http_status, body)."""
    try:
        address = validated_address(host)
    except InputError:
        raise FetchError("connect_error") from None
    deadline = monotonic() + REQUEST_TIMEOUT + 3
    try:
        with closing(HTTPSConnection(host, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context())) as conn:
            # Connect to the validated address while TLS still verifies the fixed host name.
            conn._create_connection = lambda _destination, timeout, source: socket.create_connection(
                (address, 443), timeout, source
            )
            conn.request("GET", path, headers={
                "Accept": "application/json", "User-Agent": USER_AGENT, "Connection": "close",
            })
            with conn.getresponse() as response:
                body = bytearray()
                while chunk := response.read1(16_384):
                    body.extend(chunk)
                    if len(body) > max_bytes or monotonic() >= deadline:
                        raise FetchError("http_error")
                return response.status, bytes(body)
    except (OSError, HTTPProtocolError, ValueError) as exc:
        raise FetchError("timeout" if isinstance(exc, TimeoutError) else "connect_error") from None


def _doh_query(name, record_type):
    """One DNS-over-HTTPS JSON query against the fixed resolver. Returns the parsed payload."""
    _, body = _https_get(DOH_RESOLVER, f"{DOH_PATH}?name={name}&type={RECORD_TYPES[record_type]}", MAX_DNS_BYTES)
    try:
        payload = json.loads(body)
    except ValueError:
        raise FetchError("dns_error") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("Status"), int):
        raise FetchError("dns_error")
    return payload


def _ct_names(apex):
    """Certificate-transparency names under the apex from the fixed CT search. Raw, unvalidated."""
    status, body = _https_get(CT_HOST, f"/?q=%25.{apex}&output=json", MAX_CT_BYTES)
    if status != 200:
        raise FetchError("ct_error")
    try:
        rows = json.loads(body)
    except ValueError:
        raise FetchError("ct_error")
    if not isinstance(rows, list):
        raise FetchError("ct_error")
    names = set()
    for row in rows[:MAX_CT_NAMES]:
        if isinstance(row, dict) and isinstance(row.get("name_value"), str):
            names.update(row["name_value"].split("\n"))
    return names


def _tls_facts(name, address):
    """TLS handshake facts for a name at one public address; the certificate is verified."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((address, 443), timeout=REQUEST_TIMEOUT) as raw:
            with context.wrap_socket(raw, server_hostname=name) as transport:
                cert = transport.getpeercert()
                return {
                    "version": transport.version(),
                    "cipher": transport.cipher()[0] if transport.cipher() else None,
                    "not_before": cert.get("notBefore"),
                    "not_after": cert.get("notAfter"),
                    "issuer": _cert_name(cert.get("issuer")),
                    "subject": _cert_name(cert.get("subject")),
                    "names": sorted({value for kind, value in cert.get("subjectAltName", ()) if kind == "DNS"}
                                    )[:MAX_CERT_NAMES],
                }
    except ssl.SSLError:
        raise FetchError("tls_error") from None
    except (OSError, ValueError) as exc:
        raise FetchError("timeout" if isinstance(exc, TimeoutError) else "connect_error") from None


def _well_known_file(name, address, path):
    """One well-known file from a name at one public address; redirects are recorded, not followed."""
    try:
        with closing(HTTPSConnection(name, timeout=REQUEST_TIMEOUT, context=ssl.create_default_context())) as conn:
            conn._create_connection = lambda _destination, timeout, source: socket.create_connection(
                (address, 443), timeout, source
            )
            conn.request("GET", path, headers={
                "Accept": "text/plain, text/*, */*", "User-Agent": USER_AGENT, "Connection": "close",
            })
            with conn.getresponse() as response:
                if response.status != 200:
                    return {"http_status": response.status}
                body = bytearray()
                deadline = monotonic() + REQUEST_TIMEOUT
                while chunk := response.read1(16_384):
                    body.extend(chunk)
                    if len(body) > MAX_FILE_BYTES or monotonic() >= deadline:
                        raise FetchError("http_error")
                return {"http_status": 200, "bytes": len(body), "sha256": sha256(bytes(body)).hexdigest()}
    except ssl.SSLError:
        raise FetchError("tls_error") from None
    except (OSError, HTTPProtocolError, ValueError) as exc:
        raise FetchError("timeout" if isinstance(exc, TimeoutError) else "connect_error") from None


# ---- scope ----


def _cert_name(parts):
    """One readable name from a certificate subject or issuer tuple, values capped."""
    if not parts:
        return None
    flattened = [f"{key}={value[:64]}" for group in parts for key, value in group]
    return ", ".join(flattened)[:256]


def _public_split(values):
    """Split IP answer strings into public addresses and a count of everything else."""
    public, non_public = [], 0
    for value in values:
        try:
            address = ip_address(value)
        except ValueError:
            non_public += 1
            continue
        if (address.is_global and not address.is_multicast and not address.is_reserved
                and getattr(address, "ipv4_mapped", None) is None
                and getattr(address, "sixtofour", None) is None
                and getattr(address, "teredo", None) is None
                and not (address.version == 6 and not str(address).startswith(("2", "3")))):
            public.append(str(address))
        else:
            non_public += 1
    return sorted(set(public)), non_public


def _in_scope_name(value, apex):
    """Normalize one CT name, or return None when it is not a clean subdomain of the apex."""
    name = value.strip().lower().rstrip(".")
    if name.startswith("*."):
        name = name[2:]
    if not name or (name != apex and not name.endswith("." + apex)):
        return None
    labels = name.split(".")
    if len(labels) > MAX_LABELS or any(not LABEL.fullmatch(label) for label in labels):
        return None
    return name


def _apex(host, budget):
    """The zone apex of a host, found by walking SOA records up the fixed resolver."""
    labels = host.split(".")
    for cut in range(len(labels) - 1):
        candidate = ".".join(labels[cut:])
        budget.spend()
        payload = _doh_query(candidate, "SOA")
        if payload.get("Status") == 0 and payload.get("Answer"):
            return candidate
    return host


# ---- collection ----


def _answers(payload, record_type):
    """Answer data strings of one record type from a DoH payload."""
    answers = payload.get("Answer") or []
    return [row["data"] for row in answers
            if isinstance(row, dict) and row.get("type") == RECORD_TYPES[record_type] and isinstance(row.get("data"), str)]


def _probe(name, origin, budget):
    """Collect every stage for one in-scope name. Failures land as fixed reason codes."""
    record = NameEvidence(name=name, origin=origin, dns_status="skipped", reason="over_budget")
    try:
        budget.spend()
        payload = _doh_query(name, "A")
        budget.spend()
        payload_aaaa = _doh_query(name, "AAAA")
    except FetchError as exc:
        return record.model_copy(update={"dns_status": "error", "reason": exc.reason})
    if payload.get("Status") == 3 and payload_aaaa.get("Status") == 3:
        return record.model_copy(update={"dns_status": "nxdomain", "reason": "nxdomain"})
    if payload.get("Status") != 0 or payload_aaaa.get("Status") != 0:
        return record.model_copy(update={"dns_status": "error", "reason": "dns_error"})
    addresses, non_public = _public_split(_answers(payload, "A") + _answers(payload_aaaa, "AAAA"))
    record = record.model_copy(update={
        "dns_status": "ok", "reason": None, "addresses": addresses, "non_public_addresses": non_public,
    })
    if not addresses:
        return record.model_copy(update={"reason": "no_public_address"})
    address = addresses[0]
    try:
        budget.spend()
        record.tls = TlsEvidence(status="ok", **_tls_facts(name, address))
    except FetchError as exc:
        record.tls = TlsEvidence(status="error", reason=exc.reason)
    for path in WELL_KNOWN_PATHS:
        try:
            budget.spend()
            record.files.append(WellKnownFile(path=path, status="ok", **_well_known_file(name, address, path)))
        except FetchError as exc:
            record.files.append(WellKnownFile(path=path, status="error", reason=exc.reason))
        if record.files[-1].reason == "over_budget":
            break
    return record


def _stage_reasons(record):
    """The failure reasons of one probed name, excluding normal outcomes like nxdomain."""
    reasons = [record.reason] if record.dns_status in ("error", "skipped") else []
    if record.tls and record.tls.status == "error":
        reasons.append(record.tls.reason)
    reasons += [item.reason for item in record.files if item.status == "error"]
    return [reason for reason in reasons if reason]


def _approved_hosts(project_id):
    """Every exact approved page host for the project, for evidence provenance."""
    hosts = set()
    for page in approved_pages(project_id):
        if isinstance(page, str):
            try:
                hosts.add(urlsplit(canonical_url(page)).hostname)
            except InputError:
                continue
    return sorted(hosts)


def collect(url, project_id):
    """Passive domain evidence for one approved page URL and its apex subdomains."""
    approved = approved_url(url, project_id)
    host = urlsplit(approved).hostname
    budget = _Budget()
    status, reason = "ok", None

    try:
        apex = _apex(host, budget)
    except FetchError as exc:
        apex, status, reason = host, "partial", exc.reason

    ct_names = set()
    if reason != "over_budget":
        try:
            budget.spend()
            ct_names = {name for name in (_in_scope_name(value, apex) for value in _ct_names(apex)) if name}
        except FetchError as exc:
            status, reason = "partial", reason or exc.reason

    ordered = [(host, "approved_host")]
    if apex != host:
        ordered.append((apex, "apex"))
    ordered += sorted((name, "certificate_transparency") for name in ct_names - {host, apex})[:MAX_SUBDOMAINS]

    names = []
    exhausted = reason == "over_budget"
    for name, origin in ordered:
        if exhausted:
            names.append(NameEvidence(name=name, origin=origin, dns_status="skipped", reason="over_budget"))
            continue
        record = _probe(name, origin, budget)
        failures = _stage_reasons(record)
        if failures:
            status = "partial"
            reason = reason or failures[0]
            exhausted = "over_budget" in failures
        names.append(record)

    return DomainEvidence(
        approved_hosts=_approved_hosts(project_id), apex=apex, ct_names=len(ct_names), names=names,
        requests=budget.requests, status=status, reason=reason,
    )
