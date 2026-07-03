# Cloudron deployment for blog

This directory was configured for Cloudron by dsd-cloudron. The generated files
ARE the configuration control surface - edit them and re-deploy.

## Control surface

- `CloudronManifest.json` - addons, `memoryLimit`, `httpPort`, `healthCheckPath`.
  `healthCheckPath` MUST return a 2xx response or the install fails its health
  check. The default is `/`; if your project returns 404 there under
  `DEBUG=False`, set a path that returns 200 (re-run deploy with
  `--health-check-path`, or edit the manifest).
- `blog/cloudron_settings.py` - the Django settings glue. Every
  override is gated on `CLOUDRON_APP_ORIGIN`, so it is inert during local
  development. Drop a `/app/data/custom_settings.py` on the server for ad-hoc
  overrides; it is imported last, but only when it is owned by root and not
  group/other-writable. Create it inside `cloudron exec` (which runs as root),
  then `chown root:cloudron /app/data/custom_settings.py && chmod 640` it so
  gunicorn can read it. A file the app itself could write is skipped (with a note
  on stderr), so an upload cannot turn into persistent code execution.
- `Dockerfile`, `start.sh`, `nginx.conf`, `supervisor/` - the runtime. The app
  speaks plain HTTP on port 8000; Cloudron terminates TLS.
- `.dockerignore` - keeps the build context lean. The Dockerfile does
  `COPY . /app/code/`, so anything not ignored is baked into the image. Common
  secret-bearing files (`.env.*`, `*.pem`, `*.key`, `local_settings.py`,
  service-account JSON, `*.har`) are excluded by default; add any other
  project-specific secret files before building so they do not end up in an
  image layer.

## Required packages

The generated config imports packages your project must have installed. The
deploy step ensures they end up in the `requirements.txt` the image builds from -
adding them directly for a requirements.txt project, or writing a `requirements.txt`
exported from your lock for a Poetry or Pipenv project. The packages are
`gunicorn` and a PostgreSQL driver (`psycopg[binary]`) always; `django-redis` when
Redis is enabled; `celery[redis]` when Celery is enabled; `django-allauth[socialaccount]`
when SSO is enabled. If a needed package is missing, the image builds but the app
fails to start.

### Single sign-on

`django-allauth[socialaccount]` is added to your requirements and a
`SOCIALACCOUNT_PROVIDERS` block is written, but allauth is NOT auto-wired into your
project - a retrofit deploy will not rewrite your `INSTALLED_APPS` or `urls.py`.
Finish the wiring yourself: see `CLOUDRON_NEXT_STEPS.md` (written next to this file
after each deploy) and the enable-sso guide. Close local self-service signup at the
same time - set `ACCOUNT_ADAPTER` to an adapter whose `is_open_for_signup` returns
`False` - or `/accounts/signup/` stays open once you mount `allauth.urls`.

## Deploy and iterate

```bash
cloudron login my.example.com
cloudron install -l <subdomain>     # first deploy
# edit code or config, then:
cloudron update --app <subdomain>   # subsequent deploys
cloudron logs --app <subdomain> -f  # tail logs
```

`/app/data` and the Postgres/Redis addons persist across updates. `migrate` runs
on every start, so new migrations apply automatically.

## First sign-in

A local `admin` superuser is created on the first install. Its password is
generated per install and saved on the server at
`/app/data/.initial_admin_password`. Retrieve it with:

```bash
cloudron exec --app <subdomain> -- cat /app/data/.initial_admin_password
```

Read it during this first-boot window: the file is removed automatically on the
next start once the app is initialized, so it does not linger in every backup. If
you miss it, reset the password with `cloudron exec --app <subdomain> --
python3 /app/code/manage.py changepassword admin`. Sign in at `/admin/` and change
the password. With SSO enabled, sign in with your Cloudron account instead; the
local `admin` is a break-glass account you can use to promote your Cloudron user
in the Django admin. The default account assumes the standard Django user model
(`USERNAME_FIELD = "username"`); a project with a custom user model should create
its superuser manually.

## Resource tuning

`start.sh` runs `collectstatic` into `/run/blog/static` on every
start. `/run` is tmpfs (RAM-backed), so a large static bundle counts against the
app's `memoryLimit`; raise `memoryLimit` in the manifest if collection runs the
app out of memory. `start.sh` also normalizes ownership under `/app/data` each
start (a recursive `chown`, or a `find` that skips `custom_settings.py` when that
override file exists), which walks the whole persistent volume - a large media
library adds startup latency. When Celery is enabled, the worker runs with `--concurrency=2`;
raise it (and `memoryLimit`) together in `supervisor/celery-worker.conf` if you
need more throughput.
