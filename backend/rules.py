"""Local, source-only rule registry and redacted HTML evidence adapter."""

from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urlsplit


CDNS = frozenset({"cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"})


@dataclass(frozen=True)
class HtmlElement:
    group: str
    line: int
    has_url: bool
    http: bool
    cdn_host: str | None
    integrity: bool


@dataclass(frozen=True)
class Rule:
    id: str
    group: str
    severity: str
    title: str
    title_ar: str
    remediation: str
    remediation_ar: str
    applicable: Callable[[HtmlElement], bool]
    matches: Callable[[HtmlElement], bool]
    evidence: Callable[[HtmlElement], str]
    domain: str = "html"

    def finding(self, element: HtmlElement):
        return {
            "rule": self.id,
            "domain": self.domain,
            "severity": self.severity,
            "confidence": "high",
            "assessment": "observed",
            "line": element.line,
            "evidence": self.evidence(element),
            "title": self.title,
            "title_ar": self.title_ar,
            "remediation": self.remediation,
            "remediation_ar": self.remediation_ar,
        }


RULES = {
    rule.id: rule
    for rule in (
        Rule("http-script", "scripts", "high", "Script loaded over HTTP", "تحميل سكربت عبر HTTP",
             "Serve this script over HTTPS.", "استخدم HTTPS لتحميل السكربت.",
             lambda e: e.has_url, lambda e: e.http, lambda e: '<script src="http://…">'),
        Rule("http-form", "forms", "medium", "Form submits over HTTP", "إرسال نموذج عبر HTTP",
             "Change the form destination to HTTPS.", "استخدم HTTPS لوجهة إرسال النموذج.",
             lambda e: e.has_url, lambda e: e.http, lambda e: '<form action="http://…">'),
        Rule("cdn-integrity", "scripts", "low", "CDN script lacks an integrity attribute",
             "سكربت CDN بدون بصمة سلامة", "Pin the asset version and add its verified integrity digest.",
             "ثبّت إصدار السكربت وأضف بصمة سلامة موثوقة في خاصية integrity.",
             lambda e: e.cdn_host is not None, lambda e: not e.integrity,
             lambda e: f'<script src="//{e.cdn_host}/…"> [integrity absent or blank]'),
    )
}


class SourceIndex(HTMLParser):
    CDATA_CONTENT_ELEMENTS = ("script", "style", "textarea", "title", "xmp", "iframe",
                              "noembed", "noframes", "noscript")

    def __init__(self, source: str):
        super().__init__()
        self.tags = 0
        self.profiles = {"scripts": Counter(), "forms": Counter()}
        self.applicable = set()
        self.evidence = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if tag not in ("script", "form"):
            return
        attrs = dict(reversed(attrs))
        group, url_attr = ("scripts", "src") if tag == "script" else ("forms", "action")
        raw_url = (attrs.get(url_attr) or "").strip()
        try:
            url = urlsplit(raw_url)
            host = url.hostname
            http = url.scheme == "http" and bool(host)
        except ValueError:
            host, http = None, False
        element = HtmlElement(
            group=group, line=self.getpos()[0], has_url=bool(raw_url), http=http,
            cdn_host=host if host in CDNS else None,
            integrity=bool((attrs.get("integrity") or "").strip()),
        )
        self.profiles[group][(element.http, element.cdn_host is not None, element.integrity)] += 1
        for rule in RULES.values():
            if rule.group == group and rule.applicable(element):
                self.applicable.add(rule.id)
                if rule.matches(element):
                    self.evidence.append(rule.finding(element))

    def coverage(self):
        matches = Counter(item["rule"] for item in self.evidence)
        return [
            {
                "rule": rule.id,
                "domain": rule.domain,
                "status": "matched" if matches[rule.id] else
                          "clear" if rule.id in self.applicable else "not_applicable",
                "match_count": matches[rule.id],
            }
            for rule in RULES.values()
        ]
