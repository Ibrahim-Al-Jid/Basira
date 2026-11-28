#!/usr/bin/env bash
# Start Basira locally with Docker Compose on Linux or macOS.
#
# Same job as ops/start-local.ps1: create .env.local once with random passwords
# and a GitHub credential key, start the local profile, and wait until the app
# answers. Values already present in .env.local are never overwritten.
#
#   ./ops/start-local.sh                      # http://127.0.0.1:8765
#   ./ops/start-local.sh --port 9000 --model
#   ./ops/start-local.sh --github-client-id <id> --github-app-slug <slug>
set -euo pipefail

port=8765
with_model=0
github_client_id=""
github_app_slug=""

usage() {
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --port) port="${2:?--port needs a value}"; shift 2 ;;
        --model) with_model=1; shift ;;
        --github-client-id) github_client_id="${2:?--github-client-id needs a value}"; shift 2 ;;
        --github-app-slug) github_app_slug="${2:?--github-app-slug needs a value}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$port" in
    ''|*[!0-9]*) echo "--port must be a number between 1024 and 65535." >&2; exit 2 ;;
esac
if [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then
    echo "--port must be between 1024 and 65535." >&2; exit 2
fi

root=$(cd "$(dirname "$0")/.." && pwd)
settings="$root/.env.local"
project="${COMPOSE_PROJECT_NAME:-basira-local}"

command -v docker >/dev/null 2>&1 || { echo "Install Docker and start it, then run this script again." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required." >&2; exit 1; }
docker info --format '{{.OSType}}' >/dev/null 2>&1 || { echo "Start the Docker engine and wait until it is ready." >&2; exit 1; }

random_hex() {
    od -An -tx1 -N "$1" /dev/urandom | tr -d ' \n'
}

random_alnum() {
    LC_ALL=C tr -dc '0-9A-Za-z' < /dev/urandom 2>/dev/null | head -c "$1" || true
}

# 32 random bytes in URL-safe base64, the shape the app expects for this key.
credential_key() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
    else
        od -An -tx1 -N 32 /dev/urandom | tr -d ' \n' | awk '{ for (i = 1; i < length($0); i += 2) printf "%c", strtonum("0x" substr($0, i, 2)) }' | base64 | tr '+/' '-_'
    fi
}

get_setting() {
    awk -F= -v key="$1" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$settings"
}

set_setting() {
    local key="$1" value="$2" temporary
    temporary=$(mktemp "${settings}.XXXXXX")
    awk -v key="$key" -v value="$value" '
        BEGIN { done = 0 }
        $0 ~ "^" key "=" { print key "=" value; done = 1; next }
        { print }
        END { if (!done) print key "=" value }
    ' "$settings" > "$temporary"
    chmod 600 "$temporary"
    mv "$temporary" "$settings"
}

if [ ! -f "$settings" ]; then
    umask 077
    cp "$root/ops/platform.env.example" "$settings"
    set_setting BASIRA_DB_PASSWORD "$(random_hex 32)"
    set_setting BASIRA_DISPATCH_PASSWORD "$(random_hex 32)"
    set_setting BASIRA_MIGRATION_PASSWORD "$(random_hex 32)"
    set_setting BASIRA_PORT "$port"
    sed -i.bak "s|127\.0\.0\.1:8765|127.0.0.1:${port}|g" "$settings"
    rm -f "${settings}.bak"
fi
chmod 600 "$settings"

listening=$(get_setting BASIRA_PORT)
case "$listening" in
    ''|*[!0-9]*) ;;
    *) port="$listening" ;;
esac

if [ -z "$(get_setting BASIRA_GITHUB_CALLBACK_URL)" ]; then
    set_setting BASIRA_GITHUB_CALLBACK_URL "http://127.0.0.1:${port}/api/platform/github/callback"
fi
if [ -n "$github_client_id" ] && [ -z "$(get_setting BASIRA_GITHUB_CLIENT_ID)" ]; then
    set_setting BASIRA_GITHUB_CLIENT_ID "$github_client_id"
fi
if [ -n "$github_app_slug" ] && [ -z "$(get_setting BASIRA_GITHUB_APP_SLUG)" ]; then
    set_setting BASIRA_GITHUB_APP_SLUG "$github_app_slug"
