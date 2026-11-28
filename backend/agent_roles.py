"""The five agent roles: one registry of stable ids and display names.

The id is what rows, events, contracts and tool allow-lists store, and it never changes. The names are
what people read in the interface and the docs. A test keeps the interface and the docs in step with this file.
"""

AGENT_ROLES = (
    # id, English name, Arabic name, English job, Arabic job
    ("orchestrator", "Maestro", "المايسترو", "Plans the run, sets budgets and routes work", "يخطّط التشغيل ويحدّد الميزانيات ويوجّه العمل"),
    ("planning", "Scout", "الكشّاف", "Reads the whole project and maps it", "يقرأ المشروع كله ويرسم خريطته"),
    ("analysis", "Hunter", "الصيّاد", "Finds vulnerabilities with the rules, scanners and tools", "يلاقي الثغرات بالقواعد والماسحات والأدوات"),
    ("validation", "Auditor", "المدقّق", "Re-checks every finding against the evidence", "يعيد التحقق من كل نتيجة على الدليل"),
    ("reporting", "Scribe", "الكاتب", "Writes the report from validated findings only", "يكتب التقرير من النتائج المتحقَّق منها فقط"),
)
ROLE_IDS = tuple(role[0] for role in AGENT_ROLES)
DISPLAY = {role[0]: {"en": role[1], "ar": role[2], "job_en": role[3], "job_ar": role[4]} for role in AGENT_ROLES}
