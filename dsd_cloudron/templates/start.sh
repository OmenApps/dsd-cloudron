#!/bin/bash
set -eu

APP="{{ project_name }}"
CODE=/app/code
RUN="/run/${APP}"

echo "==> Creating writable directories"
mkdir -p "${RUN}/static" /run/nginx /app/data/media

echo "==> Ensuring persistent secret key"
# Guard on non-empty (-s) and write atomically (temp then mv) so an interrupted
# first boot cannot leave a zero-byte key file on the persistent /app/data
# volume, which would brick every later start with an empty SECRET_KEY.
if [[ ! -s /app/data/.secret_key ]]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(64))" > /app/data/.secret_key.tmp
    mv /app/data/.secret_key.tmp /app/data/.secret_key
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
    # Scope the default password to this one command so it never enters the
    # long-lived supervisord/gunicorn/celery environment. Only mark initialized
    # when the superuser is actually created, so a failed first run (e.g.
    # createsuperuser errors) retries next start instead of silently leaving the
    # app with no admin account. The `if` guard keeps the non-zero exit from
    # tripping `set -e`.
    if DJANGO_SUPERUSER_PASSWORD="changeme123" gosu cloudron:cloudron \
        python3 "${CODE}/manage.py" createsuperuser \
        --username admin --email admin@cloudron.local --noinput; then
        touch /app/data/.initialized
    else
        echo "==> Superuser not created; will retry on next start"
    fi
fi

echo "==> Starting supervisor"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon
