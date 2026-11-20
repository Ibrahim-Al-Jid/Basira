import base64
import json

import pytest

from .checks import config_extra


SYNTHETIC_SECRET = "test-only-credential-value"


def package(unsafe):
    return {
        "name": "sample",
        "packageManager": "npm@11.0.0",
        "dependencies": {
            "example": "*" if unsafe else "^1.2.3",
            "local-example": "file:../outside" if unsafe else "file:./local-example",
        },
        "publishConfig": {"access": "public" if unsafe else "restricted"},
    }


def registry_lock(unsafe):
    auth = f"npm-user:{SYNTHETIC_SECRET}@" if unsafe else ""
    algo, count = ("sha1", 20) if unsafe else ("sha512", 64)
    encoded = base64.b64encode(b"0" * count).decode()
    locked = {
        "version": "1.2.3",
        "resolved": f"https://{auth}registry.example.test/example/-/example-1.2.3.tgz",
        "integrity": f"{algo}-{encoded}",
    }
    if unsafe:
        locked["deprecated"] = "Example provider advisory text is not stored."
    return {
        "lockfileVersion": 3,
        "packages": {"": {"dependencies": {"example": "^1.2.3"}}, "node_modules/example": locked},
    }


def pod(unsafe):
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "example"},
        "spec": {
            "hostIPC": unsafe,
            "automountServiceAccountToken": unsafe,
            "securityContext": {
                "sysctls": [{"name": "kernel.msgmax" if unsafe else "net.ipv4.tcp_syncookies", "value": "1"}],
                "seccompProfile": {"type": "Unconfined" if unsafe else "RuntimeDefault"},
                "runAsUser": 0 if unsafe else 10001,
            },
            "containers": [{
                "name": "example",
                "ports": [{"hostPort": 12451 if unsafe else 8080}],
                "securityContext": {
                    "procMount": "Unmasked" if unsafe else "Default",
                    "readOnlyRootFilesystem": not unsafe,
                },
            }],
        },
    }


def workflow(unsafe):
    label = "self-hosted" if unsafe else "ubuntu-latest"
    allowed_failure = "true" if unsafe else "false"
    access = "inherit" if unsafe else "{}"
    timeout = 120 if unsafe else 10
    return f"""name: Configuration fixture
on:
  pull_request:
jobs:
  verify:
    runs-on: [{label}, linux]
    timeout-minutes: {timeout}
    continue-on-error: {allowed_failure}
  call-reviewed-workflow:
    uses: ./.github/workflows/example.yml
    secrets: {access}
"""


def settings(unsafe):
    hosts = ["*"] if unsafe else ["web.example.test"]
    return "\n".join([
        f"NODE_TLS_REJECT_UNAUTHORIZED = '{'0' if unsafe else '1'}'",
        f"SESSION_COOKIE_HTTPONLY = {not unsafe}",
        f"ALLOWED_HOSTS = {hosts!r}",
        f"CORS_ALLOW_ALL_ORIGINS = {unsafe}",
        "CORS_ALLOW_CREDENTIALS = True",
        f"WTF_CSRF_ENABLED = {not unsafe}",
    ])


@pytest.fixture
def policy():
    return {
        "repository_complete": True,
        "npm_require_private_package": True,
        "kubernetes_allowed_host_ports": [8080],
        "kubernetes_require_read_only_root": True,
        "kubernetes_forbid_service_account_token": True,
        "kubernetes_forbidden_sysctls": ["kernel/msgmax"],
        "ci_forbid_secret_inheritance": True,
        "ci_max_job_timeout_minutes": 30,
        "ci_required_jobs": ["verify"],
    }


def inputs(unsafe):
    credential = SYNTHETIC_SECRET if unsafe else "${REGISTRY_TOKEN}"
    return {
        ".npmrc": f"strict-ssl={'false' if unsafe else 'true'}\n//registry.example.test/:_authToken={credential}\n",
        "package.json": json.dumps(package(unsafe), indent=2),
        "package-lock.json": json.dumps(registry_lock(unsafe), indent=2),
        "deployment/pod.json": json.dumps(pod(unsafe), indent=2),
        ".github/workflows/example.yml": workflow(unsafe),
        "app/settings.py": settings(unsafe),
    }


