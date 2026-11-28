"""Domain collector tests. Everything runs offline against a scripted network."""
import json

import pytest

from . import domain_collector as dc
from .artifact_review import InputError

PROJECT = "proj-1"
PAGE = "https://app.example.com/"
PUBLIC = "93.184.216.34"
CERT = {
    "version": "TLSv1.3", "cipher": "TLS_AES_128_GCM_SHA256",
    "not_before": "Nov  1 00:00:00 2026 GMT", "not_after": "Feb  1 00:00:00 2027 GMT",
    "issuer": "CN=Test CA", "subject": "CN=example.com", "names": ["example.com", "*.example.com"],
}


@pytest.fixture
def approved(monkeypatch):
    monkeypatch.setenv("BASIRA_APPROVED_WEBSITE_PAGES", json.dumps({PROJECT: [PAGE]}))


class Network:
    """A scripted network. Every seam is replaced, so a live call is impossible here."""

    DNS = {
        "app.example.com": {"A": [PUBLIC], "AAAA": []},
        "example.com": {"A": [PUBLIC], "AAAA": []},
        "www.example.com": {"A": ["93.184.216.35"], "AAAA": []},
        "api.example.com": {"A": ["10.1.2.3", "not-an-ip"], "AAAA": []},
        "down.example.com": {"A": None, "AAAA": None},
        "broken.example.com": {"A": "SERVFAIL", "AAAA": "SERVFAIL"},
    }
    CT = {"www.example.com", "*.api.example.com", "down.example.com",
          "evil.example.org", "APP.EXAMPLE.COM.", "example.com", "not a domain", "a_b.example.com"}

    def __init__(self, monkeypatch):
        self.calls = []
        self.sleeps = 0
        monkeypatch.setattr(dc, "_doh_query", self.doh)
        monkeypatch.setattr(dc, "_ct_names", self.ct)
        monkeypatch.setattr(dc, "_tls_facts", self.tls)
        monkeypatch.setattr(dc, "_well_known_file", self.well_known)
        monkeypatch.setattr(dc, "sleep", self.pause)

    def pause(self, _seconds):
        self.sleeps += 1

    def doh(self, name, record_type):
        self.calls.append(("doh", name, record_type))
        if record_type == "SOA":
            answer = [{"type": 6, "data": "ns1.example.com."}] if name == "example.com" else []
            return {"Status": 0 if answer else 3, "Answer": answer}
        answers = self.DNS.get(name, {}).get(record_type)
        if answers is None:
            return {"Status": 3, "Answer": []}
        if answers == "SERVFAIL":
            return {"Status": 2}
        return {"Status": 0, "Answer": [{"type": dc.RECORD_TYPES[record_type], "data": a} for a in answers]}

    def ct(self, apex):
        self.calls.append(("ct", apex))
        return set(self.CT)

    def tls(self, name, address):
        self.calls.append(("tls", name, address))
        return dict(CERT)

    def well_known(self, name, address, path):
        self.calls.append(("file", name, path))
        if path == "/.well-known/security.txt":
            return {"http_status": 200, "bytes": 321, "sha256": "c" * 64}
        return {"http_status": 404}

    def dialed(self, name):
        return [call for call in self.calls if call[0] in ("tls", "file") and call[1] == name]


@pytest.fixture
def network(monkeypatch):
    return Network(monkeypatch)


def reasons(evidence):
    found = [evidence.reason]
    for record in evidence.names:
        found += [record.reason]
        found += [record.tls.reason] if record.tls else []
        found += [item.reason for item in record.files]
    return [reason for reason in found if reason]


def test_collect_builds_scoped_evidence_for_the_approved_host_and_apex_subdomains(approved, network):
    evidence = dc.collect(PAGE, PROJECT)
    assert evidence.tool == "domain-collector" and evidence.resolver == "dns.google"
    assert evidence.status == "ok" and evidence.approved_hosts == ["app.example.com"]
    assert evidence.apex == "example.com" and evidence.ct_names == 5
    assert [(n.name, n.origin) for n in evidence.names] == [
        ("app.example.com", "approved_host"),
        ("example.com", "apex"),
        ("api.example.com", "certificate_transparency"),
        ("down.example.com", "certificate_transparency"),
        ("www.example.com", "certificate_transparency"),
    ]
    host = evidence.names[0]
    assert host.dns_status == "ok" and host.addresses == [PUBLIC] and host.non_public_addresses == 0
    assert host.tls.status == "ok" and host.tls.version == "TLSv1.3" and host.tls.names == CERT["names"]
    assert [(f.path, f.http_status) for f in host.files] == [("/.well-known/security.txt", 200), ("/robots.txt", 404)]
    assert evidence.requests <= dc.MAX_REQUESTS and network.sleeps == evidence.requests - 1


def test_serialized_evidence_round_trips_and_uses_only_fixed_reason_codes(approved, network):
    evidence = dc.collect(PAGE, PROJECT)
    loaded = dc.DomainEvidence(**json.loads(evidence.model_dump_json()))
    assert loaded == evidence and set(reasons(evidence)) <= dc.REASONS


def test_every_recorded_outcome_matches_the_scripted_network(approved, network):
    evidence = {n.name: n for n in dc.collect(PAGE, PROJECT).names}
    assert evidence["api.example.com"].reason == "no_public_address"
    assert evidence["api.example.com"].addresses == [] and evidence["api.example.com"].non_public_addresses == 2
    assert evidence["down.example.com"].dns_status == "nxdomain" and evidence["down.example.com"].tls is None


def test_a_dns_servfail_is_an_error_with_a_fixed_reason(approved, network, monkeypatch):
    network.CT = set(network.CT) | {"broken.example.com"}
    evidence = dc.collect(PAGE, PROJECT)
    broken = [n for n in evidence.names if n.name == "broken.example.com"][0]
    assert broken.dns_status == "error" and broken.reason == "dns_error" and broken.tls is None
    assert evidence.status == "partial" and evidence.reason == "dns_error"


def test_names_without_public_addresses_or_records_are_never_dialed(approved, network):
    dc.collect(PAGE, PROJECT)
    assert network.dialed("api.example.com") == [] and network.dialed("down.example.com") == []
    assert all(call[1] != "evil.example.org" for call in network.calls)


def test_an_unapproved_url_is_refused_before_any_network_call(approved, network):
    with pytest.raises(InputError):
        dc.collect("https://app.example.com/other", PROJECT)
    with pytest.raises(InputError):
        dc.collect("https://other.example.com/", PROJECT)
    assert network.calls == []


def test_budget_exhaustion_stops_collection_with_a_fixed_reason(approved, network, monkeypatch):
    monkeypatch.setattr(dc, "MAX_REQUESTS", 4)
    evidence = dc.collect(PAGE, PROJECT)
    assert evidence.status == "partial" and evidence.reason == "over_budget"
    assert evidence.requests == 4 and len([c for c in network.calls if c[0] == "doh"]) == 3
    assert all(n.dns_status == "skipped" and n.reason == "over_budget" for n in evidence.names[1:])


def test_a_ct_search_failure_degrades_to_approved_scope_only(approved, network, monkeypatch):
    def failing_ct(apex):
        raise dc.FetchError("ct_error")

    monkeypatch.setattr(dc, "_ct_names", failing_ct)
    evidence = dc.collect(PAGE, PROJECT)
    assert evidence.status == "partial" and evidence.reason == "ct_error"
    assert [n.name for n in evidence.names] == ["app.example.com", "example.com"]
    assert all(n.dns_status == "ok" for n in evidence.names)


def test_a_tls_failure_is_recorded_and_files_are_still_collected(approved, network, monkeypatch):
    monkeypatch.setattr(dc, "_tls_facts", lambda name, address: (_ for _ in ()).throw(dc.FetchError("tls_error")))
    evidence = dc.collect(PAGE, PROJECT)
    assert evidence.status == "partial" and evidence.reason == "tls_error"
    host = evidence.names[0]
    assert host.tls.status == "error" and host.tls.reason == "tls_error"
    assert [f.status for f in host.files] == ["ok", "ok"]


def test_a_well_known_failure_is_recorded_per_file(approved, network, monkeypatch):
    def failing(name, address, path):
        if path == "/robots.txt":
            raise dc.FetchError("timeout")
        return {"http_status": 200, "bytes": 1, "sha256": "d" * 64}

    monkeypatch.setattr(dc, "_well_known_file", failing)
    evidence = dc.collect(PAGE, PROJECT)
    host = evidence.names[0]
    assert [(f.path, f.status, f.reason) for f in host.files] == [
        ("/.well-known/security.txt", "ok", None), ("/robots.txt", "error", "timeout"),
    ]


def test_ct_names_cannot_widen_scope_past_the_apex(approved, network, monkeypatch):
    monkeypatch.setattr(dc, "MAX_SUBDOMAINS", 2)
    evidence = dc.collect(PAGE, PROJECT)
    probed = [n.name for n in evidence.names]
    assert len([n for n in evidence.names if n.origin == "certificate_transparency"]) == 2
    assert "evil.example.org" not in probed and "not a domain" not in probed and "a_b.example.com" not in probed


