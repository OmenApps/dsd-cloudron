# Cloudron addons reference

Cloudron addons inject configuration as environment variables when the
container starts, not at image-build time - they can change between
restarts (the server rotates credentials, you swap a Redis instance, and
so on). The generated `cloudron_settings.py` reads every variable below
fresh on each start, so a new value takes effect on the next restart
without a rebuild.

`postgresql`
: Always declared - there is no flag to turn it off. The generated
  `DATABASES` block reads `CLOUDRON_POSTGRESQL_HOST`,
  `CLOUDRON_POSTGRESQL_PORT`, `CLOUDRON_POSTGRESQL_DATABASE`,
  `CLOUDRON_POSTGRESQL_USERNAME`, and `CLOUDRON_POSTGRESQL_PASSWORD`.

`redis`
: On by default; drop it with `--no-redis`. The generated `CACHES` block
  (and, with `--celery`, `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`)
  read a single `CLOUDRON_REDIS_URL` - one connection string covers
  host, port, and database, so nothing else is needed. See
  {doc}`/guides/addons-and-email` and {doc}`/guides/enable-celery`.

`sendmail`
: On by default; drop it with `--no-sendmail`. The generated
  `EMAIL_BACKEND` reads `CLOUDRON_MAIL_SMTP_SERVER`,
  `CLOUDRON_MAIL_SMTP_PORT`, `CLOUDRON_MAIL_SMTP_USERNAME`, and
  `CLOUDRON_MAIL_SMTP_PASSWORD` for the SMTP connection, plus
  `CLOUDRON_MAIL_FROM` for `DEFAULT_FROM_EMAIL` and `SERVER_EMAIL` (falls
  back to an empty string if unset). See {doc}`/guides/addons-and-email`.

`oidc`
: Off by default; add it with `--sso`. The generated
  `SOCIALACCOUNT_PROVIDERS` block reads `CLOUDRON_OIDC_ISSUER`,
  `CLOUDRON_OIDC_CLIENT_ID`, and `CLOUDRON_OIDC_CLIENT_SECRET` for the
  allauth `openid_connect` provider, plus `CLOUDRON_OIDC_PROVIDER_NAME`
  for the display name (falls back to `Cloudron` if unset). See
  {doc}`/guides/enable-sso`.

`localstorage`
: Always declared; backs the persistent `/app/data` volume. The
  generated settings do not read an addon-specific variable for it - it
  works by mounting the volume, not by injecting configuration.

## Always present, not tied to an addon

`CLOUDRON_APP_ORIGIN`
: Set on every Cloudron app regardless of which addons are enabled. Gates
  the entire `cloudron_settings.py` block - its absence is how the
  settings stay inert during local development - and feeds
  `CSRF_TRUSTED_ORIGINS`.

`CLOUDRON_APP_DOMAIN`
: Also always present. Feeds `ALLOWED_HOSTS`.
