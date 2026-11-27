"""English UI translations of server messages must still match the messages the server sends."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def test_translated_server_messages_exist_in_the_backend():
    client = (ROOT / "frontend" / "src" / "platformClient.js").read_text(encoding="utf-8")
    block = client[client.index("const knownErrors = {"):client.index("};", client.index("const knownErrors = {"))]
    keys = [json.loads(match) for match in re.findall(r'^  ("[^"]+"):', block, re.M)]
    assert len(keys) >= 15
    source = "".join(path.read_text(encoding="utf-8") for path in (ROOT / "backend").glob("*.py")
                     if not path.name.startswith("test_"))
    assert [key for key in keys if key not in source] == []
