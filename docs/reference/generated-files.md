# Generated files reference

Both entry points - `python manage.py deploy` (retrofit) and
`dsd-cloudron new` (greenfield) - call the same packaging core to render
this artifact set. The files are the control surface: dsd-cloudron writes
them once, and you edit them from there; a later
`manage.py deploy --force-overwrite` regenerates them from your current
flags instead of leaving stale config behind.

## `CloudronManifest.json`

Cloudron's package manifest, read by `cloudron install` and
`cloudron update`. Fields dsd-cloudron sets:

`addons`
: Always includes `localstorage` (backs the persistent `/app/data`
  volume) and `postgresql`. Adds `redis` unless `--no-redis`, `sendmail`
  unless `--no-sendmail`, and `oidc` when `--sso`.

`memoryLimit`
: From `--memory-limit`. Default `1073741824` (about 1 GB).

`httpPort`
: The port the app listens on inside the container. The platform proxies
  HTTPS traffic to it and terminates TLS itself.

`healthCheckPath`
: From `--health-check-path`. Default `/`. Must return a 2xx response or
  install/update fails its health check.

`author`
: Required by Cloudron's manifest schema (at least 2 characters);
  defaults to a placeholder you should replace before publishing.

`optionalSso`
: Always `true`, regardless of `--sso`. It lets the app accept the local
  `admin` account alongside Cloudron sign-in rather than forcing every
  user through OIDC. What actually turns SSO on is the conditional `oidc`
  addon entry above; see {doc}`cloudron-addons`.

## `<project>/cloudron_settings.py`

The Django settings glue. The whole module body is gated on
`os.environ.get("CLOUDRON_APP_ORIGIN")`, so it is inert during local
development and during the image build - neither has that variable set -
and only takes effect once the container is running on Cloudron.

Inside the gate it sets `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, the HTTPS/proxy and cookie settings - including
`SECURE_SSL_REDIRECT` and a conservative one-hour `SECURE_HSTS_SECONDS` - and
a PostgreSQL `DATABASES` block (always); a Redis `CACHES` block (when Redis
is enabled); `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` (when Celery
is enabled); an SMTP `EMAIL_BACKEND` (when sendmail is enabled); and a
`SOCIALACCOUNT_PROVIDERS` block for the allauth `openid_connect` provider
(when SSO is enabled). On a retrofit `--sso` it also points `ACCOUNT_ADAPTER`
and `SOCIALACCOUNT_ADAPTER` at the shipped `cloudron_adapters.py` (see below).
See {doc}`cloudron-addons` for exactly which `CLOUDRON_*` variables each block
reads.

The last thing it does is check for `/app/data/custom_settings.py` and
execute it - but only when that file is owned by `root` and not group- or
other-writable, so a file the app process could write itself is skipped
(with a note on stderr) rather than run. Create the override inside a root
`cloudron exec` shell and `chown root:cloudron` + `chmod 640` it (see
{doc}`/guides/operating-and-updating`). It is the hook for ad-hoc,
server-side overrides that take effect on the next restart without a
rebuild.

On a retrofit, this file is appended to your project's settings with
`from <project>.cloudron_settings import *`, using an absolute import so
it resolves whether `settings.py` sits at the project root or inside a
`settings/` subpackage. A scaffolded project's `settings.py` instead ends
with a relative, guarded import - `try: from .cloudron_settings import
*`, catching only the case where that module itself is missing - so
local development and tests run cleanly before the file exists. The form
differs, but the net effect is the same: once `cloudron_settings.py` is
generated, both load it.

## `<project>/cloudron_adapters.py` (retrofit `--sso` only)

A standalone allauth adapters module, written into your project package on a
retrofit `--sso` deploy so you point `ACCOUNT_ADAPTER`/`SOCIALACCOUNT_ADAPTER`
at a real file instead of hand-authoring one. Its account adapter closes local
self-service signup (`is_open_for_signup` returns `False`) so Cloudron OIDC is
the only way in, while its social adapter keeps OIDC first-login provisioning
working. `cloudron_settings.py` already points at it under the Cloudron gate. A
scaffolded (`dsd-cloudron new`) project ships its own `accounts/adapters.py`
instead, so this file is retrofit-only.

## Dockerfile, `.dockerignore`, `start.sh`, `nginx.conf`, `supervisor/`

`Dockerfile`
: Installs dependencies with uv. The greenfield/`uv` project installs from
  `pyproject.toml`; a retrofit (`requirements.txt`, `poetry`, or `pipenv`
  project) installs from a `requirements.txt` - generated at deploy time from
  your lock for `poetry`/`pipenv` - so poetry/pipenv never run in the image. It
  then copies the project in, and stages the supervisor
  configs, nginx config, and `start.sh`. The **final** build stage is
  `FROM cloudron/base:5.0.0@sha256:04fd70dbd8ad6149c19de39e35718e024417c3e01dc9c6637eaf4a41ec4e596c`
  - earlier stages may be anything, but the shipped image must end on the
  Cloudron base. The app itself speaks plain HTTP on `httpPort`; the
  platform terminates TLS in front of it.

`.dockerignore`
: Keeps the build context lean. The Dockerfile does `COPY . /app/code/`,
  so anything not listed here ends up in an image layer. Common secret
  patterns (`.env.*`, `*.pem`, `*.key`, `local_settings.py`,
  service-account JSON, `*.har`) are excluded by default; add any other
  project-specific secret files before building.

`start.sh`
: Runs as root inside the container. Each start it creates the writable
  runtime directories, ensures a persistent `SECRET_KEY` exists under
  `/app/data`, and normalizes ownership to `cloudron:cloudron` on
  `/app/data` and the run directories - leaving
  `/app/data/custom_settings.py` untouched, because its ownership is the
  trust signal the override gate above reads. It then collects static
  files and runs `manage.py migrate` - on every start, not only the
  first - each via `gosu cloudron:cloudron`. First run only, gated on
  `/app/data/.initialized`, it creates a local `admin` superuser the
  same way; once initialization has succeeded, the next start removes
  the one-time `/app/data/.initial_admin_password` file. It finishes by
  `exec`-ing `supervisord` directly, with no
  `gosu`, so `supervisord` itself runs as root and becomes the
  container's main process, receiving `SIGTERM` on stop. The
  long-running processes still drop to `cloudron`: gunicorn and the
  celery worker/beat each set `user=cloudron` in their supervisor
  program stanza, and nginx drops its worker processes through the
  `user cloudron;` directive in `nginx.conf` (its master process stays
  root, per nginx convention).

`nginx.conf`
: Listens on `httpPort`, serves `/static/` from
  `/run/<project>/static/` and `/media/` from `/app/data/media/`, and
  proxies everything else to gunicorn over a Unix socket.

`supervisor/`
: One `.conf` per managed process. `gunicorn.conf` and `nginx.conf` are
  always written; `celery-worker.conf` and `celery-beat.conf` are added
  when `--celery` is set, alongside the generated `<project>/celery.py`
  module they import.

`README-cloudron.md`
: A per-project copy of this control-surface summary, written into the
  generated project itself.
