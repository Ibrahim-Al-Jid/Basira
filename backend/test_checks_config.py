from base64 import b64encode
import json

import pytest

from .checks import config


DOCKER_PIN = "sha256:" + "a" * 64
ACTION_PIN = "b" * 40
SYNTHETIC_TOKEN = "ghp_" + "d" * 36
SYNTHETIC_PASSWORD = "discard-this-test-password"
APP_PATH = "config/prod/settings.env"
SYNTHETIC_PEM_BODY = b64encode(b"Fictional payload with no cryptographic key material").decode("ascii")
SYNTHETIC_PEM_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
SYNTHETIC_PEM_END = "-----END " + "PRIVATE KEY-----"
SYNTHETIC_PEM = "\n".join((SYNTHETIC_PEM_BEGIN, SYNTHETIC_PEM_BODY, SYNTHETIC_PEM_END))


def kubernetes(unsafe):
    value = "true" if unsafe else "false"
    host = "/unapproved" if unsafe else "/approved"
    cap = "NET_ADMIN" if unsafe else "CHOWN"
    return f"""apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      hostNetwork: {value}
      hostPID: {value}
      volumes:
        - name: synthetic
          hostPath:
            path: {host}
      initContainers:
        - name: migration
          securityContext:
            privileged: {value}
            allowPrivilegeEscalation: {value}
      containers:
        - name: app
          securityContext:
            capabilities:
              add: [{cap}]
            allowPrivilegeEscalation: {value}
"""


def terraform(unsafe):
    flags = dict.fromkeys(config.S3_FLAGS, not unsafe)
    return json.dumps({"resource": {
        "aws_s3_bucket": {"example": {"bucket": "example-defensive-tests"}},
        "aws_s3_bucket_public_access_block": {
            "example_block": {"bucket": "${aws_s3_bucket.example.id}", **flags},
        },
    }}, indent=2)


def sql(unsafe):
    commands = ["CREATE TABLE public.example (owner_id uuid);"]
    if not unsafe:
        commands += [
            "ALTER TABLE public.example ENABLE ROW LEVEL SECURITY;",
            "CREATE POLICY example_policy ON public.example USING (owner_id IS NOT NULL);",
        ]
    return "\n".join(commands)


def workflow(unsafe):
    revision = "v4" if unsafe else ACTION_PIN
    level = "write" if unsafe else "read"
    scalar_permissions = "write-all" if unsafe else "read-all"
    persistence = "true" if unsafe else "false"
    return f"""name: Synthetic workflow
on: push
permissions: {scalar_permissions}
jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: {level}
    steps:
      - uses: actions/checkout@{revision}
        with:
          persist-credentials: {persistence}
  local:
    uses: ./.github/workflows/locally-managed.yml
"""


def branch(unsafe):
    return json.dumps({"complete": True, "branches": {"main": {
        "required_approvals": 0 if unsafe else 2,
        "required_checks": [] if unsafe else ["verify"],
    }}}, indent=2)


def app_settings(unsafe):
    return "\n".join([
        f"APP_DEBUG={'true' if unsafe else 'false'}",
        'SESSION_COOKIE_NAME=session',
        'SESSION_COOKIE_SAMESITE=None',
        f"SESSION_COOKIE_SECURE={'false' if unsafe else 'true'}",
        f"TLS_KEYSTORE_PASSWORD={SYNTHETIC_PASSWORD if unsafe else '${STORE_PASSWORD}'}",
        f"DATABASE_URL=postgresql://db_user:{SYNTHETIC_PASSWORD if unsafe else '${DB_PASSWORD}'}@db.invalid/test",
        f"PROVIDER_TOKEN={SYNTHETIC_TOKEN if unsafe else '${TOKEN}'}",
        SYNTHETIC_PEM if unsafe else "-----BEGIN CERTIFICATE-----",
    ])


@pytest.fixture
def policy():
    return {
        "snapshot_complete": True,
        "hostpath_exemptions": ["/approved"],
        "forbidden_capabilities": ["NET_ADMIN"],
        "tenant_tables": ["public.example"],
        "ci_write_permissions": {"build": ["checks"]},
        "ci_disable_checkout_credentials": True,
        "protected_branches": {"main": {"required_approvals": 2, "required_checks": ["verify"]}},
        "session_cookie_keys": ["session"],
    }


@pytest.fixture(params=[True, False], ids=["matched", "clear"])
def snapshots(request):
    unsafe = request.param
    image = "debian:example" if unsafe else f"debian@{DOCKER_PIN}"
    user = "root" if unsafe else "1000"
    return unsafe, {
        "Dockerfile": f"FROM {image}\nUSER {user}\n",
        "deploy/app.yaml": kubernetes(unsafe),
        "iac/s3.tf.json": terraform(unsafe),
        "migrations/001.sql": sql(unsafe),
        ".github/workflows/build.yml": workflow(unsafe),
        ".basira/branch-protection.json": branch(unsafe),
        APP_PATH: app_settings(unsafe),
    }


ALL_RULES = config.INF_RULES + config.CI_RULES + config.APP_RULES