def test_multilabel_suffix_apex_comes_from_the_soa_walk(approved, network, monkeypatch):
    page = "https://shop.example.co.uk/"
    monkeypatch.setenv("BASIRA_APPROVED_WEBSITE_PAGES", json.dumps({PROJECT: [page]}))

    def doh(name, record_type):
        network.calls.append(("doh", name, record_type))
        if record_type == "SOA":
            return {"Status": 0, "Answer": [{"type": 6, "data": "ns"}]} if name == "example.co.uk" else {"Status": 3}
        return {"Status": 0, "Answer": [{"type": 1, "data": PUBLIC}]} if record_type == "A" else {"Status": 0}

    monkeypatch.setattr(dc, "_doh_query", doh)
    monkeypatch.setattr(dc, "_ct_names", lambda apex: network.calls.append(("ct", apex)) or set())
    evidence = dc.collect(page, PROJECT)
    assert evidence.apex == "example.co.uk" and ("ct", "example.co.uk") in network.calls
    assert ("doh", "co.uk", "SOA") not in network.calls


@pytest.mark.parametrize("value,expected", [
    ("www.example.com", "www.example.com"),
    ("*.API.Example.Com.", "api.example.com"),
    ("example.com", "example.com"),
    ("evil.example.org", None),
    ("example.com.evil.org", None),
    ("not a domain", None),
    ("a_b.example.com", None),
    ("-bad.example.com", None),
    ("", None),
    (".".join(["a"] * 13) + ".example.com", None),
])
def test_in_scope_name(value, expected):
    assert dc._in_scope_name(value, "example.com") == expected


@pytest.mark.parametrize("value,public", [
    ("93.184.216.34", True), ("8.8.8.8", True),
    ("10.0.0.1", False), ("127.0.0.1", False), ("169.254.169.254", False),
    ("192.168.1.1", False), ("172.16.0.1", False), ("100.64.0.1", False), ("224.0.0.1", False),
    ("::ffff:127.0.0.1", False), ("::1", False), ("fe80::1", False), ("fc00::1", False),
    ("2002::1", False), ("2001:db8::1", False), ("2606:4700:4700::1111", True), ("garbage", False), ("", False),
])
def test_public_split(value, public):
    addresses, non_public = dc._public_split([value])
    assert (addresses == [value]) == public and non_public == (0 if public else 1)


def test_doh_uses_only_the_fixed_resolver_and_validates_the_payload(monkeypatch):
    seen = []

    def fake_get(host, path, max_bytes):
        seen.append((host, path, max_bytes))
        return 200, b'{"Status": 0, "Answer": []}'

    monkeypatch.setattr(dc, "_https_get", fake_get)
    assert dc._doh_query("example.com", "SOA") == {"Status": 0, "Answer": []}
    assert seen == [("dns.google", "/resolve?name=example.com&type=6", dc.MAX_DNS_BYTES)]

    for bad in (b"not json", b"[1]", b'{"Status": "0"}'):
        monkeypatch.setattr(dc, "_https_get", lambda host, path, max_bytes, body=bad: (200, body))
        with pytest.raises(dc.FetchError) as failed:
            dc._doh_query("example.com", "A")
        assert failed.value.reason == "dns_error"


def test_ct_search_requires_a_200_json_list(monkeypatch):
    monkeypatch.setattr(dc, "_https_get", lambda host, path, max_bytes: (500, b""))
    with pytest.raises(dc.FetchError) as failed:
        dc._ct_names("example.com")
    assert failed.value.reason == "ct_error"

    monkeypatch.setattr(dc, "_https_get", lambda host, path, max_bytes: (200, b'{"oops": 1}'))
    with pytest.raises(dc.FetchError) as failed:
        dc._ct_names("example.com")
    assert failed.value.reason == "ct_error"


def test_ct_rows_are_capped_and_multivalue_rows_split(monkeypatch):
    rows = [{"name_value": "a.example.com\nb.example.com"}, {"name_value": 42}, "junk"]
    rows += [{"name_value": f"n{i}.example.com"} for i in range(dc.MAX_CT_NAMES + 50)]
    monkeypatch.setattr(dc, "_https_get", lambda host, path, max_bytes: (200, json.dumps(rows).encode()))
    names = dc._ct_names("example.com")
    assert {"a.example.com", "b.example.com"} <= names
    assert len(names) == 2 + (dc.MAX_CT_NAMES - 3)  # the slice keeps the first MAX_CT_NAMES rows only


def test_a_fixed_endpoint_that_resolves_private_is_a_connect_error(monkeypatch):
    monkeypatch.setattr(dc, "validated_address", lambda host: (_ for _ in ()).throw(InputError("x")))
    with pytest.raises(dc.FetchError) as failed:
        dc._https_get("dns.google", "/resolve?name=example.com&type=1", 100)
    assert failed.value.reason == "connect_error"


def test_unknown_reason_codes_are_rejected():
    with pytest.raises(ValueError):
        dc.FetchError("some free text from a network error")
