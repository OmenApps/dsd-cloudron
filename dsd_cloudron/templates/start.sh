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
    chmod 600 /app/data/.secret_key.tmp
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
    # Generate a per-install random password so the open-source image ships no
    # world-known default credential. Persist it to /app/data (mode 600) so the
    # operator can retrieve it with `cloudron exec`; scope it to this one command
    # so it never enters the long-lived supervisord/gunicorn/celery environment.
    # Only mark initialized when the superuser is actually created, so a failed
    # first run retries next start instead of leaving the app with no admin.
    # createsuperuser names its login flag after the user model's USERNAME_FIELD,
    # so `--username admin` assumes the standard Django user model; a project with
    # a custom user model must create its admin manually. If an admin already
    # exists (e.g. /app/data was reset while the Postgres addon persisted) this
    # fails harmlessly and retries each start; the saved password file then no
    # longer matches that admin, so reset it with `manage.py changepassword admin`
    # via `cloudron exec` rather than reading the file.
    if [[ ! -s /app/data/.initial_admin_password ]]; then
        python3 -c "import secrets; print(secrets.token_urlsafe(18))" > /app/data/.initial_admin_password.tmp
        chmod 600 /app/data/.initial_admin_password.tmp
        mv /app/data/.initial_admin_password.tmp /app/data/.initial_admin_password
    fi
    if DJANGO_SUPERUSER_PASSWORD="$(cat /app/data/.initial_admin_password)" gosu cloudron:cloudron \
        python3 "${CODE}/manage.py" createsuperuser \
        --username admin --email admin@cloudron.local --noinput; then
        touch /app/data/.initialized
    else
        echo "==> Superuser not created; will retry on next start"
    fi
fi

echo "==> Starting supervisor"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon
