#!/bin/bash
set -euo pipefail

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
# Normalize ownership of the persistent volume, but never touch
# /app/data/custom_settings.py: its owner is the trust signal the settings
# gate reads. A plain recursive chown to cloudron:cloudron would downgrade a
# legit root-owned override, which the gate then rejects (the override silently
# stops working); and re-chowning it to root - the rejected alternative - would
# launder an attacker-dropped, cloudron-owned file into a root-owned one the gate
# execs. So leave its ownership alone whichever way it points. The find branch
# prunes that one path and uses chown -h so a symlink the app wrote under
# /app/data is never dereferenced (plain chown follows a symlink argument, and a
# dangling one would abort every start under set -eu). The common no-override
# case stays on the cheaper recursive chown.
if [[ -e /app/data/custom_settings.py || -L /app/data/custom_settings.py ]]; then
    find /app/data -path /app/data/custom_settings.py -prune -o -exec chown -h cloudron:cloudron {} +
else
    chown -R cloudron:cloudron /app/data
fi
chown -R cloudron:cloudron "${RUN}" /run/nginx

echo "==> Collecting static files into ${RUN}/static"
gosu cloudron:cloudron python3 "${CODE}/manage.py" collectstatic --noinput

echo "==> Applying database migrations"
# Wrap migrate so a failure prints a distinct, greppable marker to stderr before the
# boot aborts. Under `set -e` a bare failing command aborts with only Django's own
# traceback and no distinct marker; the `if !` (exempt from set -e) lets us emit the
# marker and then exit non-zero ourselves.
if ! gosu cloudron:cloudron python3 "${CODE}/manage.py" migrate --noinput; then
    echo "==> MIGRATE_FAILED" >&2
    exit 1
fi
{% if enable_wagtail %}
# Point the default Wagtail Site at the deployed host. page.full_url, canonical
# links, og:url, and sitemap.xml derive from the Wagtail Site record, NOT
# WAGTAILADMIN_BASE_URL, so without this a fresh install serves the localhost:80
# seed. cloudron_settings.py sets WAGTAILADMIN_BASE_URL from CLOUDRON_APP_ORIGIN;
# read the host back from it here. Idempotent every boot; the instance .save()
# (not a queryset .update()) fires the post_save signal that clears Wagtail's
# cached site root paths, which a bare UPDATE would leave stale.
echo "==> Pointing the default Wagtail Site at the deployed host"
gosu cloudron:cloudron python3 "${CODE}/manage.py" shell -c '
from urllib.parse import urlparse
from django.conf import settings
from wagtail.models import Site
parsed = urlparse(settings.WAGTAILADMIN_BASE_URL)
site = Site.objects.filter(is_default_site=True).first()
if parsed.hostname and site is not None:
    site.hostname = parsed.hostname
    site.port = parsed.port or (443 if parsed.scheme == "https" else 80)
    site.save()
    print("Default Wagtail Site ->", site.hostname, site.port)
'
{% endif %}
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

# Retire the one-time admin password only after the operator acknowledges they
# have it - never on a plain restart. Deleting it by restart count strands it:
# image updates and health-check restarts reuse the persistent /app/data and boot
# a fresh container first, so the file's creating container is usually gone before
# an operator can open a shell. Instead keep reprinting the retrieve + acknowledge
# steps every boot - never the value - and delete the file only once
# /app/data/.initial_admin_password.acknowledged exists (the operator touches it
# via `cloudron exec`, which runs as root). Clear the marker alongside the file so
# a later re-init generates and re-announces a fresh password instead of deleting
# it against a stale acknowledgement.
if [[ -f /app/data/.initial_admin_password ]]; then
    if [[ -f /app/data/.initial_admin_password.acknowledged ]]; then
        echo "==> Initial admin password acknowledged; removing the one-time file"
        rm -f /app/data/.initial_admin_password /app/data/.initial_admin_password.acknowledged
    else
        echo "==> A generated admin password is stored on the server. Retrieve it, then acknowledge so it can be removed:"
        echo "==>   cloudron exec --app <subdomain> -- cat /app/data/.initial_admin_password"
        echo "==>   cloudron exec --app <subdomain> -- touch /app/data/.initial_admin_password.acknowledged"
    fi
fi

echo "==> Starting supervisor"
exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon
