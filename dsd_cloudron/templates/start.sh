#!/bin/bash
set -eu

APP="{{ project_name }}"
CODE=/app/code
RUN="/run/${APP}"

echo "==> Creating writable directories"
mkdir -p "${RUN}/static" /run/nginx /app/data/media

echo "==> Ensuring persistent secret key"
if [[ ! -f /app/data/.secret_key ]]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(64))" > /app/data/.secret_key
fi
export SECRET_KEY="$(cat /app/data/.secret_key)"

source "${CODE}/venv/bin/activate"

echo "==> Normalizing ownership"
chown -R cloudron:cloudron /app/data "${RUN}" /run/nginx

echo "==> Collecting static files into ${RUN}/static"
gosu cloudron:cloudron python3 "${CODE}/manage.py" collectstatic --noinput

echo "==> Applying database migrations"
gosu cloudron:cloudron python3 "${CODE}/manage.py" migrate --noinput

if [[ ! -f /app/data/.initialized ]]; then
    echo "==> First run: creating default admin superuser"
    export DJANGO_SUPERUSER_PASSWORD="changeme123"
    # Only mark initialized when the superuser is actually created, so a failed
    # first run (e.g. createsuperuser errors) retries next start instead of
    # silently leaving the app with no admin account. The `if` guard keeps the
    # non-zero exit from tripping `set -e`.
    if gosu cloudron:cloudron python3 "${CODE}/manage.py" createsuperuser \
        --username admin --email admin@cloudron.local --noinput; then
        touch /app/data/.initialized
    else
        echo "==> Superuser not created; will retry on next start"
    fi
fi

echo "==> Starting supervisor"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon
