"""Offline review of explicitly supplied HTML text and HAR response captures."""

import base64
import binascii
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import PurePosixPath
import re
from urllib.parse import urljoin, urlsplit

from ..rules import CDNS
from .markers import Incomplete, missing


HTML_IDS = tuple(f"HTML-{i:02}" for i in range(4, 11))
WEB_IDS = tuple(f"WEB-{i:02}" for i in range(1, 11))
REFERRER_POLICIES = frozenset({
    "no-referrer", "no-referrer-when-downgrade", "origin", "origin-when-cross-origin",
    "same-origin", "strict-origin", "strict-origin-when-cross-origin", "unsafe-url",
})
CSP_DIRECTIVES = frozenset({
    "base-uri", "child-src", "connect-src", "default-src", "font-src", "form-action",
    "frame-ancestors", "frame-src", "img-src", "manifest-src", "media-src", "object-src",
    "report-to", "report-uri", "require-trusted-types-for", "sandbox", "script-src",
    "script-src-attr", "script-src-elem", "style-src", "style-src-attr", "style-src-elem",
    "trusted-types", "upgrade-insecure-requests", "worker-src",
})
META_UNSUPPORTED = frozenset({"frame-ancestors", "report-uri", "report-to", "sandbox"})
HTML_MIME = frozenset({"text/html", "application/xhtml+xml"})
TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9a-zA-Z-]+")
RELEVANT_TAGS = frozenset({"base", "button", "iframe", "input", "link", "meta", "script"})
RULE_TEXT = {
    "HTML-04": ("low", "CDN stylesheet lacks SRI", "ملف CSS من CDN من غير SRI",
                "Pin the asset and publish a verified integrity digest.", "ثبّت إصدار الملف وأضف بصمة سلامة متحقّقة."),
    "HTML-05": ("low", "Invalid SRI digest syntax", "صيغة بصمة SRI غير صالحة",
                "Use a verified SHA-256, SHA-384 or SHA-512 digest for the exact asset.",
                "استخدم بصمة SHA-256 أو SHA-384 أو SHA-512 متحقّقة لنفس الملف."),
    "HTML-06": ("medium", "Form override submits over HTTP", "زر إرسال يوجّه النموذج إلى HTTP",
                "Use HTTPS for the submit control's formaction.", "استخدم HTTPS في خاصية formaction."),
    "HTML-07": ("medium", "iframe uses HTTP", "إطار iframe يستخدم HTTP",
                "Serve the frame content over HTTPS.", "قدّم محتوى الإطار عبر HTTPS."),
    "HTML-08": ("medium", "Stylesheet uses HTTP", "ملف CSS يستخدم HTTP",
                "Serve the stylesheet over HTTPS.", "قدّم ملف CSS عبر HTTPS."),
    "HTML-09": ("medium", "Meta refresh redirects to HTTP", "إعادة توجيه meta إلى HTTP",
                "Use an HTTPS destination for this redirect.", "استخدم وجهة HTTPS لإعادة التوجيه."),
    "HTML-10": ("low", "External iframe lacks sandbox", "إطار خارجي من غير sandbox",
                "Review the integration and enable the minimum sandbox permissions it needs.",
                "راجع التكامل وفعّل أقل صلاحيات sandbox يحتاجها الإطار."),
    "WEB-01": ("medium", "HSTS is missing or disabled", "إعداد HSTS غايب أو متوقّف",
               "Set an appropriate positive HSTS max-age on your HTTPS responses.",
               "اضبط مدة HSTS على قيمة موجبة مناسبة في استجابات HTTPS."),
    "WEB-02": ("medium", "Enforcing CSP is missing", "سياسة CSP نافذة غايبة",
               "Deploy an enforced Content Security Policy appropriate to the document.",
               "طبّق سياسة CSP نافذة ومناسبة للمستند."),
    "WEB-03": ("medium", "Effective CSP permits unsafe-inline", "سياسة CSP بتسمح بسكربتات inline",
               "Move inline scripts to controlled resources or use appropriate hashes or nonces.",
               "انقل السكربتات لموارد مضبوطة أو استخدم بصمات أو nonces مناسبة."),
    "WEB-04": ("medium", "Effective CSP permits unsafe-eval", "سياسة CSP بتسمح بالتقييم الديناميكي",
               "Remove the unsafe-eval directive value after reviewing runtime dependencies.",
               "شيل unsafe-eval بعد مراجعة الاعتماديات اللي بتستخدمه وقت التشغيل."),
    "WEB-05": ("medium", "Frame protection is missing", "حماية التأطير غايبة",
               "Restrict embedding with frame-ancestors or an appropriate X-Frame-Options policy.",
               "قيّد التضمين بـframe-ancestors أو بسياسة X-Frame-Options مناسبة."),
    "WEB-06": ("low", "Content type sniffing protection is missing", "حماية تخمين نوع المحتوى غايبة",
               "Set X-Content-Type-Options to nosniff on application responses.",
               "اضبط X-Content-Type-Options على nosniff في استجابات التطبيق."),
    "WEB-07": ("low", "Referrer policy is unsafe-url", "سياسة Referrer مضبوطة على unsafe-url",
               "Choose a policy that limits cross-origin path and query disclosure.",
               "اختار سياسة بتحدّ من كشف المسار والاستعلام للأصول الخارجية."),
    "WEB-08": ("medium", "Private response permits shared caching", "استجابة خاصة بتسمح بالتخزين المشترك",
               "Use private or no-store as appropriate and review shared cache settings.",
               "اضبط private أو no-store حسب الحالة وراجع إعدادات التخزين المشترك."),
    "WEB-09": ("medium", "Session cookie lacks Secure", "كوكي الجلسة من غير Secure",
               "Add Secure to the configured session cookie on HTTPS responses.",
               "أضف Secure لكوكي الجلسة في استجابات HTTPS."),
    "WEB-10": ("medium", "Session cookie lacks HttpOnly", "كوكي الجلسة من غير HttpOnly",
               "Add HttpOnly to the configured session cookie.",
               "أضف HttpOnly لكوكي الجلسة المحددة."),
}


class Document(HTMLParser):
    CDATA_CONTENT_ELEMENTS = (
        "script", "style", "textarea", "title", "xmp", "iframe", "noembed", "noframes", "noscript",
    )

    def __init__(self, content):
        super().__init__()
        self.tags = []
        self.form_ids = {}
        self.form = None
        self.head = True
        self.template_depth = 0
        self.feed(content)
        self.close()

    def handle_starttag(self, tag, pairs):
        if tag == "template":
            self.template_depth += 1
        if self.template_depth:
            return
        attrs = dict(reversed(pairs))
        if tag == "body" or tag not in {"html", "head", "base", "link", "meta", "title", "style", "script", "noscript"}:
            self.head = False
        if tag == "form" and self.form is None:
            self.form = attrs
            if attrs.get("id"):
                self.form_ids.setdefault(attrs["id"], attrs)
        if tag in RELEVANT_TAGS:
            self.tags.append((tag, attrs, self.getpos()[0], self.head, self.form))

    def handle_endtag(self, tag):
        if self.template_depth:
            if tag == "template":
                self.template_depth -= 1
            return
        if tag == "form":
            self.form = None
        if tag == "head":
            self.head = False

    def handle_data(self, data):
        if data.strip() and not self.cdata_elem and not self.template_depth:
            self.head = False


def parse_document(content):
    try:
        return Document(content)
    except (ValueError, AssertionError):
        return None


def parsed_url(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        url = urlsplit(value)
        _ = url.port
        return url if url.hostname else None
    except ValueError:
        return None


def url_origin(url):
    if url and url.scheme in {"http", "https"}:
        port = url.port if url.port is not None else (443 if url.scheme == "https" else 80)
        return url.scheme, url.hostname, port
    return None


def resolve_url(base, raw):
    try:
        return parsed_url(urljoin(base, raw))
    except ValueError:
        return None


def policy_strings(policy, key):
    values = policy.get(key)
    return {value for value in values if isinstance(value, str)} if isinstance(values, list) else set()


def record(results, rule, path, line, evidence=None, *, contextual=False):
    if results[rule] is None or isinstance(results[rule], Incomplete):
        results[rule] = []
    if evidence is not None:
        severity, title, title_ar, remediation, remediation_ar = RULE_TEXT[rule]
        results[rule].append({
            "path": path, "line": line, "evidence": evidence, "severity": severity,
            "title": title, "title_ar": title_ar, "remediation": remediation, "remediation_ar": remediation_ar,
            "confidence": "medium" if contextual else "high",
            "assessment": "review_required" if contextual else "observed",
        })


def points_to_http(value):
    url = parsed_url(value.strip())
    return bool(url and url.scheme == "http")


def supported_digest(value):
    lengths = {"sha256": 32, "sha384": 48, "sha512": 64}
    for item in value.split():
        digest, _, _ = item.partition("?")
        algorithm, _, written = digest.partition("-")
        if algorithm not in lengths or not re.fullmatch(r"[A-Za-z0-9+/_-]+={0,2}", written):
            continue
        try:
            decoded = base64.b64decode(written + "=" * (-len(written) % 4), altchars=b"-_", validate=True)
        except (binascii.Error, ValueError):
            continue
        if len(decoded) == lengths[algorithm]:
            return True
    return False


def submit_override(document, tag, attrs, form):
    if tag not in {"button", "input"} or "formaction" not in attrs or "disabled" in attrs:
        return False
    kind = (attrs.get("type") or "").lower()
    if tag == "input":
        if kind not in {"submit", "image"}:
            return False
    elif kind in {"reset", "button"} or (kind != "submit" and ("command" in attrs or "commandfor" in attrs)):
        return False
    form = document.form_ids.get(attrs.get("form")) if "form" in attrs else form
    if form is None:
        return False
    return (attrs.get("formmethod") or form.get("method") or "").lower() != "dialog"


def html_checks(results, text_inputs, policy):
    base = policy.get("base_url") or ""
    base_url = parsed_url(base)
    origin = url_origin(base_url)
    https = origin is not None and origin[0] == "https"
    frame_exempt = {url_origin(parsed_url(value)) for value in policy_strings(policy, "frame_origins_allowlist")}
    for path, content in text_inputs.items():
        if PurePosixPath(path).suffix.lower() not in {".html", ".htm"}:
            continue
        document = parse_document(content)
        if document is None:
            continue
        effective_base = base if origin else ""
        for tag, attrs, _, head, _ in document.tags:
            if tag == "base" and head and "href" in attrs:
                first_base = resolve_url(effective_base, attrs.get("href") or "")
                if url_origin(first_base):
                    effective_base = first_base.geturl()
                break
        for tag, attrs, line, _, form in document.tags:
            stylesheet = tag == "link" and "stylesheet" in (attrs.get("rel") or "").lower().split()
            if stylesheet or tag == "script":
                value = (attrs.get("href" if stylesheet else "src") or "").strip()
                asset = resolve_url(effective_base, value) if value else None
                sri = (attrs.get("integrity") or "").strip()
                resource_eligible = eligible_resource(value)
                if stylesheet and resource_eligible and asset and asset.hostname in CDNS:
                    record(results, "HTML-04", path, line, None if sri else "CDN stylesheet has no integrity metadata.")
                if resource_eligible and sri:
                    record(results, "HTML-05", path, line,
                           None if supported_digest(sri) else "No supported, structurally valid SRI digest.")
                if stylesheet and https and value:
                    record(results, "HTML-08", path, line,
                           "Stylesheet href explicitly uses HTTP." if points_to_http(value) else None)
            if submit_override(document, tag, attrs, form):
                value = attrs.get("formaction") or ""
                record(results, "HTML-06", path, line,
                       "Submit control overrides its form action with an HTTP destination." if points_to_http(value) else None)
            if tag == "iframe" and "srcdoc" not in attrs and (value := (attrs.get("src") or "").strip()):
                if https:
                    record(results, "HTML-07", path, line,
                           "iframe src explicitly uses HTTP." if points_to_http(value) else None)
                frame_origin = url_origin(resolve_url(effective_base, value))
                if origin and frame_origin and frame_origin != origin and frame_origin not in frame_exempt:
                    record(results, "HTML-10", path, line,
                           "External iframe lacks sandbox." if "sandbox" not in attrs else None, contextual=True)
            if https and tag == "meta" and (attrs.get("http-equiv") or "").lower() == "refresh":
                refresh = re.match(r"\s*\d+(?:\.\d+)?\s*[;,](.*)$", attrs.get("content") or "", flags=re.DOTALL)
                if refresh:
                    target = re.sub(r"^url\s*=\s*", "", refresh[1].strip(), flags=re.IGNORECASE)
                    if target := target.strip().strip("'\""):
                        record(results, "HTML-09", path, line,
                               "Meta refresh explicitly points to HTTP." if points_to_http(target) else None)


def eligible_resource(value):
    try:
        resource = urlsplit(value)
        _ = resource.port
        if resource.scheme or value.startswith("//"):
            return resource.scheme in {"", "http", "https"} and bool(resource.hostname)
        return bool(value)
    except ValueError:
        return False


def parse_csp(value, *, meta=False):
    directives = {}
    for clause in value.split(";"):
        words = clause.split()
        if not words:
            continue
        name, *arguments = words
        directive = name.lower()
        if directive in CSP_DIRECTIVES and (not meta or directive not in META_UNSUPPORTED):
            directives.setdefault(directive, arguments)
    return directives


def captured_policies(content):
    text = content.get("text")
    if not isinstance(text, str):
        return None
    if content.get("encoding") == "base64":
        try:
            text = base64.b64decode(text, validate=True).decode("utf-8")
        except (ValueError, binascii.Error):
            return None
    elif content.get("encoding") not in (None, ""):
        return None
    size = content.get("size")
    if type(size) is int and size > len(text.encode("utf-8", errors="replace")):
        return None
    document = parse_document(text)
    if document is None:
        return None
    return [
        parsed
        for tag, attrs, _, head, _ in document.tags
        if head and tag == "meta" and (attrs.get("http-equiv") or "").lower() == "content-security-policy"
        if (parsed := parse_csp(attrs.get("content") or "", meta=True))
    ]


def script_sources(policy, override=None):
    for key in (override, "script-src", "default-src"):
        if key in policy:
            return policy[key]
    return None


def permits_inline(source):
    if source is None:
        return True
    keywords = [token.lower() for token in source]
    restrictive = any(
        token == "'strict-dynamic'" or re.fullmatch(r"'(?:nonce|sha256|sha384|sha512)-[a-z0-9+/_=-]+'", token)
        for token in keywords
    )
    return "'unsafe-inline'" in keywords and not restrictive


def permits_eval(source):
    return source is None or any(token.lower() == "'unsafe-eval'" for token in source)


def header_map(entries):
    headers = defaultdict(list)
    complete_items = True
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("value"), str):
            complete_items = False
            continue
        headers[item["name"].casefold()].append(item["value"].strip())
    return headers, complete_items