@pytest.mark.parametrize("rule", ALL_RULES)
def test_config_catalog_outcomes(rule, snapshots, policy):
    unsafe, inputs = snapshots
    actual = config.check(inputs, None, policy, [])[rule]
    if unsafe:
        assert len(actual) == 1
        hit = actual[0]
        assert hit["path"] in inputs
        assert 1 <= hit["line"] <= len(inputs[hit["path"]].splitlines())
        assert hit["title_ar"] and hit["remediation_ar"]
        assert SYNTHETIC_TOKEN not in str(hit)
        assert SYNTHETIC_PASSWORD not in str(hit)
    else:
        assert actual == []
    assert config.check({"README.md": "Offline catalog"}, None, policy, [])[rule] is None


def test_app_private_key_needs_a_complete_plausible_pem_block():
    inputs = {
        "backend/test_example.py": f'head = "{SYNTHETIC_PEM_BEGIN}"',
        "app/truncated.pem": f"{SYNTHETIC_PEM_BEGIN}\n{SYNTHETIC_PEM_BODY}\n",
        "app/empty.key": f"{SYNTHETIC_PEM_BEGIN}\n{SYNTHETIC_PEM_END}\n",
        "app/bad-encoding.pem": f"{SYNTHETIC_PEM_BEGIN}\n{SYNTHETIC_PEM_BODY}!\n{SYNTHETIC_PEM_END}",
        "app/wrong-label.pem": SYNTHETIC_PEM.removesuffix(SYNTHETIC_PEM_END) + "-----END CERTIFICATE-----",
        "app/match.pem": SYNTHETIC_PEM,
        "app/match.py": f'# First line\nKEY = """{SYNTHETIC_PEM}"""',
        "app/match.json": json.dumps({"key": SYNTHETIC_PEM}),
    }
    hits = config.check(inputs, None, {}, [])["APP-01"]
    assert {(hit["path"], hit["line"]) for hit in hits} == {
        ("app/match.pem", 1), ("app/match.py", 2), ("app/match.json", 1),
    }
    assert SYNTHETIC_PEM_BODY not in str(hits)


def test_absence_rules_require_policy_and_complete_input(policy):
    inputs = {"main.tf.json": terraform(True), "schema.sql": sql(True)}
    results = config.check(inputs, None, {**policy, "snapshot_complete": False}, [])
    assert results["INF-09"] is results["INF-10"] is None
    partial = json.dumps({"complete": False, "branches": {"main": {"required_approvals": 0, "required_checks": []}}})
    results = config.check({".basira/branch-protection.json": partial}, None, policy, [])
    assert results["CI-05"] is results["CI-06"] is None


def test_docker_stages_and_heredocs_are_handled(policy):
    content = f"""FROM alpine@{DOCKER_PIN} AS builder
USER root
RUN <<EOF
FROM ignored-image
USER root
EOF
FROM builder AS runtime
USER app
"""
    results = config.check({"Dockerfile": content}, None, policy, [])
    assert results["INF-01"] == results["INF-02"] == []
    inherited = config.check({"Dockerfile": content.removesuffix("USER app\n")}, None, policy, [])
    assert inherited["INF-01"][0]["line"] == 2


def test_kubernetes_aliases_and_string_booleans(policy):
    content = """apiVersion: v1
kind: Pod
x-template: &template
  privileged: true
spec:
  hostNetwork: "true"
  containers:
    - name: app
      securityContext:
        <<: *template
        privileged: false
        allowPrivilegeEscalation: true
"""
    results = config.check({"pod.yaml": content}, None, policy, [])
    assert results["INF-03"] == results["INF-04"] == []
    assert len(results["INF-08"]) == 1


def test_sql_static_migration_ignores_comments_and_dynamic_bodies(policy):
    misleading_content = """
-- ALTER TABLE public.example ENABLE ROW LEVEL SECURITY;
/* outer /* nested */ ALTER TABLE public.example ENABLE ROW LEVEL SECURITY; */
DO $do$BEGIN
  EXECUTE 'ALTER TABLE public.example ENABLE ROW LEVEL SECURITY;';
END;$do$;
"""
    result = config.check({"migrations/001.sql": sql(True) + misleading_content}, None, policy, [])
    assert result["INF-10"][0]["assessment"] == "review_required"
    inputs = {"migrations/001.sql": sql(False),
              "migrations/002.sql": "DROP POLICY IF EXISTS example_policy ON public.example;"}
    assert len(config.check(inputs, None, policy, [])["INF-10"]) == 1


def test_python_does_not_evaluate_dynamic_settings_and_ignores_fixture_markers(policy):
    source = f"""DEBUG = bool(environment())
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = False
SECRET = "{SYNTHETIC_TOKEN}"
"""
    result = config.check({"fixtures/settings.py": source, "config/settings_prod.py": source},
                          None, {**policy, "session_cookie_keys": []}, [])
    assert result["APP-04"] is None
    assert len(result["APP-02"]) == len(result["APP-05"]) == 1
    assert result["APP-02"][0]["path"] == "config/settings_prod.py"
