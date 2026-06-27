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

The generated config imports packages your project must have installed
(dsd-cloudron's deploy step adds them to your requirements): `gunicorn` and a
PostgreSQL driver (`psycopg[binary]`) always; `django-redis` when Redis is
enabled; `celery` when Celery is enabled; `django-allauth` (with its
`openid_connect` provider wired into `INSTALLED_APPS`, `AUTHENTICATION_BACKENDS`,
and your urls) when SSO is enabled. If a needed package is missing, the image
builds but the app fails to start.

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

## Resource tuning

`start.sh` runs `collectstatic` into `/run/{{ project_name }}/static` on every
start. `/run` is tmpfs (RAM-backed), so a large static bundle counts against the
app's `memoryLimit`; raise `memoryLimit` in the manifest if collection runs the
app out of memory. `start.sh` also runs `chown -R cloudron:cloudron /app/data`
each start, which walks the whole persistent volume - a large media library adds
startup latency. When Celery is enabled, the worker runs with `--concurrency=2`;
raise it (and `memoryLimit`) together in `supervisor/celery-worker.conf` if you
need more throughput.