fi
if [ -z "$(get_setting BASIRA_GITHUB_CREDENTIAL_KEY)" ]; then
    set_setting BASIRA_GITHUB_CREDENTIAL_KEY "$(credential_key)"
fi
if ! get_setting BASIRA_GITHUB_CREDENTIAL_KEY | grep -Eq '^[A-Za-z0-9_-]{43}=$'; then
    echo "BASIRA_GITHUB_CREDENTIAL_KEY in .env.local is not a valid key (32 random bytes in URL-safe base64, 44 characters ending with =). Clear the value and run this script again to get a new one. Connections saved with the old key must be reconnected." >&2
    exit 1
fi

if [ -n "$(get_setting BASIRA_GITHUB_CLIENT_ID)" ] && [ -z "$(get_setting BASIRA_GITHUB_CLIENT_SECRET)" ] && [ -t 0 ]; then
    printf 'Paste the GitHub App Client Secret (hidden, saved only in .env.local): ' >&2
    IFS= read -rs client_secret
    printf '\n' >&2
    if [ -n "$client_secret" ]; then
        set_setting BASIRA_GITHUB_CLIENT_SECRET "$client_secret"
    fi
    unset client_secret
fi

missing=""
for name in BASIRA_GITHUB_CLIENT_ID BASIRA_GITHUB_CLIENT_SECRET BASIRA_GITHUB_APP_SLUG; do
    if [ -z "$(get_setting "$name")" ]; then
        missing="$missing $name"
    fi
done
if [ -n "$missing" ]; then
    echo "Warning: GitHub connection is not configured yet. Empty in .env.local:$missing. Fill them and run this script again; the app starts without GitHub until then." >&2
fi

if [ "$with_model" = 0 ] && [ "$(get_setting BASIRA_PROJECT_MODEL_ENABLED)" = "1" ]; then
    with_model=1
fi
if [ "$with_model" = 1 ]; then
    set_setting BASIRA_PROJECT_MODEL_ENABLED 1
    if [ -z "$(get_setting BASIRA_GATEWAY_URL)" ]; then
        set_setting BASIRA_GATEWAY_URL "http://model-gateway:8001"
    fi
    if [ -z "$(get_setting BASIRA_GATEWAY_TOKEN)" ]; then
        set_setting BASIRA_GATEWAY_TOKEN "$(random_hex 32)"
    fi
    model_password=$(get_setting BASIRA_MODEL_DB_PASSWORD)
    if [ -z "$model_password" ]; then
        set_setting BASIRA_MODEL_DB_PASSWORD "$(random_alnum 24)"
    elif ! printf '%s' "$model_password" | grep -Eq '^[0-9A-Za-z]{24,128}$'; then
        echo "BASIRA_MODEL_DB_PASSWORD in .env.local must be 24 to 128 letters or digits. Clear the value and run this script again to get a new one." >&2
        exit 1
    fi
fi

cd "$root"
compose=(-p "$project" -f compose.yaml -f compose.local.yaml --env-file .env.local)
if [ "$with_model" = 1 ]; then
    compose+=(--profile model)
fi

if ! docker compose "${compose[@]}" up -d --build; then
    echo "Basira failed to start. Check the Docker Compose output above." >&2
    exit 1
fi

published=$(docker compose "${compose[@]}" port app 8000 || true)
if [ -z "$published" ]; then
    echo "Basira did not publish its local web port." >&2
    exit 1
fi
url="http://${published}"

options=$(mktemp)
trap 'rm -f "$options"' EXIT
deadline=$(( $(date +%s) + 45 ))
ready=0
while [ "$(date +%s)" -lt "$deadline" ]; do
    if curl -fsS --max-time 3 "$url/api/platform/auth/options" -o "$options" 2>/dev/null; then
        ready=1
        break
    fi
    sleep 1
done
if [ "$ready" = 0 ]; then
    echo "Basira did not become ready. Check the app logs: docker compose -p $project logs app" >&2
    exit 1
fi
if ! grep -Eq '"password"[[:space:]]*:[[:space:]]*true' "$options" \
        || ! grep -Eq '"registration"[[:space:]]*:[[:space:]]*true' "$options"; then
    echo "Basira responded, but local sign-in or registration is disabled." >&2
    exit 1
fi

echo "Open $url/signin to sign in or create an account."
echo "Stop it with: docker compose -p $project down (data is kept)."
