"""Extra local checks for HTML and submitted HAR data."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from urllib.parse import SplitResult

from .markers import Incomplete, missing
from .web import (
    Document, HTML_MIME, TOKEN, header_map, parsed_url, points_to_http, policy_strings,
    private_cache_shared, resolve_url, split_quoted, supported_digest, url_origin,
)


HTML_IDS = tuple(f"HTML-{number:02}" for number in range(11, 21))
WEB_IDS = tuple(f"WEB-{number:02}" for number in range(11, 26))
SENSITIVE_FEATURES = frozenset({"camera", "microphone", "geolocation"})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
CLASSIC_SCRIPT_TYPES = frozenset({
    "", "application/ecmascript", "application/javascript", "application/x-ecmascript",
    "application/x-javascript", "text/ecmascript", "text/javascript", "text/javascript1.0",
    "text/javascript1.1", "text/javascript1.2", "text/javascript1.3", "text/javascript1.4",
    "text/javascript1.5", "text/jscript", "text/livescript", "text/x-ecmascript", "text/x-javascript",
})
PRODUCT_VERSION = re.compile(r"(?:^|\s)[A-Za-z][A-Za-z0-9_.-]*/v?\d+(?:\.\d+)+(?:\s|$|[;(])")
JSON_MIME = re.compile(r"application/(?:json|[!#$%&'*+.^_`|~0-9a-z-]+\+json)")
STRUCTURED_PARAMETER = re.compile(r'[a-z*][a-z0-9_.*-]*(?:=(?:"(?:[^"\\]|\\["\\])*"|[^\s",;]+))?')
PERMISSION_ITEM = re.compile(r'\*|self|"[^"\r\n]+"')
PERMISSION_LIST = re.compile(rf'(?:{PERMISSION_ITEM.pattern})(?: +(?:{PERMISSION_ITEM.pattern}))*')
SPEC = {
    "HTML-11": ("medium", "Cross-origin SRI resource lacks CORS mode", "مورد خارجي بـSRI من غير وضع CORS",
                "Set an appropriate crossorigin mode and verify CORS on the asset host.",
                "اضبط وضع crossorigin المناسب وتحقق من سياسة CORS لمضيف المورد."),
    "HTML-12": ("medium", "External new tab explicitly retains its opener", "تبويب خارجي بيحتفظ بالصفحة اللي فتحته",
                "Remove the opener relationship or explicitly use rel=noopener.",
                "شيل علاقة opener أو استخدم rel=noopener."),
    "HTML-13": ("medium", "Same-origin sandbox combines scripts and origin access", "عزل إطار من نفس الأصل بيسمح بالسكريبتات والأصل",
                "Separate the frame to a dedicated origin or remove a sandbox capability.",
                "انقل الإطار لأصل منفصل أو شيل إحدى صلاحيات sandbox."),
    "HTML-14": ("low", "Media URL explicitly uses HTTP", "رابط وسائط مكتوب بصيغة HTTP صريحة",
                "Use HTTPS for the declared media URL.", "استخدم HTTPS للوسائط المصرّح بيها."),
    "HTML-15": ("medium", "Document base changes the resource origin", "عنوان base بيغيّر أصل الموارد",
                "Keep the document base on its own origin or review the deliberate exception.",
                "خلّي عنوان base من نفس أصل الصفحة أو راجع الاستثناء المقصود."),
    "HTML-16": ("low", "Hyperlink audit sends a third-party ping", "الرابط بيعلن إرسال ping لطرف خارجي",
                "Remove the external ping or use a policy-approved destination.",
                "شيل الـping الخارجي أو استخدم وجهة توافق سياسة المشروع."),
    "HTML-17": ("high", "Password named control can submit through GET", "حقل كلمة مرور له اسم وبيتبع نموذج GET",
                "Set the form to POST over HTTPS and review submit controls.",
                "اضبط النموذج على POST عبر HTTPS وراجع أزرار الإرسال."),
    "HTML-18": ("medium", "Password control is prefilled in source", "حقل كلمة المرور فيه قيمة مكتوبة في المصدر",
                "Remove the password value from server-rendered markup.",
                "شيل قيمة كلمة المرور من الـHTML اللي بيتولّد على السيرفر."),
    "HTML-19": ("low", "Connection hint names a third-party origin", "تلميح الاتصال مكتوب لأصل خارجي",
                "Limit preconnect and dns-prefetch to origins approved by your privacy policy.",
                "قيّد preconnect وdns-prefetch بالأصول المسموح بيها في سياسة الخصوصية."),
    "HTML-20": ("medium", "External frame requests sensitive capability delegation", "إطار خارجي بيطلب تفويض صلاحية حساسة",
                "Limit camera, microphone and geolocation delegation to trusted integrations.",
                "اقصر تفويض الكاميرا والمايك والموقع على التكاملات الموثوقة."),
    "WEB-11": ("medium", "Session cookie lacks a valid explicit SameSite value", "كوكي الجلسة من غير SameSite صريحة وصالحة",
               "Set the SameSite value appropriate to the session flow.",
               "اضبط SameSite على القيمة المناسبة لمسار الجلسة."),
    "WEB-12": ("medium", "Session cookie violates the host-only policy", "كوكي الجلسة بتخالف سياسة المضيف فقط",
               "Omit the Domain attribute for cookies intended to be host-only.",
               "شيل Domain من الكوكي اللي المفروض تقتصر على المضيف."),
    "WEB-13": ("medium", "Credentialed CORS origin is outside policy", "أصل CORS ببيانات اعتماد خارج السياسة",
               "Limit credentialed CORS to the origins in the approved policy.",
               "اقصر CORS ببيانات اعتماد على الأصول المعتمدة."),
    "WEB-14": ("medium", "Cacheable origin-varying CORS lacks Vary", "استجابة CORS قابلة للتخزين بتتغير حسب Origin من غير Vary",
               "Send Vary: Origin for origin-dependent shared responses.",
               "استخدم Vary: Origin لما الاستجابة المشتركة تعتمد على الأصل."),
    "WEB-15": ("medium", "COOP misses cross-origin isolation policy", "قيمة COOP بتخالف سياسة عزل الأصول",
               "Set Cross-Origin-Opener-Policy to same-origin on documents that require isolation.",
               "اضبط Cross-Origin-Opener-Policy على same-origin للمستندات اللي تتطلب العزل."),
    "WEB-16": ("medium", "COEP misses cross-origin isolation policy", "قيمة COEP بتخالف سياسة عزل الأصول",
               "Set Cross-Origin-Embedder-Policy to require-corp or credentialless as appropriate.",
               "اضبط Cross-Origin-Embedder-Policy على require-corp أو credentialless حسب الحالة."),
    "WEB-17": ("medium", "CORP is ineffective for a protected resource", "سياسة CORP للمورد المحمي أوسع من المطلوب",
               "Set Cross-Origin-Resource-Policy to the protection required for this path.",
               "اضبط Cross-Origin-Resource-Policy بالمستوى المطلوب للمسار ده."),
    "WEB-18": ("medium", "Permissions-Policy delegates a sensitive feature to any origin", "سياسة Permissions-Policy بتفوّض صلاحية حساسة لأي أصل",
               "Use an explicit allowlist or deny the feature.",
               "استخدم قائمة سماح صريحة أو امنع الصلاحية."),
    "WEB-19": ("low", "Configured logout cleanup directive is missing", "استجابة الخروج من غير توجيه التنضيف المطلوب",
               "Apply the required Clear-Site-Data directives for this logout flow.",
               "طبّق توجيهات Clear-Site-Data المطلوبة لمسار الخروج."),
    "WEB-20": ("medium", "Untrusted download lacks attachment disposition", "تنزيل غير موثوق من غير وضع attachment",
               "Serve this configured download with Content-Disposition: attachment.",
               "قدّم التنزيل ده بـContent-Disposition: attachment."),
    "WEB-21": ("low", "Server header exposes a software version", "رأس الاستجابة بيكشف إصدار برنامج الخادم",
               "Remove unnecessary version details from Server and X-Powered-By.",
               "شيل تفاصيل الإصدار غير الضرورية من Server وX-Powered-By."),
    "WEB-22": ("medium", "Basic authentication is challenged over HTTP", "طلب Basic authentication على اتصال HTTP",
               "Offer Basic authentication only on HTTPS responses.",
               "استخدم Basic authentication في استجابات HTTPS فقط."),
    "WEB-23": ("medium", "HTTPS redirect points to HTTP", "إعادة توجيه من HTTPS إلى HTTP",
               "Set an HTTPS destination in the Location header.",
               "استخدم وجهة HTTPS في رأس Location."),
    "WEB-24": ("medium", "Service worker registration scope is too broad", "نطاق تسجيل Service Worker أوسع من المسموح",
               "Limit the allowed registration scope to the configured application directory.",
               "اقصر نطاق التسجيل على مجلد التطبيق المسموح."),
    "WEB-25": ("medium", "JSON endpoint supplies a different media type", "مسار JSON بيرجع نوع محتوى مختلف",
               "Return application/json or an appropriate application/*+json media type.",
               "اضبط النوع على application/json أو نوع application/*+json مناسب."),
}


class ExtraDocument(Document):
    def handle_starttag(self, tag, pairs):
        super().handle_starttag(tag, pairs)
        if not self.template_depth and tag in {"a", "area", "audio", "img", "video"}:
            self.tags.append((tag, dict(reversed(pairs)), self.getpos()[0], self.head, self.form))


def record(results, rule, path, line, evidence=None, *, contextual=False):
    if results[rule] is None or isinstance(results[rule], Incomplete):
        results[rule] = []
    if evidence is not None:
        severity, title, title_ar, remediation, remediation_ar = SPEC[rule]
        results[rule].append({
            "path": path, "line": line, "evidence": evidence, "severity": severity,
            "title": title, "title_ar": title_ar, "remediation": remediation, "remediation_ar": remediation_ar,
            "confidence": "medium" if contextual else "high",
            "assessment": "review_required" if contextual else "observed",
        })


def attr(attrs, name):
    return (attrs.get(name) or "").strip()


def linked_origin(base, raw):
    return url_origin(resolve_url(base, raw)) if raw else None


def trusted_origins(policy, key):
    return {origin for value in policy_strings(policy, key) if (origin := url_origin(parsed_url(value)))}


def document_base(document, base):
    for tag, attrs, line, in_head, _ in document.tags:
        if tag == "base" and in_head and "href" in attrs:
            resolved = resolve_url(base, attrs.get("href") or "")
            if url_origin(resolved):
                return resolved.geturl(), line
            break
    return base, None


def delegated_sensitive_features(value, frame_origin):
    delegated = set()
    seen = set()
    for directive in value.split(";"):
        tokens = directive.split()
        if not tokens or tokens[0] not in SENSITIVE_FEATURES or tokens[0] in seen:
            continue
        feature, *allowlist = tokens
        seen.add(feature)
        if not allowlist or any(
            item in {"*", "'src'"} or url_origin(parsed_url(item)) == frame_origin
            for item in allowlist
        ):
            delegated.add(feature)
    return delegated


def html_checks(results, files, policy):
    supplied_base = policy.get("base_url")
    document_origin = url_origin(parsed_url(supplied_base))
    complete_base = supplied_base if document_origin else ""
    base_exempt = trusted_origins(policy, "base_origins_allowlist")
    hints_exempt = trusted_origins(policy, "connection_hint_origins_allowlist")
    sensitive_frames_exempt = trusted_origins(policy, "sensitive_frame_origins_allowlist")
    for path, text in files.items():
        if PurePosixPath(path).suffix.lower() not in {".htm", ".html"}:
            continue
        try:
            document = ExtraDocument(text)
        except (ValueError, AssertionError):
            continue
        base, base_line = document_base(document, complete_base)
        if document_origin and base_line is not None:
            target = url_origin(parsed_url(base))
            off_origin = target != document_origin and target not in base_exempt
            record(results, "HTML-15", path, base_line,
                   "First effective base URL changes the document origin used for relative URLs."
                   if off_origin else None, contextual=True)
        for tag, attrs, line, _, form in document.tags:
            rel = set(attr(attrs, "rel").lower().split())
            stylesheet = tag == "link" and "stylesheet" in rel
            classic_script = tag == "script" and attr(attrs, "type").lower() in CLASSIC_SCRIPT_TYPES
            if document_origin and (stylesheet or classic_script) and supported_digest(attr(attrs, "integrity")):
                asset = linked_origin(base, attr(attrs, "href" if stylesheet else "src"))
                if asset and asset != document_origin:
                    record(results, "HTML-11", path, line,
                           "Cross-origin resource with validly shaped SRI has no crossorigin attribute."
                           if "crossorigin" not in attrs else None)
            if document_origin and tag in {"a", "area"}:
                target = linked_origin(base, attr(attrs, "href"))
                if target and target != document_origin and attr(attrs, "target").lower() == "_blank":
                    opener = "opener" in rel and not {"noopener", "noreferrer"} & rel
                    record(results, "HTML-12", path, line,
                           "Off-origin new tab explicitly opts into its opener relationship."
                           if opener else None, contextual=True)
                pings = {linked_origin(base, url) for url in attr(attrs, "ping").split()} - {None}
                if "href" in attrs and pings and policy.get("disallow_external_pings") is True:
                    record(results, "HTML-16", path, line,
                           "A hyperlink specifies an off-origin audit endpoint." if pings - {document_origin} else None)
            if tag == "iframe" and document_origin:
                target = document_origin if "srcdoc" in attrs else linked_origin(base, attr(attrs, "src"))
                if target == document_origin and "sandbox" in attrs:
                    flags = set(attr(attrs, "sandbox").lower().split())
                    weak = {"allow-scripts", "allow-same-origin"} <= flags
                    record(results, "HTML-13", path, line,
                           "Same-origin sandbox enables scripts and retains same-origin privileges."
                           if weak else None, contextual=True)
                if target and target != document_origin and "allow" in attrs:
                    features = delegated_sensitive_features(attr(attrs, "allow"), target)
                    if target in sensitive_frames_exempt:
                        features = set()
                    record(results, "HTML-20", path, line,
                           f"External iframe requests delegation for {', '.join(sorted(features))}."
                           if features else None, contextual=True)
            if document_origin and document_origin[0] == "https" and tag in {"img", "audio", "video"}:
                for attribute in (("src", "poster") if tag == "video" else ("src",)):
                    source = attr(attrs, attribute)
                    if linked_origin(base, source):
                        record(results, "HTML-14", path, line,
                               f"{tag} {attribute} explicitly uses HTTP." if points_to_http(source) else None)
            if tag == "input" and attr(attrs, "type").lower() == "password":
                owner = document.form_ids.get(attr(attrs, "form")) if "form" in attrs else form
                if owner is not None and attr(attrs, "name") and "disabled" not in attrs:
                    method = attr(owner, "method").lower()
                    record(results, "HTML-17", path, line,
                           "Named password control belongs to a form with effective default GET."
                           if method not in {"post", "dialog"} else None, contextual=True)
                record(results, "HTML-18", path, line,
                       "Password control has a nonempty literal value attribute."
                       if attrs.get("value") else None, contextual=True)
            if (tag == "link" and document_origin and policy.get("restrict_connection_hints") is True
                    and rel & {"preconnect", "dns-prefetch"}):
                target = linked_origin(base, attr(attrs, "href"))
                if target:
                    record(results, "HTML-19", path, line,
                           "Connection hint targets a third-party origin outside the privacy allowlist."
                           if target != document_origin and target not in hints_exempt else None)


@dataclass(frozen=True)
class Capture:
    ordinal: int
    url: SplitResult
    status: int
    headers: dict
    request_headers: dict
    method: str | None
    complete: bool
    mime: str

    @property
    def final(self):
        return not 300 <= self.status < 400

    @property
    def html(self):
        return self.mime.split(";", 1)[0].strip().lower() in HTML_MIME

    @property
    def representation(self):
        return self.status in {200, 201, 202, 203} and self.method != "HEAD"


def captures(har, policy):
    log = har.get("log") if isinstance(har, dict) else None
    entries = log.get("entries") if isinstance(log, dict) else None
    if not isinstance(entries, list):
        return
    managed = {value.lower() for value in policy_strings(policy, "managed_hosts")}
    base = parsed_url(policy.get("base_url"))
    if base and not managed:
        managed.add(base.hostname)
    for ordinal, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            continue
        request, response = item.get("request"), item.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            continue
        url = parsed_url(request.get("url"))
        status, fields = response.get("status"), response.get("headers")
        if (not url_origin(url) or managed and url.hostname not in managed
                or type(status) is not int or not 200 <= status <= 599 or not isinstance(fields, list)):
            continue
        headers, well_formed = header_map(fields)
        raw_request = request.get("headers")
        request_headers, _ = header_map(raw_request if isinstance(raw_request, list) else [])
        content = response.get("content")
        fallback_mime = content.get("mimeType") if isinstance(content, dict) else None
        mime = singleton(headers, "content-type") or fallback_mime
        method = request.get("method")
        yield Capture(ordinal, url, status, headers, request_headers, method if isinstance(method, str) else None,
                      well_formed and policy.get("har_headers_complete") is True,
                      mime if isinstance(mime, str) else "")


def singleton(headers, name):
    values = headers.get(name, [])
    return values[0] if len(values) == 1 else None


def has_measurement(capture, name):
    return capture.complete or singleton(capture.headers, name) is not None


def unmeasured(results, capture, rule):
    """A rule whose evidence needs a complete capture; the scan reports it as skipped."""
    if results[rule] is None:
        results[rule] = missing(capture.complete)


def compare_header(results, capture, rule, header, expected, fact, *, structured=False):
    if has_measurement(capture, header):
        value = singleton(capture.headers, header)
        if structured and value is not None:
            value = structured_value(value)
        assess(results, capture, rule, value not in expected, fact)
    else:
        unmeasured(results, capture, rule)


def assess(results, capture, rule, failed, fact, *, contextual=False):
    evidence = f"HAR response #{capture.ordinal}: {fact}" if failed else None
    record(results, rule, "capture.har", 1, evidence, contextual=contextual)


def cookies(headers, session_names):
    for field in headers.get("set-cookie", []):
        first, *attributes = field.split(";")
        name, has_value, _ = first.partition("=")
        name = name.strip()
        if not has_value or name not in session_names:
            continue
        parsed = {}
        for attribute in attributes:
            key, _, value = attribute.partition("=")
            parsed[key.strip().lower()] = value.strip()
        yield parsed


def serialized_origin(value):
    if value == "null":
        return "null"
    url = parsed_url(value)
    origin = url_origin(url)
    if (not origin or url.path or url.query or url.fragment or url.username is not None
            or not re.fullmatch(r"[a-zA-Z0-9.:-]+", url.hostname)):
        return None
    host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
    port = f":{origin[2]}" if origin[2] != (443 if origin[0] == "https" else 80) else ""
    serialized = f"{origin[0]}://{host}{port}"
    return serialized if serialized == value else None


def cors_checks(results, capture, policy, variants):
    origin = singleton(capture.headers, "access-control-allow-origin")
    allowed = policy.get("cors_credential_origins")
    if isinstance(allowed, list) and singleton(capture.headers, "access-control-allow-credentials") == "true":
        approved = {serialized_origin(value) for value in allowed if isinstance(value, str)}
        actual = serialized_origin(origin)
        if actual is not None or origin == "*":
            assess(results, capture, "WEB-13", actual is not None and actual not in approved,
                   "Credential-enabled CORS has an explicit origin outside the allowlist.", contextual=True)
    request_origin = singleton(capture.request_headers, "origin")
    if (capture.complete and capture.status == 200 and capture.method == "GET"
            and serialized_origin(request_origin) not in {None, "null"} and request_origin == origin
            and private_cache_shared(capture.headers.get("cache-control", []))):
        # The exact captured URL is an in-memory grouping key only.
        variants[capture.url.geturl()].append((request_origin, capture))


def structured_value(field):
    value, *parameters = split_quoted(field, ";")
    if len(list(split_quoted(value, ","))) == 1 and all(
        STRUCTURED_PARAMETER.fullmatch(parameter.strip()) for parameter in parameters
    ):
        return value.strip()
    return None


def permissions_wildcards(fields):
    clauses = {}
    for value in fields:
        for clause in split_quoted(value, ","):
            name, separator, setting = clause.partition("=")
            name = name.strip()
            if separator and name in SENSITIVE_FEATURES:
                value = structured_value(setting)
                if value is None:
                    return None
                if value.startswith("(") and value.endswith(")"):
                    inner = value[1:-1].strip()
                    if inner and not PERMISSION_LIST.fullmatch(inner):
                        return None
                    values = PERMISSION_ITEM.findall(inner)
                else:
                    values = [value]
                if not all(PERMISSION_ITEM.fullmatch(item) for item in values):
                    return None
                clauses[name] = values
    return {name for name, settings in clauses.items() if "*" in settings} if clauses else None


def valid_directory(value):
    return (isinstance(value, str) and value.startswith("/") and value.endswith("/")
            and not any(mark in value for mark in ("//", "\\", "%", "?", "#"))
            and not {".", ".."} & set(value.split("/")))


def service_worker_check(results, capture, configured):
    expected = configured.get(capture.url.path)
    name = "service-worker-allowed"
    if not valid_directory(expected):
        return
    if not has_measurement(capture, name):
        unmeasured(results, capture, "WEB-24")
        return
    value = singleton(capture.headers, name)
    if value is None and not capture.headers.get(name):
        actual = capture.url.path.rsplit("/", 1)[0] + "/"
    else:
        destination = resolve_url(capture.url.geturl(), value) if value else None
        if url_origin(destination) != url_origin(capture.url) or destination.query or destination.fragment:
            return
        actual = destination.path
    if not valid_directory(actual):
        return
    assess(results, capture, "WEB-24", not actual.startswith(expected),
           "Allowed service worker scope extends outside the configured application directory.")


def har_checks(results, har, policy):
    variants = defaultdict(list)
    session_names = {name for name in policy_strings(policy, "session_cookie_names") if TOKEN.fullmatch(name)}
    corp_paths = policy_strings(policy, "corp_paths")
    logout_paths = policy_strings(policy, "clear_site_data_logout_paths")
    downloads = policy_strings(policy, "untrusted_download_paths")
    json_paths = policy_strings(policy, "expected_json_paths")
    scope = policy.get("service_worker_scopes")
    for capture in captures(har, policy):
        headers, path = capture.headers, capture.url.path
        https = capture.url.scheme == "https"
        for attributes in cookies(headers, session_names):
            if policy.get("require_explicit_samesite") is True:
                assess(results, capture, "WEB-11", attributes.get("samesite", "").lower() not in {"strict", "lax", "none"},
                       "Configured session cookie lacks a recognized explicit SameSite value.", contextual=True)
            if policy.get("session_cookie_host_only") is True:
                assess(results, capture, "WEB-12", bool(attributes.get("domain")),
                       "A configured host-only session cookie supplies a Domain attribute.", contextual=True)
        cors_checks(results, capture, policy, variants)
        if (https and capture.html and capture.final and capture.status not in {204, 205}
                and policy.get("require_cross_origin_isolation") is True):
            compare_header(results, capture, "WEB-15", "cross-origin-opener-policy", {"same-origin"},
                           "Document lacks the required same-origin COOP value.", structured=True)
            compare_header(results, capture, "WEB-16", "cross-origin-embedder-policy", {"require-corp", "credentialless"},
                           "Document lacks a COEP value suitable for the configured isolation policy.", structured=True)
        if capture.final and path in corp_paths:
            permitted = {"same-origin", "same-site"} if policy.get("corp_same_site_allowed") is True else {"same-origin"}
            compare_header(results, capture, "WEB-17", "cross-origin-resource-policy", permitted,
                           "Captured resource lacks the required restrictive CORP value.")
        if capture.html and capture.final and headers.get("permissions-policy"):
            wildcard = permissions_wildcards(headers["permissions-policy"])
            if wildcard is not None:
                assess(results, capture, "WEB-18", bool(wildcard),
                       f"Permissions-Policy contains unrestricted {', '.join(sorted(wildcard))}.", contextual=True)
        if https and 200 <= capture.status < 400 and path in logout_paths:
            if capture.complete:
                tokens = {part.strip() for field in headers.get("clear-site-data", []) for part in field.split(",")}
                absent = '"*"' not in tokens and not {'"cache"', '"cookies"'} <= tokens
                assess(results, capture, "WEB-19", absent,
                       "Configured logout response lacks the required quoted cache and cookies directives.", contextual=True)
            else:
                unmeasured(results, capture, "WEB-19")
        if capture.representation and path in downloads and has_measurement(capture, "content-disposition"):
            disposition = singleton(headers, "content-disposition") or ""
            assess(results, capture, "WEB-20", disposition.split(";", 1)[0].strip().lower() != "attachment",
                   "Configured untrusted download lacks an attachment disposition.")
        if policy.get("redact_server_versions") is True:
            versions = headers.get("server", []) + headers.get("x-powered-by", [])
            if versions or capture.complete:
                assess(results, capture, "WEB-21", any(PRODUCT_VERSION.search(field) for field in versions),
                       "Server metadata includes an explicit software version.")
            else:
                unmeasured(results, capture, "WEB-21")
        if headers.get("www-authenticate"):
            basic = any(re.match(r"^basic(?:\s|$)", part.strip(), flags=re.I)
                        for value in headers["www-authenticate"] for part in split_quoted(value, ","))
            assess(results, capture, "WEB-22", basic and not https, "Basic authentication challenge observed over HTTP.")
        if https and capture.status in REDIRECT_STATUSES and (location := singleton(headers, "location")):
            target = resolve_url(capture.url.geturl(), location)
            if url_origin(target):
                assess(results, capture, "WEB-23", target.scheme == "http",
                       "HTTPS response redirects to an HTTP destination.")
        if https and capture.final and isinstance(scope, dict):
            service_worker_check(results, capture, scope)
        if capture.representation and path in json_paths and has_measurement(capture, "content-type"):
            declared_type = (singleton(headers, "content-type") or "").split(";", 1)[0].strip().lower()
            assess(results, capture, "WEB-25", not JSON_MIME.fullmatch(declared_type),
                   "Configured JSON response has no JSON media type.")

    for options in variants.values():
        if len({origin for origin, _ in options}) < 2:
            continue
        for _, capture in options:
            vary = {part.strip().lower() for field in capture.headers.get("vary", []) for part in field.split(",")}
            assess(results, capture, "WEB-14", not vary & {"*", "origin"},
                   "Two captured shared responses vary their CORS origin, but this one has no Vary: Origin.",
                   contextual=True)


def check(text_inputs, har, policy, advisories):
    results = dict.fromkeys((*HTML_IDS, *WEB_IDS))
    html_checks(results, text_inputs, policy)
    har_checks(results, har, policy)
    return results
