# Addons and email

Every deploy declares a set of Cloudron addons in `CloudronManifest.json`
and wires the environment variables those addons inject into the generated
Django settings. This guide covers what is on by default, how outgoing
email works, and the flags that size and identify the app on the server.

## Default addons

PostgreSQL, Redis, and sendmail are configured automatically on both
`manage.py deploy` and `dsd-cloudron new`:

PostgreSQL
: No off switch - every Django project needs a database, so it is always
  declared.

Redis
: Backs the Django cache (`django-redis`) and, when `--celery` is set,
  the Celery broker too. Drop it with `--no-redis` if your project does
  not use a cache.

sendmail
: Delivers outgoing email through Cloudron's mail relay. Drop it with
  `--no-sendmail` if your project does not send mail.

```bash
python manage.py deploy --location blog --no-redis --no-sendmail
dsd-cloudron new "My App" --no-redis --no-sendmail
```

`--celery` requires Redis, since the worker and beat use the Redis addon
as their broker - combining it with `--no-redis` is rejected before
anything is written. See {doc}`enable-celery` for the rest of that setup.

## Email through the sendmail addon

With sendmail enabled, the generated Cloudron settings configure Django's
SMTP email backend to read the connection details Cloudron injects at
runtime, rather than hardcoding any mail credentials:

```python
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ["CLOUDRON_MAIL_SMTP_SERVER"]
EMAIL_PORT = int(os.environ["CLOUDRON_MAIL_SMTP_PORT"])
EMAIL_HOST_USER = os.environ["CLOUDRON_MAIL_SMTP_USERNAME"]
EMAIL_HOST_PASSWORD = os.environ["CLOUDRON_MAIL_SMTP_PASSWORD"]
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = os.environ.get("CLOUDRON_MAIL_FROM", "")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
```

`CLOUDRON_MAIL_SMTP_*` and `CLOUDRON_MAIL_FROM` come from the sendmail
addon, and they are read at process start rather than baked into the
image - that matters because Cloudron can rotate them, and the app picks
up the new values on its next start without a rebuild. There is nothing
to configure on the addon itself; `cloudron email` on the server controls
the relay's outbound settings if you need to adjust those.

If you turn sendmail off, none of this block is rendered, and Django
falls back to whatever `EMAIL_BACKEND` your own settings define (the
console backend, by default, which only logs messages instead of sending
them).

## Sizing and identity flags

A handful of flags control how the app is identified and sized on the
Cloudron server, independent of which addons are enabled:

`--app-id`
: Reverse-DNS app id, e.g. `com.example.blog`. This is what Cloudron uses
  internally to identify the app, separate from the subdomain it is
  installed at. Defaults to `com.example.<project-name>`.

`--memory-limit`
: Memory limit in bytes, enforced by Cloudron as a hard cap on the app's
  container. Defaults to `1073741824` (1 GB). Raise it for projects that
  need more headroom, for example a Celery worker processing large jobs.

`--health-check-path`
: The path Cloudron polls after install and on every update to decide the
  app is up. It must return a 2xx response, or the install or update
  fails its health check. Defaults to `/`; a project scaffolded with
  `dsd-cloudron new` ships a `/healthz/` view that always returns 200, so
  the default works out of the box. On a retrofit, point this at a route
  that returns one if your root view does not - see
  {doc}`troubleshooting` if an install fails this check.

## Targeting a Cloudron server

`--server` and `--allow-selfsigned` are not addon flags, but they affect
which server an install lands on:

`--server`
: Which logged-in Cloudron server to target, if `cloudron login` has been
  run against more than one. Without it, the deploy uses whichever
  session the `cloudron` CLI considers current.

`--allow-selfsigned`
: Accept a self-signed certificate on that server, for a Cloudron
  instance that is not yet using a certificate from a trusted CA.

Both only matter when `--automate-all` (or `dsd-cloudron new` followed by
`cloudron install`) actually talks to a server; with config-only deploys
they have no effect.
