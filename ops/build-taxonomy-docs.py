"""Write docs/taxonomy.md from backend/taxonomy.py. Run: python ops/build-taxonomy-docs.py [--check]"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import taxonomy as t  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "taxonomy.md"


def render():
    s = t.summary()
    lines = ["# Vulnerability taxonomy", "",
             "Generated from `backend/taxonomy.py` by `ops/build-taxonomy-docs.py`. Edit the module, not this file.", "",
             f"{s['domains']} domains, {s['subdomains']} subdomains, {s['problems']} named problems. "
             f"{s['subdomains_with_rules']} subdomains are backed by at least one of the 100 shipped checks; "
             f"{s['subdomains_gap']} are documented gaps that need active probing or human review.", "",
             "Reference sets: OWASP Top 10:2025, OWASP API Security Top 10 2023, OWASP WSTG 4.x chapters, CWE (2025 Top 25 informs ranking).",
             "", "Modes: `artifact` reviews supplied files. `capture` reviews a supplied HAR or header capture. "
             "`active` needs authorized live probing and is not in the current scope policy. `manual` needs a person.", ""]
    for d in t.DOMAINS:
        lines += [f"## {d['id']} {d['name']}", "", "| ID | Subdomain | CWE | OWASP 2025 | WSTG | Modes | Marsad checks |", "|---|---|---|---|---|---|---|"]
        for x in d["subdomains"]:
            refs = ", ".join(x["owasp_2025"] + x["owasp_api_2023"])
            rules = ", ".join(x["rules"]) if x["rules"] else "gap"
            lines.append(f"| {x['id']} | {x['name']} | {', '.join(map(str, x['cwe']))} | {refs} | {', '.join(x['wstg'])} | {', '.join(x['modes'])} | {rules} |")
        lines.append("")
        for x in d["subdomains"]:
            if x["problems"]:
                lines.append(f"- **{x['id']}** " + "; ".join(x["problems"]))
        lines.append("")
    lines += ["## Out of scope", "", "Memory-safety weaknesses from the CWE Top 25 are native-code problems, not website problems: "
              + ", ".join(f"CWE-{k} {v}" for k, v in t.OUT_OF_SCOPE_CWE.items()) + ".", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        raise SystemExit(0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else "docs/taxonomy.md is stale")
    OUT.write_text(text, encoding="utf-8")
