"""Worker side of the Hunter model call: every turn goes through the gateway's /chat route.

The worker never holds a provider key. The gateway checks the scan reservation and the per-scan call cap on every
turn, so a loop that runs longer than its budget is stopped there as well as in hunt()."""
import json

import httpx

TOOL_PROTOCOL = (
    "To use a tool, reply with JSON only: "
    '{"tool_calls":[{"name":"<tool>","arguments":{...}}]}. Allowed tools: %s. '
    "To finish, reply with the final JSON object only."
)
MAX_TURN_SECONDS = 60


def wire_messages(messages, tool_names):
    first = dict(messages[0])
    first["content"] = first["content"] + "\n" + TOOL_PROTOCOL % ", ".join(sorted(tool_names))
    # Tool output is already wrapped in <data> tags by hunt(); providers only need user, assistant and system roles.
    return [first] + [{"role": "user" if item["role"] == "tool" else item["role"], "content": item["content"]}
                      for item in messages[1:]]


def tool_calls(text):
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    calls = data.get("tool_calls") if isinstance(data, dict) else None
    if not isinstance(calls, list):
        return None
    return [item for item in calls if isinstance(item, dict)]


def gateway_model(url, headers, identity, post=httpx.post):
    """Return the model(messages, tool_names) callable hunt() expects. `identity` carries the reservation fields
    (connection, provider, model, org/project/scan ids, lease, generation, source), never a key."""
    def model(messages, tool_names):
        reply = post(url + "/chat", json={**identity, "messages": wire_messages(messages, tool_names)},
                     headers=headers, timeout=MAX_TURN_SECONDS, trust_env=False)
        reply.raise_for_status()
        data = reply.json()
        text = data["content"]
        usage = data["usage"]
        if not isinstance(text, str):
            raise ValueError("Gateway answer has no text")
        calls = tool_calls(text)
        return {"content": None if calls is not None else text, "tool_calls": calls or [],
                "usage": {"input": usage["input"], "output": usage["output"]}}
    return model