@pytest.fixture(params=[True, False], ids=["matched", "clear"])
def snapshot(request):
    return request.param, inputs(request.param)


@pytest.mark.parametrize("rule", config_extra.TEXT)
def test_extra_config_check_outcomes(rule, snapshot, policy):
    unsafe, files = snapshot
    matches = config_extra.check(files, None, policy, [])[rule]
    if unsafe:
        assert len(matches) == 1
        match = matches[0]
        assert 1 <= match["line"] <= len(files[match["path"]].splitlines())
        assert match["title_ar"] and match["remediation_ar"]
        assert all(value not in str(match) for value in (SYNTHETIC_SECRET, "npm-user", "Example provider advisory text"))
    else:
        assert matches == []
    assert config_extra.check({"README.md": "No eligible settings."}, None, policy, [])[rule] is None


def test_checks_require_policy_where_specified():
    results = config_extra.check(inputs(True), None, {}, [])
    for rule in ("DEP-13", "DEP-14", "INF-15", "INF-17", "INF-18", "CI-07", "CI-09", "CI-10"):
        assert results[rule] is None


def test_nested_workspace_dependency_resolves_inside_root(policy):
    manifest = package(True)
    manifest["dependencies"] = {"local-example": "file:../../shared/example"}
    path = "packages/service/package.json"
    assert config_extra.check({path: json.dumps(manifest)}, None, policy, [])["DEP-14"] == []
    manifest["dependencies"]["local-example"] = "file:../../../elsewhere"
    assert len(config_extra.check({path: json.dumps(manifest)}, None, policy, [])["DEP-14"]) == 1


def test_stronger_digest_suppresses_weak_only_match():
    lockfile = registry_lock(True)
    package = lockfile["packages"]["node_modules/example"]
    package["integrity"] += " sha512-" + base64.b64encode(b"1" * 64).decode()
    result = config_extra.check({"package-lock.json": json.dumps(lockfile)}, None, {}, [])
    assert result["DEP-15"] == []


def test_npmrc_interpolated_credential_is_not_a_literal_secret():
    content = "//registry.example.test/:_authToken=prefix-${NPM_TOKEN}"
    assert config_extra.check({".npmrc": content}, None, {}, [])["DEP-11"] == []


def test_container_overrides_pod_default_and_quotes_are_not_booleans(policy):
    yaml = """apiVersion: v1
kind: Pod
spec:
  hostIPC: "true"
  securityContext:
    seccompProfile:
      type: Unconfined
    runAsUser: 0
  containers:
    - name: example
      securityContext:
        seccompProfile:
          type: RuntimeDefault
        runAsUser: 10001
"""
    result = config_extra.check({"pod.yml": yaml}, None, policy, [])
    assert result["INF-11"] is None
    assert result["INF-14"] == result["INF-16"] == []


def test_dynamic_ci_values_and_non_pull_request_workflow_are_not_inferred(policy):
    text = """
on: push
jobs:
  verify:
    runs-on: self-hosted
    timeout-minutes: ${{ vars.RUNTIME_MINUTES }}
    continue-on-error: ${{ vars.ALLOW_FAILURE }}
"""
    result = config_extra.check({".github/workflows/example.yml": text}, None, policy, [])
    assert result["CI-08"] is result["CI-09"] is result["CI-10"] is None


def test_fixtures_and_dynamic_python_host_values_are_not_evaluated():
    config_file = "ALLOWED_HOSTS = get_hosts()\nWTF_CSRF_ENABLED = False"
    result = config_extra.check({"fixtures/settings.py": config_file}, None, {}, [])
    assert result["APP-09"] is result["APP-11"] is None
    result = config_extra.check({"app/settings.py": config_file}, None, {}, [])
    assert result["APP-09"] is None
    assert len(result["APP-11"]) == 1