def parse_directives(values, delimiter):
    for value in values:
        for chunk in split_quoted(value, delimiter):
            key, separator, raw = chunk.strip().partition("=")
            if TOKEN.fullmatch(key.strip()):
                yield key.strip().lower(), raw.strip().strip('"') if separator else None


def split_quoted(value, delimiter):
    start = 0
    quoted = escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == delimiter and not quoted:
            yield value[start:index]
            start = index + 1
    yield value[start:]


def bad_hsts(values):
    if not values:
        return True
    max_ages = [argument for key, argument in parse_directives(values[:1], ";") if key == "max-age"]
    return bool(len(max_ages) == 1 and max_ages[0] and re.fullmatch("0+", max_ages[0]))


def has_frame_protection(csp, xfo):
    ancestors = [p["frame-ancestors"] for p in csp if "frame-ancestors" in p]
    if ancestors:
        return any("*" not in sources for sources in ancestors)
    options = {option.strip().upper() for value in xfo for option in value.split(",")}
    return options in ({"DENY"}, {"SAMEORIGIN"})


def private_cache_shared(values):
    directives = list(parse_directives(values, ","))
    if ("private", None) in directives or ("no-store", None) in directives:
        return False
    if ("public", None) in directives:
        return True
    ages = [age for directive, age in directives if directive == "s-maxage"]
    return bool(len(ages) == 1 and ages[0] and re.fullmatch(r"0*[1-9]\d*", ages[0], flags=re.ASCII))


def unmeasured(results, rule, marker):
    """A rule whose evidence needs a complete capture; the scan reports it as skipped."""
    if results[rule] is None:
        results[rule] = marker


