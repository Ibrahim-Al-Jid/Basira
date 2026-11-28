"""The Auditor's candidate check (docs/ARCHITECTURE-agents.md, sections 2 and 6).

A candidate that a model proposes is accepted only if it points at a real place in the pinned snapshot and quotes
what is there. The check never trusts the model: it re-reads the files. Rejections carry a fixed reason code, never
model text. Findings from the deterministic rules are not routed through here and are unchanged."""
import re

from .artifact_review import redact_label

REASONS = ("bad_shape", "unknown_path", "line_out_of_range", "quote_missing", "quote_not_at_location",
           "unknown_rule", "duplicate")
MIN_QUOTE = 4
MAX_QUOTE = 300


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def audit_candidates(candidates, files, rules=None):
    """candidates: list of {path, line, quote, rule?}. files: path -> text. rules: optional set of known rule ids.
    Returns (accepted, rejected) where rejected rows are {index, reason}. Order is kept."""
    lines = {}
    for path, text in files.items():
        lines.setdefault(redact_label(path), text.split("\n"))
    accepted, rejected, seen = [], [], set()
    for index, item in enumerate(candidates):
        reason = _reason(item, lines, rules, seen)
        if reason:
            rejected.append({"index": index, "reason": reason})
        else:
            accepted.append(item)
    return accepted, rejected


def _reason(item, lines, rules, seen):
    if not isinstance(item, dict):
        return "bad_shape"
    path, line, quote, rule = item.get("path"), item.get("line"), item.get("quote"), item.get("rule")
    if not isinstance(path, str) or not isinstance(line, int) or isinstance(line, bool):
        return "bad_shape"
    if path not in lines:
        return "unknown_path"
    if not 1 <= line <= len(lines[path]):
        return "line_out_of_range"
    if not isinstance(quote, str) or not MIN_QUOTE <= len(squash(quote)) <= MAX_QUOTE:
        return "quote_missing"
    if squash(quote) not in squash(lines[path][line - 1]):
        return "quote_not_at_location"
    if rules is not None and rule not in rules:
        return "unknown_rule"
    key = (path, line, rule)
    if key in seen:
        return "duplicate"
    seen.add(key)
    return None
