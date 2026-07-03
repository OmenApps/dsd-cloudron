# Cloudron deployment for {{ project_name }}

This directory was configured for Cloudron by dsd-cloudron. The generated files
ARE the configuration control surface - edit them and re-deploy.

## Control surface

- `CloudronManifest.json` - addons, `memoryLimit`, `httpPort`, `healthCheckPath`.
  `healthCheckPath` MUST return a 2xx response or the install fails its health
  check. The default is `/`; if your project returns 404 there under
  `DEBUG=False`, set a path that returns 200 (re-run deploy with
  `--health-check-path`, or edit the manifest).
- `{{ project_name }}/cloudron_settings.py` - the Django settings glue. Every
  override is gated on `CLOUDRON_APP_ORIGIN`, so it is inert during local
  development. Drop a `/app/data/custom_settings.py` on the server for ad-hoc
  overrides; it is imported last.
- `Dockerfile`, `start.sh`, `nginx.conf`, `supervisor/` - the runtime. The app
  speaks plain HTTP on port {{ http_port }}; Cloudron terminates TLS.
- `.dockerignore` - keeps the build context lean. The Dockerfile does
  `COPY . /app/code/`, so anything not ignored is baked into the image. Add any
  project-specific secret files (service-account JSON, `*.pem`, `local_settings.py`)
  to it before building so they do not end up in an image layer.

## Required packages

The generated config imports packages your project must have installed. The
deploy step ensures they end up in the `requirements.txt` the image builds from -
adding them directly for a requirements.txt project, or writing a `requirements.txt`
exported from your lock for a Poetry or Pipenv project. The packages are
`gunicorn` and a PostgreSQL driver (`psycopg[binary]`) always; `django-redis` when
Redis is enabled; `celery[redis]` when Celery is enabled; `django-allauth[socialaccount]`
when SSO is enabled. If a needed package is missing, the image builds but the app
fails to start.
{% if enable_sso %}
### Single sign-on

{% if greenfield %}This project ships with django-allauth fully wired: the `openid_connect`
provider is in `INSTALLED_APPS`, `AUTHENTICATION_BACKENDS` keeps the model backend
and adds allauth's, the account middleware is installed, and `allauth.urls` is
mounted. Sign in with your Cloudron account; the local `admin` is a break-glass
account.
{% else %}`django-allauth[socialaccount]` is added to your requirements and a
`SOCIALACCOUNT_PROVIDERS` block is written, but allauth is NOT auto-wired into your
project - a retrofit deploy will not rewrite your `INSTALLED_APPS` or `urls.py`.
Finish the wiring yourself: see `CLOUDRON_NEXT_STEPS.md` (written next to this file
after each deploy) and the enable-sso guide. Close local self-service signup at the
same time - set `ACCOUNT_ADAPTER` to an adapter whose `is_open_for_signup` returns
`False` - or `/accounts/signup/` stays open once you mount `allauth.urls`.
{% endif %}{% endif %}
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

Sign in at `/admin/`, change the password, then delete
`/app/data/.initial_admin_password` - it persists in backups until you do. With
SSO enabled, sign in with your Cloudron account instead; the local `admin` is a
break-glass account you can use to promote your Cloudron user in the Django
admin. The default account assumes the standard Django user model
(`USERNAME_FIELD = "username"`); a project with a custom user model should create
its superuser manually.

## Resource tuning

`start.sh` runs `collectstatic` into `/run/{{ project_name }}/static` on every
start. `/run` is tmpfs (RAM-backed), so a large static bundle counts against the
app's `memoryLimit`; raise `memoryLimit` in the manifest if collection runs the
app out of memory. `start.sh` also runs `chown -R cloudron:cloudron /app/data`
each start, which walks the whole persistent volume - a large media library adds
startup latency. When Celery is enabled, the worker runs with `--concurrency=2`;
raise it (and `memoryLimit`) together in `supervisor/celery-worker.conf` if you
need more throughput.