def har_checks(results, har, policy):
    log = har.get("log") if isinstance(har, dict) else None
    entries = log.get("entries") if isinstance(log, dict) else None
    if not isinstance(entries, list):
        return
    managed_hosts = {value.lower() for value in policy_strings(policy, "managed_hosts")}
    if (base := parsed_url(policy.get("base_url"))) and not managed_hosts:
        managed_hosts.add(base.hostname)
    private_paths = policy_strings(policy, "private_paths")
    session_names = {name for name in policy_strings(policy, "session_cookie_names") if TOKEN.fullmatch(name)}
    for ordinal, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            continue
        request, response = item.get("request"), item.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            continue
        url = parsed_url(request.get("url"))
        status, raw_headers = response.get("status"), response.get("headers")
        if not url_origin(url) or type(status) is not int or not (200 <= status <= 599) or not isinstance(raw_headers, list):
            continue
        if managed_hosts and url.hostname not in managed_hosts:
            continue
        headers, complete_items = header_map(raw_headers)
        complete = policy.get("har_headers_complete") is True and complete_items
        https = url.scheme == "https"
        final = not 300 <= status < 400
        content = response.get("content")
        if not isinstance(content, dict):
            content = {}
        mime = headers["content-type"][-1] if headers["content-type"] else content.get("mimeType")
        html = isinstance(mime, str) and mime.split(";", 1)[0].strip().lower() in HTML_MIME
        csp = [parsed for value in headers["content-security-policy"] for part in value.split(",")
               if (parsed := parse_csp(part))] if html else []
        meta = captured_policies(content) if html else None
        policies = csp + (meta or [])

        def assess(rule, failed, fact, *, contextual=False):
            evidence = f"HAR response #{ordinal}: {fact}" if failed else None
            record(results, rule, "capture.har", 1, evidence, contextual=contextual)

        if https and final and url.hostname in managed_hosts:
            if complete or headers["strict-transport-security"]:
                assess("WEB-01", bad_hsts(headers["strict-transport-security"]), "HSTS is absent or max-age is zero.")
            else:
                unmeasured(results, "WEB-01", missing(complete))
        if html and final and policy.get("require_csp") is True:
            if policies or (complete and meta is not None):
                assess("WEB-02", not policies, "No enforcing CSP in the full header capture or valid head meta.")
            else:
                unmeasured(results, "WEB-02", missing(complete))
        if html and final and policies:
            inline = []
            for override in ("script-src-elem", "script-src-attr"):
                sources = [script_sources(p, override) for p in policies]
                if any(source is not None for source in sources):
                    inline.append((override, all(permits_inline(source) for source in sources)))
            unblocked = [override for override, allowed in inline if allowed]
            if inline and (complete and meta is not None or len(inline) == 2 and not unblocked):
                assess("WEB-03", bool(unblocked),
                       f"Effective enforcing CSP permits unsafe-inline via {', '.join(unblocked)}.", contextual=True)
            elif inline:
                unmeasured(results, "WEB-03", missing(complete))
            sources = [script_sources(p) for p in policies]
            if any(source is not None for source in sources):
                allowed = all(permits_eval(source) for source in sources)
                if not allowed or (complete and meta is not None):
                    assess("WEB-04", allowed, "Effective enforcing CSP permits unsafe-eval.", contextual=True)
                else:
                    unmeasured(results, "WEB-04", missing(complete))
        if html and final and policy.get("require_frame_protection") is True:
            if complete:
                assess("WEB-05", not has_frame_protection(csp, headers["x-frame-options"]),
                       "No restrictive frame-ancestors or applicable X-Frame-Options.")
            else:
                unmeasured(results, "WEB-05", missing(complete))
        if final and url.hostname in managed_hosts:
            if complete:
                assess("WEB-06", [v.lower() for v in headers["x-content-type-options"]] != ["nosniff"],
                       "X-Content-Type-Options does not supply a single nosniff value.")
            else:
                unmeasured(results, "WEB-06", missing(complete))
        if html and final:
            if complete and headers["referrer-policy"]:
                valid = [value.strip().lower() for field in headers["referrer-policy"] for value in field.split(",")
                         if value.strip().lower() in REFERRER_POLICIES]
                if valid:
                    assess("WEB-07", valid[-1] == "unsafe-url", "Effective Referrer-Policy header is unsafe-url.")
            elif not complete:
                unmeasured(results, "WEB-07", missing(complete))
        if final and url.path in private_paths:
            if complete:
                assess("WEB-08", private_cache_shared(headers["cache-control"]),
                       "A configured private route explicitly allows shared caching.", contextual=True)
            else:
                unmeasured(results, "WEB-08", missing(complete))
        for value in headers["set-cookie"]:
            cookie, *attributes = value.split(";")
            name, separator, _ = cookie.strip().partition("=")
            name = name.strip()
            if not separator or name not in session_names:
                continue
            flags = {attribute.partition("=")[0].strip().lower() for attribute in attributes}
            if https:
                assess("WEB-09", "secure" not in flags, f"Configured session cookie {name} lacks Secure.")
            assess("WEB-10", "httponly" not in flags, f"Configured session cookie {name} lacks HttpOnly.")


def check(text_inputs, har, policy, advisories):
    results = dict.fromkeys((*HTML_IDS, *WEB_IDS))
    html_checks(results, text_inputs, policy)
    har_checks(results, har, policy)
    return results
