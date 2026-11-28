"""Arabic wording for the fixed evidence sentences the document checks write.

The stored evidence stays English: fingerprints hash it. Only the Arabic exports translate it, at render time."""
import re

_SENTENCES = (
    (re.compile(r"(\d+) matching declarations in the document\."), "{0} تعريف مطابق في المستند."),
    (re.compile(r"Saved ZAP report contains (\d+) observation\(s\) for this rule\."),
     "تقرير ZAP المحفوظ فيه {0} ملاحظة لهذه القاعدة."),
)


def localized_evidence(evidence, ar):
    if not ar or not evidence:
        return evidence
    for pattern, template in _SENTENCES:
        found = pattern.fullmatch(evidence)
        if found:
            return template.format(*found.groups())
    return evidence
