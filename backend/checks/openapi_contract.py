"""Inventory a submitted OpenAPI document without loading any references."""
import re
from collections import Counter
from urllib.parse import unquote

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
SCHEME_TYPES = {"apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"}
MISSING = object()
RULES = {
    "API-01": ("HTTP server declared", "عنوان خادم HTTP معلن",
               "Use HTTPS for published servers.", "استخدم HTTPS لعناوين الخوادم المنشورة."),
    "API-02": ("Operations permit anonymous access", "عمليات بتسمح بوصول من غير تسجيل",
               "Review the declared audience and add authentication where required.",
               "راجع الجمهور المقصود وأضف المصادقة للعمليات اللي تحتاجها."),
    "API-03": ("References could not be resolved offline", "مراجع تعذّر حلها محليًا",
               "Bundle references into the submitted document.", "ادمج المراجع في نفس الوثيقة."),
}


def security(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) or any(
        not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes)
        for scopes in row.values()
    ) for row in value):
        raise ValueError("security")
    return value


def servers(node):
    rows = node.get("servers", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) or
                                        not isinstance(row.get("url"), str) or not row["url"].strip() for row in rows):
        raise ValueError("servers")
    return sum(row["url"].strip().lower().startswith("http://") for row in rows)


def local_target(document, value):
    if value == "#":
        return document
    if not isinstance(value, str) or not value.startswith("#/") or len(value) > 4096:
        return MISSING

    node = document
    for token in unquote(value[2:]).split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and key in node:
            node = node[key]
        elif isinstance(node, list) and len(key) <= 9 and re.fullmatch(r"0|[1-9][0-9]*", key) and int(key) < len(node):
            node = node[int(key)]
        else:
            return MISSING
    return node


def scheme_type(document, value):
    seen = set()
    while isinstance(value, dict) and "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref or len(ref) > 4096:
            raise ValueError("scheme reference")
        if ref in seen or len(seen) >= 16:
            return "unresolved"
        seen.add(ref)
        value = local_target(document, ref)
        if value is MISSING:
            return "unresolved"
    kind = value.get("type") if isinstance(value, dict) else None
    if not isinstance(kind, str) or kind not in SCHEME_TYPES:
        raise ValueError("scheme type")
    if kind == "mutualTLS" and document["openapi"].startswith("3.0."):
        raise ValueError("scheme type")
    return kind


def classify_schemes(document):
    components = document.get("components", {})
    schemes = components.get("securitySchemes", {}) if isinstance(components, dict) else None
    if not isinstance(schemes, dict) or len(schemes) > 250:
        raise ValueError("security schemes")
    return {name: scheme_type(document, value) for name, value in schemes.items()}


def inspect_document(document):
    version = document.get("openapi")
    if not isinstance(version, str) or not re.fullmatch(r"3\.[01]\.[0-9]{1,3}", version):
        raise ValueError("version")
    paths, info = document.get("paths"), document.get("info")
    if not isinstance(paths, dict) or not isinstance(info, dict) or any(
        not isinstance(info.get(key), str) or not info[key].strip() for key in ("title", "version")
    ):
        raise ValueError("structure")
    inherited = security(document.get("security", []))
    schemes = classify_schemes(document)
    required_names = {name for alternative in inherited for name in alternative}
    operations = anonymous = local = unresolved = 0
    http = servers(document)
    for path, row in paths.items():
        if path.startswith("x-"):
            continue
        if not path.startswith("/") or not isinstance(row, dict):
            raise ValueError("path")
        http += servers(row)
        for method in METHODS & row.keys():
            operation = row[method]
            if not isinstance(operation, dict):
                raise ValueError("operation")
            options = security(operation["security"]) if "security" in operation else inherited
            required_names.update(name for alternative in options for name in alternative)
            operations += 1
            anonymous += not options or any(not choice for choice in options)
            http += servers(operation)
    stack = [document]
    remaining = 100_000
    while stack:
        node = stack.pop()
        remaining -= 1
        if remaining < 0:
            raise ValueError("size")
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if not isinstance(ref, str) or not ref:
                    raise ValueError("reference")
                if local_target(document, ref) is not MISSING:
                    local += 1
                else:
                    unresolved += 1
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return {
        "version": version, "operations": operations, "declared_auth": operations - anonymous,
        "anonymous_operations": anonymous, "local_references": local, "unresolved_references": unresolved,
        "security_schemes": dict(sorted(Counter(schemes.values()).items())),
        "unresolved_security_requirements": sum(schemes.get(name, "unresolved") == "unresolved"
                                                for name in required_names),
    }, {"API-01": http, "API-02": anonymous, "API-03": unresolved}
