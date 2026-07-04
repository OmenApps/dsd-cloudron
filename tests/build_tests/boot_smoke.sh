#!/usr/bin/env bash
# Build a rendered dsd-cloudron project and boot it under Cloudron-faithful
# constraints (readonly rootfs, writable /run and /app/data, addon env vars),
# then assert the health check answers 2xx. No Cloudron account is used; Postgres
# and Redis run as local containers to stand in for the addons.
#
# Usage: boot_smoke.sh <context_dir> <flavor>
#   <context_dir>  a directory holding a rendered project (Dockerfile at its root)
#   <flavor>       retrofit-lean | greenfield-full  (selects addon env + health path)
set -euo pipefail

CONTEXT_DIR="${1:?usage: boot_smoke.sh <context_dir> <flavor>}"
FLAVOR="${2:?usage: boot_smoke.sh <context_dir> <flavor>}"

# The stand-in app domain. It feeds CLOUDRON_APP_DOMAIN/ORIGIN (so the rendered
# settings set ALLOWED_HOSTS = [this]) and the Host header on the health poll, so
# the two always agree. Cloudron's own reverse proxy forwards the app domain as
# the Host header, so sending it here is faithful, not a workaround.
APP_DOMAIN="localhost"

RUN_ID="${GITHUB_RUN_ID:-local}-$$-${RANDOM}"
NET="smoke-net-${RUN_ID}"
PG="smoke-pg-${RUN_ID}"
REDIS="smoke-redis-${RUN_ID}"
APP="smoke-app-${RUN_ID}"
IMAGE="smoke-image-${RUN_ID}"
DATA_VOL="smoke-data-${RUN_ID}"

case "$FLAVOR" in
    retrofit-lean) HEALTH_PATH="/" ;;
    greenfield-full) HEALTH_PATH="/healthz/" ;;
    *) echo "unknown flavor: $FLAVOR" >&2; exit 2 ;;
esac

cleanup() {
    echo "==> Cleaning up"
    docker rm -f "$APP" "$PG" "$REDIS" >/dev/null 2>&1 || true
    docker volume rm "$DATA_VOL" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Creating network $NET"
docker network create "$NET" >/dev/null

echo "==> Starting Postgres and Redis addons"
docker run -d --name "$PG" --network "$NET" \
    -e POSTGRES_DB=smoke -e POSTGRES_USER=smoke -e POSTGRES_PASSWORD=smoke \
    postgres:15 >/dev/null
docker run -d --name "$REDIS" --network "$NET" redis:7 >/dev/null

echo "==> Waiting for Postgres to accept connections"
PG_READY=""
for _ in $(seq 1 30); do
    if docker exec "$PG" pg_isready -U smoke >/dev/null 2>&1; then PG_READY=1; break; fi
    sleep 1
done
if [ -z "$PG_READY" ]; then
    echo "==> Postgres never became ready; dumping its logs" >&2
    docker logs "$PG" >&2 || true
    exit 1
fi

echo "==> Building image from $CONTEXT_DIR"
docker build -t "$IMAGE" "$CONTEXT_DIR"

# Addon env the generated cloudron_settings reads. The whole settings block is
# gated on CLOUDRON_APP_ORIGIN; ALLOWED_HOSTS comes from CLOUDRON_APP_DOMAIN.
ENV_ARGS=(
    -e "CLOUDRON_APP_ORIGIN=https://${APP_DOMAIN}"
    -e "CLOUDRON_APP_DOMAIN=${APP_DOMAIN}"
    -e "CLOUDRON_POSTGRESQL_HOST=${PG}"
    -e "CLOUDRON_POSTGRESQL_PORT=5432"
    -e "CLOUDRON_POSTGRESQL_DATABASE=smoke"
    -e "CLOUDRON_POSTGRESQL_USERNAME=smoke"
    -e "CLOUDRON_POSTGRESQL_PASSWORD=smoke"
    -e "CLOUDRON_POSTGRESQL_URL=postgres://smoke:smoke@${PG}:5432/smoke"
    -e "CLOUDRON_REDIS_URL=redis://${REDIS}:6379"
)
if [ "$FLAVOR" = "greenfield-full" ]; then
    # sendmail and oidc addons are on for the greenfield cell; the settings block
    # reads these at import, so supply stand-ins (never exercised by the health GET).
    ENV_ARGS+=(
        -e "CLOUDRON_MAIL_SMTP_SERVER=localhost"
        -e "CLOUDRON_MAIL_SMTP_PORT=2525"
        -e "CLOUDRON_MAIL_SMTP_USERNAME=smoke"
        -e "CLOUDRON_MAIL_SMTP_PASSWORD=smoke"
        -e "CLOUDRON_MAIL_FROM=smoke@localhost"
        -e "CLOUDRON_OIDC_ISSUER=https://localhost"
        -e "CLOUDRON_OIDC_CLIENT_ID=smoke"
        -e "CLOUDRON_OIDC_CLIENT_SECRET=smoke"
        -e "CLOUDRON_OIDC_PROVIDER_NAME=Cloudron"
    )
fi

echo "==> Booting app under readonly rootfs"
# Publish the app's port on an ephemeral loopback host port rather than a fixed
# 8000. A fixed host port collides with anything already bound there - and 8000
# is Django's own runserver default, so a developer running this harness locally
# very often has it taken. Docker picks a free port; we read it back below.
docker run -d --name "$APP" --network "$NET" -p 127.0.0.1::8000 \
    --read-only --tmpfs /run --tmpfs /tmp \
    -v "${DATA_VOL}:/app/data" \
    "${ENV_ARGS[@]}" \
    "$IMAGE" >/dev/null

HOST_PORT="$(docker port "$APP" 8000/tcp | head -n1 | sed 's/.*://')"
if [ -z "$HOST_PORT" ]; then
    echo "==> Could not read the published host port for container port 8000" >&2
    docker logs "$APP" >&2 || true
    exit 1
fi

echo "==> Polling http://127.0.0.1:${HOST_PORT}${HEALTH_PATH} (Host: ${APP_DOMAIN}) for a 2xx"
CODE=000
for _ in $(seq 1 60); do
    CODE="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${APP_DOMAIN}" "http://127.0.0.1:${HOST_PORT}${HEALTH_PATH}")" || CODE=000
    case "$CODE" in
        2*) echo "==> Health check passed with HTTP $CODE"; exit 0 ;;
    esac
    sleep 2
done

echo "==> Health check FAILED (last code: $CODE); dumping app logs" >&2
docker logs "$APP" >&2 || true
exit 1
