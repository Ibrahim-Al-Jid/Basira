"""Read a saved ZAP Traditional JSON report with a fixed passive-rule allowlist."""
from collections import Counter
from urllib.parse import urlsplit


TOOL = "zap-passive-report"
RULES = {
    "ZAP-10020": ("medium", "Anti-clickjacking header observation", "ملاحظة عن حماية منع تضمين الصفحة",
                  "Review the effective frame-ancestors policy and X-Frame-Options header.",
                  "راجع سياسة frame-ancestors ورأس X-Frame-Options الفعليين."),
    "ZAP-10021": ("low", "MIME-sniffing header observation", "ملاحظة عن منع تخمين نوع المحتوى",
                  "Review the Content-Type and X-Content-Type-Options headers.",
                  "راجع رؤوس Content-Type وX-Content-Type-Options."),
    "ZAP-10035": ("low", "Strict-Transport-Security header observation", "ملاحظة عن رأس HSTS",
                  "Review HSTS on the HTTPS response against the deployment policy.",
                  "راجع رأس HSTS في استجابة HTTPS حسب سياسة النشر."),
    "ZAP-10038": ("medium", "Content Security Policy header observation", "ملاحظة عن رأس سياسة أمان المحتوى",
                  "Review the effective Content-Security-Policy header.",
                  "راجع رأس Content-Security-Policy الفعلي."),
}


def origin(value):
    if (not isinstance(value, str) or len(value) > 4096
            or any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in value)):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
                parsed.username is not None or parsed.password is not None):
            return None
        port = parsed.port
    except ValueError:
        return None
    if port == 0:
        return None
    return parsed.scheme, parsed.hostname.casefold(), port if port is not None else (443 if parsed.scheme == "https" else 80)


def inspect_document(document, target):
    """Keep only report-level counts. No submitted alert text or URI is projected."""
    selected = origin(target)
    sites = document.get("site")
    if selected is None:
        raise ValueError("scope")
    if not isinstance(sites, list) or not 1 <= len(sites) <= 50:
        raise ValueError("format")
    counts = Counter()
    skipped = accepted = instances = 0
    for site in sites:
        if not isinstance(site, dict) or origin(site.get("@name")) != selected:
            raise ValueError("scope")
        alerts = site.get("alerts")
        if not isinstance(alerts, list) or accepted + skipped + len(alerts) > 500:
            raise ValueError("format")
        for alert in alerts:
            if not isinstance(alert, dict):
                raise ValueError("format")
            plugin = alert.get("pluginid")
            rule = f"ZAP-{plugin}" if type(plugin) in {str, int} else None
            if rule not in RULES:
                skipped += 1
                continue
            if "alertRef" in alert:
                ref = alert["alertRef"]
                if not isinstance(ref, str) or not (ref == str(plugin) or ref.startswith(f"{plugin}-")):
                    skipped += 1
                    continue
            observations = alert.get("instances")
            if not isinstance(observations, list) or not observations:
                raise ValueError("format")
            instances += len(observations)
            if instances > 2500:
                raise ValueError("format")
            if any(not isinstance(item, dict) or origin(item.get("uri")) != selected for item in observations):
                raise ValueError("scope")
            accepted += 1
            counts[rule] += len(observations)
    return {
        "source": TOOL, "status": "imported", "accepted_alerts": accepted, "skipped_alerts": skipped,
    }, counts
