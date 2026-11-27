"""Model-backed configurations of the detection experiment (C2 to C4).

Every configuration uses the same model, temperature, token limit and taxonomy list.
They differ only in structure: one agent, several agents, several agents with tools.
Every request and response is appended to a JSONL log so a run can be audited.
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .taxonomy import DOMAINS

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
MAX_TOKENS = 3000
GROUPS = {
    "injection-and-client": ["D04", "D05"],
    "access-and-identity": ["D01", "D02", "D03"],
    "files-and-requests": ["D06", "D12", "D09", "D08", "D07"],
}
TOOLS = [
    {"type": "function", "function": {"name": "search_code", "description": "Regex search over the file under review. Returns matching line numbers and lines.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "static_review", "description": "Run Basira's deterministic checks on the file under review and return rule IDs.",
     "parameters": {"type": "object", "properties": {}}}},
]


NESTED_QUANTIFIER = re.compile(r"\([^()]*[+*][^()]*\)\s*(?:[+*]|\{\d*,\d*\})|\\[1-9]")


def search_lines(source, pattern):
    """Regex search for the search_code tool. The pattern comes from a model, so it is bounded:
    short, no nested quantifiers or backreferences (the usual catastrophic-backtracking shapes), no
    more than 2000 lines. This is a heuristic guard, not a proof against every slow pattern."""
    if not isinstance(pattern, str) or not pattern or len(pattern) > 200 or NESTED_QUANTIFIER.search(pattern):
        return "pattern rejected"
    try:
        compiled = re.compile(pattern)
    except re.error:
        return "invalid pattern"
    lines = source.splitlines()[:2000]
    return "\n".join(f"{n}: {line[:400]}" for n, line in enumerate(lines, 1) if compiled.search(line))[:2000] or "no match"


def taxonomy_text(domain_ids=None):
    lines = []
    for domain in DOMAINS:
        if domain_ids is None or domain["id"] in domain_ids:
            lines += [f"{item['id']}: {item['name']}" for item in domain["subdomains"]]
    return "\n".join(lines)


class Client:
    def __init__(self, log_path, key=None):
        self.key = key or os.environ["OPENROUTER_API_KEY"]
        self.log_path = log_path
        self.calls = 0

    def chat(self, label, messages, tools=None):
        body = {"model": MODEL, "messages": messages, "temperature": 0, "max_tokens": MAX_TOKENS}
        if tools:
            body["tools"] = tools
        for attempt in range(8):
            request = Request(URL, json.dumps(body).encode(), {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=180) as response:
                    data = json.load(response)
                if data.get("error"):
                    raise RuntimeError(str(data["error"])[:200])
                break
            except (HTTPError, RuntimeError, TimeoutError, OSError) as error:
                time.sleep(min(60, 5 * 2 ** attempt))
                data = {"error": str(error)[:200]}
        self.calls += 1
        with open(self.log_path, "a", encoding="utf-8") as log:
            log.write(json.dumps({"label": label, "request_messages": len(messages), "error": data.get("error"), "usage": data.get("usage"),
                                  "response": (data.get("choices") or [{}])[0].get("message")}) + "\n")
        if data.get("error"):
            return {"content": "", "error": True}
        return data["choices"][0]["message"]


def parse_findings(text):
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0)).get("findings", [])
    except (ValueError, AttributeError):
        return []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and isinstance(item.get("subdomain"), str)]


def agent_prompt(role, domain_ids, source):
    return [
        {"role": "system", "content": f"You are the {role} agent of a defensive web-application security review. Report only vulnerabilities that are actually present in the code. "
         "If the code is safe, report none. Use only these taxonomy IDs:\n" + taxonomy_text(domain_ids)
         + '\nAnswer with JSON only: {"findings":[{"subdomain":"Dxx.x","evidence":"short quote"}]}'},
        {"role": "user", "content": "File under review:\n```php\n" + source + "\n```"},
    ]


def run_single(client, source):
    return {item["subdomain"] for item in parse_findings(client.chat("single", agent_prompt("single security reviewer", None, source))["content"])}


def run_team(client, source, tools_enabled=False, static_hook=None):
    def specialist(item):
        role, ids = item
        messages = agent_prompt(role, ids, source)
        for _ in range(4 if tools_enabled else 1):
            reply = client.chat(role, messages, TOOLS if tools_enabled else None)
            calls = reply.get("tool_calls") or []
            if not calls:
                return parse_findings(reply.get("content"))
            messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                if name == "search_code":
                    out = search_lines(source, args.get("pattern", ""))
                elif name == "static_review" and static_hook:
                    out = static_hook()
                else:
                    out = "unknown tool"
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
        return parse_findings(client.chat(role + "-final", messages)["content"])

    with ThreadPoolExecutor(3) as pool:
        candidates = [item for result in pool.map(specialist, GROUPS.items()) for item in result]
    if not candidates:
        return set()
    verify = [
        {"role": "system", "content": "You are the verification agent. Keep only candidate findings that the code clearly supports; drop the rest. "
         'Answer with JSON only: {"findings":[{"subdomain":"Dxx.x","evidence":"short quote"}]}'},
        {"role": "user", "content": "Code:\n```php\n" + source + "\n```\nCandidates:\n" + json.dumps(candidates)},
    ]
    return {item["subdomain"] for item in parse_findings(client.chat("verification", verify)["content"])}
