"""Scan timeline messages: one place for the stored text and its stable translation key.

The stored text is the Arabic fallback. The key never changes, so the interface can translate each event."""
import re

MESSAGES = {
    "scan.queued": "تم تسجيل الطلب للفحص.",
    "scan.completed": "اكتمل الفحص.",
    "scan.partial_ready": "التقرير التجريبي جاهز.",
    "scan.cancelled": "اتلغى الفحص.",
    "scan.cancelled_requester_changed": "اتلغى الفحص لأن صلاحية مقدم الطلب اتغيّرت.",
    "scan.cancelled_project_deleted": "اتلغى الفحص بعد حذف المشروع.",
    "scan.failed_input_expired": "انتهت مدة الاحتفاظ بالمدخل قبل اكتمال الفحص.",
    "scan.failed_provenance": "تعذّر التحقق من مصدر الفحص أو النطاق المسجّل.",
    "scan.failed_retry_limit": "وصلت المهمة للحد الأقصى لمحاولات التشغيل.",
    "scan.failed": "تعذّر تنفيذ الفحص.",
    "scan.agent_failed": "تعذّر تشغيل وضع الوكلاء، فمتّحسبش النتيجة كفحص وكلاء.",
    "scan.agent_fallback": "مسار الوكلاء ما اكتملش، وكمّلنا بالقواعد.",
}
BY_TEXT = {text: key for key, text in MESSAGES.items()}
ATTEMPT_STARTED = "بدأت محاولة التنفيذ رقم {number}."
ATTEMPT_RESUMED = "استؤنفت محاولة التنفيذ رقم {number} من نتيجة التحليل المحفوظة."
ATTEMPTS = {"scan.attempt_started": ATTEMPT_STARTED, "scan.attempt_resumed": ATTEMPT_RESUMED}
ATTEMPT_PATTERNS = {key: re.compile("^" + re.escape(text).replace(r"\{number\}", r"(\d+)") + "$")
                    for key, text in ATTEMPTS.items()}


def event_key(detail):
    """Return (key, params) for a stored event text. Unknown text gives (None, None) and the client shows the text."""
    if detail in BY_TEXT:
        return BY_TEXT[detail], None
    for key, pattern in ATTEMPT_PATTERNS.items():
        found = pattern.match(detail)
        if found:
            return key, {"attempt": int(found.group(1))}
    return None, None
